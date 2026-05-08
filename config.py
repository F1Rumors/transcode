"""
config.py — TranscodeConfig dataclass for the transcode tool.
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .presets import RESOLUTIONS, VALID_FPS, VALID_FORMATS, Resolution


def _find_ffmpeg() -> str:
    """Return the path to an ffmpeg executable.

    Preference order:
    1. System ffmpeg on PATH (covers the Synology NAS at /bin/ffmpeg and any
       desktop with ffmpeg installed normally).
    2. The binary bundled by imageio-ffmpeg (Windows dev machines where ffmpeg
       is not installed system-wide).
    """
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass
    return "ffmpeg"  # let the OS error surface at runtime


@dataclass
class TranscodeConfig:
    resolution: Optional[Resolution] = None   # None = keep source
    fps: Optional[int] = None                  # None = keep source
    fmt: Optional[str] = None                  # None = keep source
    quality: int = 23                          # CRF for libx264/libx265
    output_dir: Optional[Path] = None         # None = same dir as input
    dryrun: bool = False
    overwrite: bool = False
    use_original: bool = True   # seek unsuffixed source file to avoid re-encoding
    ffmpeg_executable: str = "ffmpeg"

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "TranscodeConfig":
        resolution: Optional[Resolution] = None
        if args.resolution:
            key = args.resolution.lower()
            if key not in RESOLUTIONS:
                raise ValueError(
                    f"Unknown resolution {args.resolution!r}. "
                    f"Valid: {', '.join(sorted(RESOLUTIONS))}"
                )
            resolution = RESOLUTIONS[key]

        fps: Optional[int] = None
        if args.fps is not None:
            fps = int(args.fps)
            if fps not in VALID_FPS:
                raise ValueError(
                    f"Invalid fps {fps}. Valid: {', '.join(str(f) for f in sorted(VALID_FPS))}"
                )

        fmt: Optional[str] = None
        if args.format:
            fmt = args.format.lower().lstrip(".")
            if fmt not in VALID_FORMATS:
                raise ValueError(
                    f"Unknown format {args.format!r}. "
                    f"Valid: {', '.join(sorted(VALID_FORMATS))}"
                )

        output_dir: Optional[Path] = None
        if args.output:
            output_dir = Path(args.output)

        ffmpeg_executable = _find_ffmpeg()

        return cls(
            resolution=resolution,
            fps=fps,
            fmt=fmt,
            quality=int(args.quality),
            output_dir=output_dir,
            dryrun=args.dryrun,
            overwrite=args.overwrite,
            use_original=not getattr(args, "no_original", False),
            ffmpeg_executable=ffmpeg_executable,
        )

    # ── Validation ────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Raise ValueError if no transcode action was requested."""
        if self.resolution is None and self.fps is None and self.fmt is None:
            raise ValueError(
                "Nothing to do: specify at least one of "
                "--resolution, --fps, or --format"
            )
        if self.output_dir is not None and not self.output_dir.is_dir():
            raise ValueError(
                f"Output directory does not exist: {self.output_dir}"
            )
        if not (1 <= self.quality <= 51):
            raise ValueError(f"Quality (CRF) must be 1–51, got {self.quality}")
