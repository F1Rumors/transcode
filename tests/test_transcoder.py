"""Tests for transcode.transcoder."""

import contextlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

import imageio_ffmpeg

from transcode.config import TranscodeConfig
from transcode.presets import RESOLUTIONS
from transcode.transcoder import (
    TranscodeResult,
    build_ffmpeg_command,
    derive_output_path,
    find_source_path,
    transcode_all,
    transcode_file,
)

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def make_test_clip(path: Path, duration: int = 1, width: int = 320, height: int = 240) -> None:
    """Generate a tiny synthetic video clip using ffmpeg's lavfi source."""
    cmd = [
        FFMPEG, "-y",
        "-f", "lavfi", "-i", f"color=c=blue:size={width}x{height}:rate=10",
        "-t", str(duration),
        "-c:v", "libx264", "-crf", "30", "-preset", "ultrafast",
        "-an",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"Failed to create test clip: {result.stderr.decode()}")


def _cfg(**kwargs) -> TranscodeConfig:
    defaults = dict(ffmpeg_executable=FFMPEG)
    defaults.update(kwargs)
    return TranscodeConfig(**defaults)


# ── find_source_path ──────────────────────────────────────────────────────────

class TestFindSourcePath(unittest.TestCase):

    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.tmp = Path(stack.enter_context(tempfile.TemporaryDirectory()))

    def _make(self, name: str) -> Path:
        p = self.tmp / name
        p.write_bytes(b"x")
        return p

    def test_no_suffix_returns_original(self):
        f = self._make("arials.mp4")
        self.assertEqual(find_source_path(f), f)

    def test_resolution_suffix_with_original_present(self):
        original = self._make("arials.mp4")
        derived = self._make("arials_720p.mp4")
        self.assertEqual(find_source_path(derived), original)

    def test_resolution_suffix_without_original_returns_self(self):
        derived = self._make("arials_720p.mp4")
        # arials.mp4 does NOT exist
        self.assertEqual(find_source_path(derived), derived)

    def test_fps_only_suffix_with_original_present(self):
        original = self._make("arials.mp4")
        derived = self._make("arials_24fps.mp4")
        self.assertEqual(find_source_path(derived), original)

    def test_resolution_and_fps_suffix(self):
        original = self._make("arials.mp4")
        derived = self._make("arials_720p_24fps.mp4")
        self.assertEqual(find_source_path(derived), original)

    def test_all_resolution_names_recognised(self):
        for res in ("4k", "1080p", "1080i", "720p", "720i", "pal"):
            with self.subTest(res=res):
                original = self._make(f"clip.mp4")
                derived = self._make(f"clip_{res}.mp4")
                self.assertEqual(find_source_path(derived), original)
                original.unlink()
                derived.unlink()

    def test_case_insensitive(self):
        original = self._make("clip.mp4")
        derived = self._make("clip_720P.mp4")
        self.assertEqual(find_source_path(derived), original)

    def test_unrelated_underscore_not_stripped(self):
        # "my_video.mp4" — "_video" is not a resolution suffix
        f = self._make("my_video.mp4")
        self.assertEqual(find_source_path(f), f)

    def test_use_original_respected_in_transcode_file(self):
        """transcode_file uses the original when use_original=True."""
        original = self._make("arials.mp4")
        # Create a minimal valid mp4 for the original
        make_test_clip(original)
        derived = self.tmp / "arials_720p.mp4"
        derived.write_bytes(b"old transcoded data")

        cfg = _cfg(resolution=RESOLUTIONS["pal"], overwrite=True, use_original=True)
        r = transcode_file(derived, cfg)
        self.assertTrue(r.ok, msg=r.stderr)
        # Output should be arials_pal.mp4, derived from the original stem
        self.assertEqual(r.output_path.name, "arials_pal.mp4")

    def test_no_original_flag_uses_file_as_is(self):
        """transcode_file uses the clicked file when use_original=False."""
        self._make("arials.mp4")  # original exists but should be ignored
        derived = self._make("arials_720p.mp4")
        make_test_clip(derived)

        cfg = _cfg(resolution=RESOLUTIONS["pal"], overwrite=True, use_original=False)
        r = transcode_file(derived, cfg)
        self.assertTrue(r.ok, msg=r.stderr)
        # Output is derived from arials_720p stem, not arials
        self.assertEqual(r.output_path.name, "arials_720p_pal.mp4")


