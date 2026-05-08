"""Tests for transcode.presets."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from transcode.presets import (
    RESOLUTIONS,
    VALID_FPS,
    VALID_FORMATS,
    Resolution,
    scale_filter,
)


class TestResolutions(unittest.TestCase):

    def test_all_six_presets_present(self):
        self.assertEqual(set(RESOLUTIONS), {"4k", "1080p", "1080i", "720p", "720i", "pal"})

    def test_4k_dimensions(self):
        r = RESOLUTIONS["4k"]
        self.assertEqual((r.width, r.height), (3840, 2160))
        self.assertFalse(r.interlaced)

    def test_1080i_is_interlaced(self):
        self.assertTrue(RESOLUTIONS["1080i"].interlaced)

    def test_1080p_is_progressive(self):
        self.assertFalse(RESOLUTIONS["1080p"].interlaced)

    def test_720i_is_interlaced(self):
        self.assertTrue(RESOLUTIONS["720i"].interlaced)

    def test_pal_dimensions(self):
        r = RESOLUTIONS["pal"]
        self.assertEqual((r.width, r.height), (720, 576))
        self.assertFalse(r.interlaced)

    def test_resolution_is_immutable(self):
        r = RESOLUTIONS["720p"]
        with self.assertRaises(Exception):
            r.width = 999  # type: ignore[misc]


class TestValidSets(unittest.TestCase):

    def test_valid_fps(self):
        self.assertEqual(VALID_FPS, frozenset({24, 30, 60}))

    def test_valid_formats(self):
        self.assertEqual(VALID_FORMATS, frozenset({"mp4", "mov", "avi"}))


class TestScaleFilter(unittest.TestCase):

    def test_progressive_filter_shape(self):
        r = RESOLUTIONS["720p"]
        f = scale_filter(r)
        self.assertIn("scale=1280:720", f)
        self.assertIn("pad=1280:720", f)
        self.assertIn("force_original_aspect_ratio=decrease", f)
        self.assertNotIn("setfield", f)

    def test_interlaced_appends_setfield(self):
        r = RESOLUTIONS["1080i"]
        f = scale_filter(r)
        self.assertTrue(f.endswith(",setfield=tff"))

    def test_progressive_no_setfield(self):
        for name, r in RESOLUTIONS.items():
            if not r.interlaced:
                self.assertNotIn("setfield", scale_filter(r), msg=name)
