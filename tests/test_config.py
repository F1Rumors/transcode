"""Tests for transcode.config."""

import os
import sys
import tempfile
import unittest
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from transcode.config import TranscodeConfig
from transcode.presets import RESOLUTIONS


def _args(**kwargs):
    """Return a minimal Namespace with all expected attributes."""
    defaults = dict(
        resolution=None,
        fps=None,
        format=None,
        quality=23,
        output=None,
        dryrun=False,
        overwrite=False,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestTranscodeConfigFromArgs(unittest.TestCase):

    def test_defaults_produce_none_fields(self):
        cfg = TranscodeConfig.from_args(_args())
        self.assertIsNone(cfg.resolution)
        self.assertIsNone(cfg.fps)
        self.assertIsNone(cfg.fmt)
        self.assertEqual(cfg.quality, 23)
        self.assertFalse(cfg.dryrun)
        self.assertFalse(cfg.overwrite)

    def test_resolution_parsed(self):
        cfg = TranscodeConfig.from_args(_args(resolution="720p"))
        self.assertEqual(cfg.resolution, RESOLUTIONS["720p"])

    def test_resolution_case_insensitive(self):
        cfg = TranscodeConfig.from_args(_args(resolution="1080P"))
        self.assertEqual(cfg.resolution, RESOLUTIONS["1080p"])

    def test_invalid_resolution_raises(self):
        with self.assertRaises(ValueError):
            TranscodeConfig.from_args(_args(resolution="480p"))

    def test_fps_parsed(self):
        cfg = TranscodeConfig.from_args(_args(fps=24))
        self.assertEqual(cfg.fps, 24)

    def test_invalid_fps_raises(self):
        with self.assertRaises(ValueError):
            TranscodeConfig.from_args(_args(fps=25))

    def test_format_parsed(self):
        cfg = TranscodeConfig.from_args(_args(format="mov"))
        self.assertEqual(cfg.fmt, "mov")

    def test_format_strips_leading_dot(self):
        cfg = TranscodeConfig.from_args(_args(format=".mp4"))
        self.assertEqual(cfg.fmt, "mp4")

    def test_invalid_format_raises(self):
        with self.assertRaises(ValueError):
            TranscodeConfig.from_args(_args(format="mkv"))

    def test_output_dir_parsed(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = TranscodeConfig.from_args(_args(resolution="720p", output=d))
            self.assertEqual(cfg.output_dir, Path(d))

    def test_dryrun_flag(self):
        cfg = TranscodeConfig.from_args(_args(resolution="720p", dryrun=True))
        self.assertTrue(cfg.dryrun)

    def test_overwrite_flag(self):
        cfg = TranscodeConfig.from_args(_args(resolution="720p", overwrite=True))
        self.assertTrue(cfg.overwrite)


class TestTranscodeConfigValidate(unittest.TestCase):

    def test_no_action_raises(self):
        cfg = TranscodeConfig()
        with self.assertRaises(ValueError, msg="Nothing to do"):
            cfg.validate()

    def test_resolution_only_is_valid(self):
        cfg = TranscodeConfig(resolution=RESOLUTIONS["720p"])
        cfg.validate()  # should not raise

    def test_fps_only_is_valid(self):
        cfg = TranscodeConfig(fps=24)
        cfg.validate()

    def test_format_only_is_valid(self):
        cfg = TranscodeConfig(fmt="mov")
        cfg.validate()

    def test_nonexistent_output_dir_raises(self):
        cfg = TranscodeConfig(
            resolution=RESOLUTIONS["720p"],
            output_dir=Path("/no/such/directory_transcode_test_xyz"),
        )
        with self.assertRaises(ValueError):
            cfg.validate()

    def test_quality_out_of_range_raises(self):
        cfg = TranscodeConfig(resolution=RESOLUTIONS["720p"], quality=0)
        with self.assertRaises(ValueError):
            cfg.validate()

        cfg2 = TranscodeConfig(resolution=RESOLUTIONS["720p"], quality=52)
        with self.assertRaises(ValueError):
            cfg2.validate()

    def test_quality_boundary_values_ok(self):
        for q in (1, 51):
            cfg = TranscodeConfig(resolution=RESOLUTIONS["720p"], quality=q)
            cfg.validate()  # should not raise
