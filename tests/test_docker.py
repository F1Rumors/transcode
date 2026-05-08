"""
Integration tests that build and exercise the transcode Docker image.

These tests are skipped automatically when Docker is not available.
Run docker-build.ps1 before running this file for the first time, or
when the transcode code changes.

    python -m pytest transcode/tests/test_docker.py -v
"""

import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
DOCKER = shutil.which("docker")
IMAGE = "transcode:latest"

SCRIPT_DIR = Path(__file__).parent.parent


def docker_available() -> bool:
    if not DOCKER:
        return False
    try:
        r = subprocess.run([DOCKER, "info"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def image_exists() -> bool:
    r = subprocess.run(
        [DOCKER, "image", "inspect", IMAGE],
        capture_output=True,
    )
    return r.returncode == 0


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


def docker_run(*args: str, dir_mount: Path | None = None) -> subprocess.CompletedProcess:
    cmd = [DOCKER, "run", "--rm"]
    if dir_mount:
        cmd += ["--volume", f"{dir_mount}:/data"]
    cmd.append(IMAGE)
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True)


@unittest.skipUnless(docker_available(), "Docker not available or not running")
class TestDockerImageExists(unittest.TestCase):

    def test_image_present(self):
        """The transcode:latest image must exist. Run docker-build.ps1 if this fails."""
        self.assertTrue(
            image_exists(),
            "transcode:latest image not found — run transcode\\docker-build.ps1 first",
        )


@unittest.skipUnless(docker_available() and image_exists(), "Docker image not available")
class TestDockerHelp(unittest.TestCase):

    def test_help_exits_zero(self):
        r = docker_run("--help")
        self.assertEqual(r.returncode, 0, msg=r.stderr)

    def test_help_mentions_resolution(self):
        r = docker_run("--help")
        self.assertIn("resolution", r.stdout.lower())


@unittest.skipUnless(docker_available() and image_exists(), "Docker image not available")
class TestDockerTranscode(unittest.TestCase):

    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        self.tmp = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        self.src = self.tmp / "clip.mp4"
        make_test_clip(self.src)

    def test_resolution_transcode_creates_output(self):
        r = docker_run(
            "--resolution", "pal", "--overwrite",
            "/data/clip.mp4",
            dir_mount=self.tmp,
        )
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertTrue((self.tmp / "clip_pal.mp4").exists())

    def test_dryrun_exits_zero_no_output(self):
        r = docker_run(
            "--resolution", "pal", "--dryrun",
            "/data/clip.mp4",
            dir_mount=self.tmp,
        )
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertFalse((self.tmp / "clip_pal.mp4").exists())

    def test_original_detection_inside_docker(self):
        """When the original (unsuffixed) file exists, Docker should use it."""
        # Rename clip.mp4 → clip_720p.mp4 and put a fresh original as clip.mp4
        original = self.tmp / "clip.mp4"
        derived = self.tmp / "clip_720p.mp4"
        derived.write_bytes(original.read_bytes())
        # original stays as clip.mp4

        r = docker_run(
            "--resolution", "pal", "--overwrite",
            "/data/clip_720p.mp4",
            dir_mount=self.tmp,
        )
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        # Output should be clip_pal.mp4 (derived from original stem "clip")
        self.assertTrue(
            (self.tmp / "clip_pal.mp4").exists(),
            "Expected clip_pal.mp4 (from original clip.mp4), not clip_720p_pal.mp4",
        )

    def test_no_original_flag_uses_file_as_is(self):
        """--no-original should transcode the clicked file directly."""
        derived = self.tmp / "clip_720p.mp4"
        make_test_clip(derived)

        r = docker_run(
            "--resolution", "pal", "--no-original", "--overwrite",
            "/data/clip_720p.mp4",
            dir_mount=self.tmp,
        )
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertTrue(
            (self.tmp / "clip_720p_pal.mp4").exists(),
            "Expected clip_720p_pal.mp4 when --no-original is used",
        )

    def test_missing_file_exits_zero(self):
        """A missing file is skipped (not a hard error)."""
        r = docker_run(
            "--resolution", "pal",
            "/data/no_such_file.mp4",
            dir_mount=self.tmp,
        )
        self.assertEqual(r.returncode, 0, msg=r.stderr)

    def test_multiple_files_all_transcoded(self):
        src2 = self.tmp / "clip2.mp4"
        make_test_clip(src2)
        r = docker_run(
            "--resolution", "pal", "--overwrite",
            "/data/clip.mp4", "/data/clip2.mp4",
            dir_mount=self.tmp,
        )
        self.assertEqual(r.returncode, 0, msg=r.stderr)
        self.assertTrue((self.tmp / "clip_pal.mp4").exists())
        self.assertTrue((self.tmp / "clip2_pal.mp4").exists())


@unittest.skipUnless(docker_available(), "Docker not available or not running")
class TestDockerBuild(unittest.TestCase):
    """Verify the image can be rebuilt from source."""

    def test_build_succeeds(self):
        r = subprocess.run(
            [DOCKER, "build", "--tag", IMAGE, str(SCRIPT_DIR)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(r.returncode, 0, msg=r.stderr[-2000:])
