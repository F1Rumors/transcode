"""
cli.py — Command-line entry point for the transcode tool.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import TranscodeConfig
from .presets import RESOLUTIONS, VALID_FPS, VALID_FORMATS
from .transcoder import transcode_all


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="transcode",
        description="Transcode video files to standard resolutions, frame rates, and formats.",
    )
    p.add_argument(
        "paths",
        nargs="*",
        metavar="FILE",
        help="Input video file(s) to transcode.",
    )
    p.add_argument(
        "--resolution", "-r",
        metavar="RES",
        choices=sorted(RESOLUTIONS),
        help=f"Target resolution: {', '.join(sorted(RESOLUTIONS))}.",
    )
    p.add_argument(
        "--fps", "-f",
        type=int,
        metavar="FPS",
        choices=sorted(VALID_FPS),
        help=f"Target frame rate: {', '.join(str(f) for f in sorted(VALID_FPS))}.",
    )
    p.add_argument(
        "--format",
        metavar="FMT",
        choices=sorted(VALID_FORMATS),
        help=f"Output container format: {', '.join(sorted(VALID_FORMATS))}.",
    )
    p.add_argument(
        "--quality", "-q",
        type=int,
        default=23,
        metavar="CRF",
        help="Encoder quality (CRF, 1–51; lower = better quality). Default: 23.",
    )
    p.add_argument(
        "--output", "-o",
        metavar="DIR",
        help="Write output files to DIR instead of alongside the source.",
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files.",
    )
    p.add_argument(
        "--dryrun",
        action="store_true",
        help="Print what would be done without running ffmpeg.",
    )
    p.add_argument(
        "--no-original",
        action="store_true",
        dest="no_original",
        help="Transcode the file as-is; do not seek an unsuffixed original.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.paths:
        parser.error("no input files specified")

    try:
        cfg = TranscodeConfig.from_args(args)
        cfg.validate()
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    paths = [Path(p) for p in args.paths]
    results = transcode_all(paths, cfg)

    failures = [r for r in results if not r.ok]
    return len(failures) if failures else 0


if __name__ == "__main__":
    sys.exit(main())
