"""
transcoder.py — Core ffmpeg invocation logic for the transcode tool.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import TranscodeConfig
from .presets import Resolution, scale_filter

# Matches suffixes appended by this tool: _720p, _1080i, _24fps, _720p_24fps, etc.
_GENERATED_SUFFIX = re.compile(
    r'(_(?:4k|1080[pi]|720[pi]|pal)(_\d+fps)?|_\d+fps)$',
    re.IGNORECASE,
)


def find_source_path(path: Path) -> Path:
    """Return the best source for transcoding *path*.

    If *path* looks like a previously-transcoded file (its stem ends with a
    resolution or fps suffix added by this tool), and the inferred original
    exists in the same directory, return the original.  This prevents lossy
    re-encoding and avoids accidentally transcoding upward in resolution.
    """
    stem = path.stem
    stripped = _GENERATED_SUFFIX.sub("", stem)
    if stripped == stem:
        return path
    original = path.parent / f"{stripped}{path.suffix}"
    return original if original.exists() else path


# ── Output-path derivation ────────────────────────────────────────────────────

def derive_output_path(input_path: Path, cfg: TranscodeConfig) -> Path:
    """Return the output path for *input_path* given *cfg*.

    Suffix components are appended to the stem in the order they were
    requested: resolution first, fps second.  The extension reflects the
    requested format (or the source extension if none was requested).

        arials.mp4  --resolution 720p          → arials_720p.mp4
        arials.mp4  --fps 24                   → arials_24fps.mp4
        arials.mp4  --resolution 720p --fps 24 → arials_720p_24fps.mp4
        arials.mp4  --format mov               → arials.mov
        arials.mp4  --resolution 720p --format mov → arials_720p.mov
    """
    stem = input_path.stem
    src_ext = input_path.suffix.lstrip(".").lower()
    out_ext = cfg.fmt if cfg.fmt else src_ext

    if cfg.resolution:
        stem += f"_{cfg.resolution.name}"
    if cfg.fps is not None:
        stem += f"_{cfg.fps}fps"

    directory = cfg.output_dir if cfg.output_dir else input_path.parent
    return directory / f"{stem}.{out_ext}"


# ── ffmpeg command builder ────────────────────────────────────────────────────

def build_ffmpeg_command(
    input_path: Path,
    output_path: Path,
    cfg: TranscodeConfig,
) -> list[str]:
    """Build the ffmpeg argv list for this transcode operation."""
    src_ext = input_path.suffix.lstrip(".").lower()
    out_ext = output_path.suffix.lstrip(".").lower()

    cmd = [cfg.ffmpeg_executable, "-i", str(input_path)]

    if cfg.overwrite:
        cmd.append("-y")
    else:
        cmd.append("-n")  # never overwrite — let ffmpeg error on collision

    # ── Video stream ──────────────────────────────────────────────────────
    if cfg.resolution is None and cfg.fps is None and src_ext in {"mp4", "mov"} and out_ext in {"mp4", "mov"}:
        # Format-only change between mp4/mov — stream copy
        cmd += ["-c:v", "copy"]
    else:
        out_ext_is_avi = out_ext == "avi"
        codec = "mpeg4" if out_ext_is_avi else "libx264"
        cmd += ["-c:v", codec]

        vf_parts: list[str] = []
        if cfg.resolution:
            vf_parts.append(scale_filter(cfg.resolution))
        if vf_parts:
            cmd += ["-vf", ",".join(vf_parts)]

        if codec == "libx264":
            cmd += ["-crf", str(cfg.quality), "-preset", "medium"]
            if cfg.resolution and cfg.resolution.interlaced:
                cmd += ["-x264opts", "interlaced=1:tff=1"]
        else:
            cmd += ["-q:v", str(cfg.quality)]
            if cfg.resolution and cfg.resolution.interlaced:
                cmd += ["-flags", "+ildct+ilme"]

    if cfg.fps is not None:
        cmd += ["-r", str(cfg.fps)]

    # ── Audio stream ──────────────────────────────────────────────────────
    if out_ext == "avi":
        cmd += ["-c:a", "libmp3lame", "-ab", "192k"]
    else:
        cmd += ["-c:a", "copy"]

    cmd.append(str(output_path))
    return cmd


# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class TranscodeResult:
    input_path: Path
    output_path: Path
    skipped: bool = False
    skip_reason: str = ""
    returncode: int = 0
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.skipped or self.returncode == 0


# ── Per-file entry point ──────────────────────────────────────────────────────

def transcode_file(input_path: Path, cfg: TranscodeConfig) -> TranscodeResult:
    """Transcode a single file; return a ``TranscodeResult``."""
    input_path = input_path.resolve()

    if cfg.use_original:
        input_path = find_source_path(input_path).resolve()

    output_path = derive_output_path(input_path, cfg)

    # Skip if output == input (e.g., --format mp4 on an mp4 with no other changes)
    if output_path.resolve() == input_path:
        return TranscodeResult(
            input_path=input_path,
            output_path=output_path,
            skipped=True,
            skip_reason="output path is the same as input — nothing to do",
        )

    if output_path.exists() and not cfg.overwrite and not cfg.dryrun:
        return TranscodeResult(
            input_path=input_path,
            output_path=output_path,
            skipped=True,
            skip_reason=f"output already exists: {output_path} (use --overwrite to replace)",
        )

    cmd = build_ffmpeg_command(input_path, output_path, cfg)

    if cfg.dryrun:
        return TranscodeResult(
            input_path=input_path,
            output_path=output_path,
            skipped=True,
            skip_reason="dryrun: would run: " + " ".join(cmd),
        )

    # stdout=DEVNULL silences ffmpeg's occasional stdout chatter.
    # stderr is inherited so ffmpeg's live progress line streams to the terminal.
    result = subprocess.run(cmd, stdout=subprocess.DEVNULL)
    return TranscodeResult(
        input_path=input_path,
        output_path=output_path,
        returncode=result.returncode,
        stderr="",
    )


# ── Batch entry point ─────────────────────────────────────────────────────────

def transcode_all(
    paths: list[Path],
    cfg: TranscodeConfig,
) -> list[TranscodeResult]:
    """Transcode each path in *paths*; print status; return all results."""
    results: list[TranscodeResult] = []
    for path in paths:
        if not path.exists():
            print(f"file not found: {path}")
            results.append(TranscodeResult(
                input_path=path,
                output_path=path,
                skipped=True,
                skip_reason="file not found",
            ))
            continue

        r = transcode_file(path, cfg)
        results.append(r)

        if r.skipped:
            print(f"skipped  {path.name}: {r.skip_reason}")
        elif r.ok:
            print(f"ok       {path.name} -> {r.output_path.name}")
        else:
            print(f"FAILED   {path.name} (exit {r.returncode})")
            if r.stderr:
                for line in r.stderr.splitlines()[-10:]:
                    print(f"         {line}")

    return results
