#!/usr/bin/env python3
"""Offline test adapter. Never use its placeholder media for a real deliverable."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def color_for(value: str) -> tuple[int, int, int]:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return tuple(55 + byte % 155 for byte in digest[:3])


def run(args: list[str]) -> None:
    subprocess.run(args, check=True, capture_output=True)


def resolve_input(project_dir: Path, job: dict[str, Any], role: str) -> Path | None:
    record = next((item for item in job.get("inputs", []) if item.get("role") == role), None)
    if not record or not record.get("path"):
        return None
    path = Path(record["path"])
    return path if path.is_absolute() else project_dir / path


def make_image(job: dict[str, Any], output: Path) -> None:
    aspect = job.get("params", {}).get("aspect", "9:16")
    dims = {"16:9": (640, 360), "9:16": (360, 640), "1:1": (512, 512),
            "4:5": (432, 540), "3:4": (450, 600), "4:3": (600, 450)}
    width, height = dims.get(aspect, (360, 640))
    base = Image.new("RGB", (width, height), color_for(job["id"]))
    draw = ImageDraw.Draw(base)
    font = ImageFont.load_default()
    margin = max(18, width // 18)
    draw.rectangle((margin, margin, width - margin, height - margin),
                   outline=(245, 238, 220), width=max(3, width // 90))
    draw.text((margin * 2, margin * 2), "OFFLINE TEST MEDIA", fill="white", font=font)
    draw.text((margin * 2, margin * 3), job["id"], fill="white", font=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    base.save(output)


def make_video(job: dict[str, Any], project_dir: Path, output: Path) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required by the offline test adapter")
    duration = max(0.25, float(job.get("params", {}).get("duration_s", 1)))
    source = resolve_input(project_dir, job, "keyframe")
    output.parent.mkdir(parents=True, exist_ok=True)
    if source and source.is_file():
        run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-loop", "1",
            "-i", str(source), "-t", f"{duration:.3f}",
            "-vf", "scale=360:640:force_original_aspect_ratio=decrease,"
                   "pad=360:640:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-r", "24", "-c:v", "libx264", str(output),
        ])
        return
    source = resolve_input(project_dir, job, "source")
    if source and source.is_file():
        range_s = next(
            (item.get("range_s") for item in job.get("inputs", [])
             if item.get("role") == "source"), None
        )
        start = float(range_s[0]) if range_s and range_s[0] is not None else 0.0
        run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{duration:.3f}",
            "-vf", "scale=360:640:force_original_aspect_ratio=decrease,"
                   "pad=360:640:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-an", "-r", "24", "-c:v", "libx264", str(output),
        ])
        return
    color = "#%02x%02x%02x" % color_for(job["id"])
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
        "-i", f"color=c={color}:s=360x640:r=24:d={duration:.3f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output),
    ])


def make_audio(job: dict[str, Any], output: Path) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required by the offline test adapter")
    duration = max(0.5, float(job.get("params", {}).get("duration_s", 1)))
    frequency = 330 if job["kind"] == "speech" else 165
    output.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
        "-i", f"sine=frequency={frequency}:duration={duration:.3f}:sample_rate=48000",
        "-c:a", "pcm_s16le", str(output),
    ])


def execute(job: dict[str, Any], project_dir: Path) -> Path:
    output = project_dir / job["output"]["path"]
    if job["kind"] in {"image_generation", "image_edit"}:
        make_image(job, output)
    elif job["kind"] in {"image_to_video", "video_edit"}:
        make_video(job, project_dir, output)
    elif job["kind"] in {"speech", "music"}:
        make_audio(job, output)
    else:
        raise RuntimeError(f"unsupported test job kind: {job['kind']}")
    return output
