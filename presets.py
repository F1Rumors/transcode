"""
presets.py — Resolution, FPS, and format constants for the transcode tool.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Resolution:
    name: str
    width: int
    height: int
    interlaced: bool


RESOLUTIONS: dict[str, Resolution] = {
    "4k":    Resolution("4k",    3840, 2160, False),
    "1080p": Resolution("1080p", 1920, 1080, False),
    "1080i": Resolution("1080i", 1920, 1080, True),
    "720p":  Resolution("720p",  1280, 720,  False),
    "720i":  Resolution("720i",  1280, 720,  True),
    "pal":   Resolution("pal",   720,  576,  False),
}

VALID_FPS: frozenset[int] = frozenset({24, 30, 60})
VALID_FORMATS: frozenset[str] = frozenset({"mp4", "mov", "avi"})


def scale_filter(res: Resolution) -> str:
    """Return an ffmpeg -vf expression that scales to *res* while preserving
    aspect ratio (letterbox / pillarbox as needed).

    For interlaced resolutions the ``setfield=tff`` filter is appended so the
    encoder receives properly-tagged fields.
    """
    w, h = res.width, res.height
    expr = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
    )
    if res.interlaced:
        expr += ",setfield=tff"
    return expr
