"""Tests for transcode.cli."""

import contextlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

import imageio_ffmpeg

from transcode.cli import build_parser, main

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def make_test_clip(path: Path, duration: int = 1, width: int = 320, height: int = 240) -> None:
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


# ── build_parser ──────────────────────────────────────────────────────────────

class TestBuildParser(unittest.TestCase):

    def _parse(self, *args):
        return build_parser().parse_args(args)

    def test_defaults(self):
        args = self._parse("clip.mp4")
        self.assertIsNone(args.resolution)
        self.assertIsNone(args.fps)
        self.assertIsNone(args.format)
        self.assertEqual(args.quality, 23)
        self.assertIsNone(args.output)
        self.assertFalse(args.dryrun)
        self.assertFalse(args.overwrite)

    def test_resolution_flag(self):
        args = self._parse("clip.mp4", "--resolution", "720p")
        self.assertEqual(args.resolution, "720p")

    def test_fps_flag(self):
        args = self._parse("clip.mp4", "--fps", "24")
        self.assertEqual(args.fps, 24)

    def test_format_flag(self):
        args = self._parse("clip.mp4", "--format", "mov")
        self.assertEqual(args.format, "mov")

    def test_quality_flag(self):
        args = self._parse("clip.mp4", "--resolution", "720p", "--quality", "18")
        self.assertEqual(args.quality, 18)

    def test_output_flag(self):
        args = self._parse("clip.mp4", "--resolution", "720p", "--output", "/out")
        self.assertEqual(args.output, "/out")

    def test_dryrun_flag(self):
        args = self._parse("clip.mp4", "--resolution", "720p", "--dryrun")
        self.assertTrue(args.dryrun)

    def test_overwrite_flag(self):
        args = self._parse("clip.mp4", "--resolution", "720p", "--overwrite")
        self.assertTrue(args.overwrite)

    def test_multiple_files(self):
        args = self._parse("a.mp4", "b.mp4", "--resolution", "720p")
        self.assertEqual(args.paths, ["a.mp4", "b.mp4"])

    def test_short_resolution_flag(self):
        args = self._parse("clip.mp4", "-r", "1080p")
        self.assertEqual(args.resolution, "1080p")

    def test_invalid_resolution_rejected_by_argparse(self):
        with self.assertRaises(SystemExit):
            self._parse("clip.mp4", "--resolution", "480p")

    def test_invalid_fps_rejected_by_argparse(self):
        with self.assertRaises(SystemExit):
            self._parse("clip.mp4", "--fps", "25")

    def test_invalid_format_rejected_by_argparse(self):
        with self.assertRaises(SystemExit):
            self._parse("clip.mp4", "--format", "mkv")


# ── main() — argument / config errors (no ffmpeg needed) ─────────────────────

class TestMainNoFiles(unittest.TestCase):

    def test_no_files_exits_nonzero(self):
        with self.assertRaises(SystemExit) as cm:
            main(["--resolution", "720p"])
        self.assertNotEqual(cm.exception.code, 0)


class TestMainNoAction(unittest.TestCase):

    def test_no_action_returns_1(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "clip.mp4"
            f.write_bytes(b"data")
            result = main([str(f)])
        self.assertEqual(result, 1)


class TestMainInvalidOutputDir(unittest.TestCase):

    def test_nonexistent_output_dir_returns_1(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "clip.mp4"
            f.write_bytes(b"data")
            result = main([
                "--resolution", "pal",
                "--output", "/no/such/dir_transcode_test_xyz",
                str(f),
            ])
        self.assertEqual(result, 1)


# ── main() — real ffmpeg integration ─────────────────────────────────────────

class TestMainReal(unittest.TestCase):
    """Integration tests that actually invoke ffmpeg via main()."""

    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.tmp = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        self.src = self.tmp / "clip.mp4"
        make_test_clip(self.src)

    def test_resolution_transcode_returns_zero(self):
        with patch("builtins.print"):
            result = main(["--resolution", "pal", "--overwrite", str(self.src)])
        self.assertEqual(result, 0)

    def test_output_file_created_with_correct_name(self):
        with patch("builtins.print"):
            main(["--resolution", "pal", "--overwrite", str(self.src)])
        expected = self.tmp / "clip_pal.mp4"
        self.assertTrue(expected.exists(), msg=f"{expected} was not created")

    def test_dryrun_returns_zero_without_output(self):
        with patch("builtins.print"):
            result = main(["--resolution", "pal", "--dryrun", str(self.src)])
        self.assertEqual(result, 0)
        self.assertFalse((self.tmp / "clip_pal.mp4").exists())

    def test_fps_change_creates_output(self):
        with patch("builtins.print"):
            result = main(["--fps", "24", "--overwrite", str(self.src)])
        self.assertEqual(result, 0)
        self.assertTrue((self.tmp / "clip_24fps.mp4").exists())

    def test_resolution_and_fps_combined(self):
        with patch("builtins.print"):
            result = main(["--resolution", "pal", "--fps", "24", "--overwrite", str(self.src)])
        self.assertEqual(result, 0)
        self.assertTrue((self.tmp / "clip_pal_24fps.mp4").exists())

    def test_output_to_separate_dir(self):
        out_dir = self.tmp / "out"
        out_dir.mkdir()
        with patch("builtins.print"):
            result = main([
                "--resolution", "pal", "--overwrite",
                "--output", str(out_dir),
                str(self.src),
            ])
        self.assertEqual(result, 0)
        self.assertTrue((out_dir / "clip_pal.mp4").exists())

    def test_multiple_files_all_transcoded(self):
        src2 = self.tmp / "clip2.mp4"
        make_test_clip(src2)
        with patch("builtins.print"):
            result = main(["--resolution", "pal", "--overwrite", str(self.src), str(src2)])
        self.assertEqual(result, 0)
        self.assertTrue((self.tmp / "clip_pal.mp4").exists())
        self.assertTrue((self.tmp / "clip2_pal.mp4").exists())

    def test_missing_file_skipped_no_failure(self):
        missing = self.tmp / "no_such.mp4"
        with patch("builtins.print"):
            result = main(["--resolution", "pal", str(missing)])
        self.assertEqual(result, 0)

    def test_existing_output_skipped_without_overwrite(self):
        out = self.tmp / "clip_pal.mp4"
        out.write_bytes(b"sentinel")
        with patch("builtins.print"):
            result = main(["--resolution", "pal", str(self.src)])
        self.assertEqual(result, 0)
        # Sentinel content unchanged — ffmpeg was not run on it
        self.assertEqual(out.read_bytes(), b"sentinel")