# ── derive_output_path ────────────────────────────────────────────────────────

class TestDeriveOutputPath(unittest.TestCase):

    def _path(self, name):
        return Path("/videos") / name

    def test_resolution_suffix_added(self):
        cfg = _cfg(resolution=RESOLUTIONS["720p"])
        out = derive_output_path(self._path("arials.mp4"), cfg)
        self.assertEqual(out.name, "arials_720p.mp4")

    def test_fps_suffix_added(self):
        cfg = _cfg(fps=24)
        out = derive_output_path(self._path("arials.mp4"), cfg)
        self.assertEqual(out.name, "arials_24fps.mp4")

    def test_resolution_and_fps_both_suffixed(self):
        cfg = _cfg(resolution=RESOLUTIONS["1080p"], fps=30)
        out = derive_output_path(self._path("arials.mp4"), cfg)
        self.assertEqual(out.name, "arials_1080p_30fps.mp4")

    def test_format_only_changes_extension(self):
        cfg = _cfg(fmt="mov")
        out = derive_output_path(self._path("arials.mp4"), cfg)
        self.assertEqual(out.name, "arials.mov")

    def test_resolution_with_format_change(self):
        cfg = _cfg(resolution=RESOLUTIONS["720p"], fmt="mov")
        out = derive_output_path(self._path("arials.mp4"), cfg)
        self.assertEqual(out.name, "arials_720p.mov")

    def test_output_dir_used_when_set(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = _cfg(resolution=RESOLUTIONS["720p"], output_dir=Path(d))
            out = derive_output_path(self._path("arials.mp4"), cfg)
            self.assertEqual(out.parent, Path(d))
            self.assertEqual(out.name, "arials_720p.mp4")

    def test_parent_dir_unchanged_when_no_output_dir(self):
        cfg = _cfg(resolution=RESOLUTIONS["720p"])
        inp = self._path("arials.mp4")
        out = derive_output_path(inp, cfg)
        self.assertEqual(out.parent, inp.parent)

    def test_avi_input_extension_preserved(self):
        cfg = _cfg(resolution=RESOLUTIONS["720p"])
        out = derive_output_path(self._path("clip.avi"), cfg)
        self.assertEqual(out.suffix, ".avi")


# ── build_ffmpeg_command ──────────────────────────────────────────────────────

class TestBuildFfmpegCommand(unittest.TestCase):

    def _cmd(self, inp, out, **kwargs):
        return build_ffmpeg_command(Path(inp), Path(out), _cfg(**kwargs))

    def test_executable_is_first_token(self):
        cmd = self._cmd("/a.mp4", "/a_720p.mp4", resolution=RESOLUTIONS["720p"])
        self.assertEqual(cmd[0], FFMPEG)

    def test_input_and_output_present(self):
        cmd = self._cmd("/a.mp4", "/a_720p.mp4", resolution=RESOLUTIONS["720p"])
        self.assertTrue(any("a.mp4" in arg and "720p" not in arg for arg in cmd))
        self.assertTrue(any("a_720p.mp4" in arg for arg in cmd))

    def test_no_overwrite_flag_by_default(self):
        cmd = self._cmd("/a.mp4", "/a_720p.mp4", resolution=RESOLUTIONS["720p"])
        self.assertIn("-n", cmd)
        self.assertNotIn("-y", cmd)

    def test_overwrite_flag(self):
        cmd = self._cmd("/a.mp4", "/a_720p.mp4", resolution=RESOLUTIONS["720p"], overwrite=True)
        self.assertIn("-y", cmd)
        self.assertNotIn("-n", cmd)

    def test_libx264_for_mp4_output(self):
        cmd = self._cmd("/a.mp4", "/a_720p.mp4", resolution=RESOLUTIONS["720p"])
        self.assertIn("libx264", cmd)

    def test_mpeg4_for_avi_output(self):
        cmd = self._cmd("/a.mp4", "/a_720p.avi", resolution=RESOLUTIONS["720p"], fmt="avi")
        self.assertIn("mpeg4", cmd)
        self.assertNotIn("libx264", cmd)

    def test_vf_filter_present_with_resolution(self):
        cmd = self._cmd("/a.mp4", "/a_720p.mp4", resolution=RESOLUTIONS["720p"])
        self.assertIn("-vf", cmd)
        vf_val = cmd[cmd.index("-vf") + 1]
        self.assertIn("scale=1280:720", vf_val)

    def test_no_vf_without_resolution(self):
        cmd = self._cmd("/a.mp4", "/a_24fps.mp4", fps=24)
        self.assertNotIn("-vf", cmd)

    def test_fps_flag_present(self):
        cmd = self._cmd("/a.mp4", "/a_24fps.mp4", fps=24)
        self.assertIn("-r", cmd)
        self.assertEqual(cmd[cmd.index("-r") + 1], "24")

    def test_no_fps_flag_without_fps(self):
        cmd = self._cmd("/a.mp4", "/a_720p.mp4", resolution=RESOLUTIONS["720p"])
        self.assertNotIn("-r", cmd)

    def test_audio_copy_for_mp4_output(self):
        cmd = self._cmd("/a.mp4", "/a_720p.mp4", resolution=RESOLUTIONS["720p"])
        idx = cmd.index("-c:a")
        self.assertEqual(cmd[idx + 1], "copy")

    def test_mp3lame_for_avi_output(self):
        cmd = self._cmd("/a.mp4", "/a_720p.avi", resolution=RESOLUTIONS["720p"], fmt="avi")
        idx = cmd.index("-c:a")
        self.assertEqual(cmd[idx + 1], "libmp3lame")

    def test_stream_copy_for_mp4_to_mov_format_only(self):
        """No resolution or fps change, mp4→mov: video should be stream-copied."""
        cmd = self._cmd("/a.mp4", "/a.mov", fmt="mov")
        idx = cmd.index("-c:v")
        self.assertEqual(cmd[idx + 1], "copy")

    def test_stream_copy_not_used_when_resolution_also_changes(self):
        cmd = self._cmd("/a.mp4", "/a_720p.mov", resolution=RESOLUTIONS["720p"], fmt="mov")
        idx = cmd.index("-c:v")
        self.assertNotEqual(cmd[idx + 1], "copy")

    def test_interlaced_x264opts_present(self):
        cmd = self._cmd("/a.mp4", "/a_1080i.mp4", resolution=RESOLUTIONS["1080i"])
        self.assertIn("-x264opts", cmd)
        x264_val = cmd[cmd.index("-x264opts") + 1]
        self.assertIn("interlaced=1", x264_val)

    def test_interlaced_setfield_in_vf(self):
        cmd = self._cmd("/a.mp4", "/a_1080i.mp4", resolution=RESOLUTIONS["1080i"])
        vf_val = cmd[cmd.index("-vf") + 1]
        self.assertIn("setfield=tff", vf_val)

    def test_crf_quality_passed(self):
        cmd = self._cmd("/a.mp4", "/a_720p.mp4", resolution=RESOLUTIONS["720p"], quality=18)
        idx = cmd.index("-crf")
        self.assertEqual(cmd[idx + 1], "18")


# ── transcode_file — real ffmpeg ──────────────────────────────────────────────

class TestTranscodeFileReal(unittest.TestCase):
    """Integration tests that actually invoke ffmpeg."""

    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.tmp = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        self.src = self.tmp / "clip.mp4"
        make_test_clip(self.src)

    def test_transcode_to_lower_resolution_creates_output(self):
        cfg = _cfg(resolution=RESOLUTIONS["pal"], overwrite=True)
        r = transcode_file(self.src, cfg)
        self.assertTrue(r.ok, msg=r.stderr)
        self.assertTrue(r.output_path.exists())

    def test_fps_change_produces_output(self):
        cfg = _cfg(fps=24, overwrite=True)
        r = transcode_file(self.src, cfg)
        self.assertTrue(r.ok, msg=r.stderr)
        self.assertTrue(r.output_path.exists())

    def test_skips_when_output_equals_input(self):
        """format=mp4 on an mp4 input with no other changes → output==input → skip."""
        cfg = _cfg(fmt="mp4")
        r = transcode_file(self.src, cfg)
        self.assertTrue(r.skipped)
        self.assertIn("same as input", r.skip_reason)

    def test_skips_when_output_exists_and_no_overwrite(self):
        out = self.tmp / "clip_pal.mp4"
        out.write_bytes(b"existing")
        cfg = _cfg(resolution=RESOLUTIONS["pal"])
        r = transcode_file(self.src, cfg)
        self.assertTrue(r.skipped)
        self.assertIn("already exists", r.skip_reason)

    def test_dryrun_skips_without_creating_output(self):
        cfg = _cfg(resolution=RESOLUTIONS["pal"], dryrun=True)
        r = transcode_file(self.src, cfg)
        self.assertTrue(r.skipped)
        self.assertIn("dryrun", r.skip_reason)
        self.assertFalse((self.tmp / "clip_pal.mp4").exists())

    def test_output_to_separate_directory(self):
        out_dir = self.tmp / "out"
        out_dir.mkdir()
        cfg = _cfg(resolution=RESOLUTIONS["pal"], output_dir=out_dir, overwrite=True)
        r = transcode_file(self.src, cfg)
        self.assertTrue(r.ok, msg=r.stderr)
        self.assertEqual(r.output_path.parent, out_dir)


# ── transcode_all ─────────────────────────────────────────────────────────────

class TestTranscodeAll(unittest.TestCase):

    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.tmp = Path(stack.enter_context(tempfile.TemporaryDirectory()))

    def test_missing_file_reported_and_skipped(self):
        missing = self.tmp / "no_such_file.mp4"
        cfg = _cfg(resolution=RESOLUTIONS["pal"])
        printed = []
        with __import__("unittest.mock", fromlist=["patch"]).patch(
            "builtins.print", side_effect=lambda *a, **k: printed.append(" ".join(str(x) for x in a))
        ):
            results = transcode_all([missing], cfg)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].skipped)
        self.assertIn("file not found", "\n".join(printed))

    def test_continues_after_missing_file(self):
        missing = self.tmp / "no_such_file.mp4"
        existing = self.tmp / "clip.mp4"
        make_test_clip(existing)
        cfg = _cfg(resolution=RESOLUTIONS["pal"], overwrite=True)
        with __import__("unittest.mock", fromlist=["patch"]).patch("builtins.print"):
            results = transcode_all([missing, existing], cfg)
        self.assertEqual(len(results), 2)
        self.assertTrue(results[0].skipped)
        self.assertTrue(results[1].ok)

    def test_returns_all_results(self):
        files = []
        for name in ("a.mp4", "b.mp4"):
            f = self.tmp / name
            make_test_clip(f)
            files.append(f)
        cfg = _cfg(resolution=RESOLUTIONS["pal"], overwrite=True)
        with __import__("unittest.mock", fromlist=["patch"]).patch("builtins.print"):
            results = transcode_all(files, cfg)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.ok for r in results))
