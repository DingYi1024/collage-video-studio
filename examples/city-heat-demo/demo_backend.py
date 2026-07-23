#!/usr/bin/env python3
"""Deterministic offline adapter for the bundled city-heat demonstration."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


STYLE_SOURCES = {
    "style:map-print": "source-media/styles/map-print.png",
    "style:street-copy": "source-media/styles/street-copy.png",
    "style:paper-lab": "source-media/styles/paper-lab.png",
}


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def resolve_input(project_dir: Path, job: dict[str, Any], role: str) -> Path:
    record = next((item for item in job["inputs"] if item.get("role") == role), None)
    if not record:
        raise RuntimeError(f"{job['id']}: missing {role!r} input")
    path = Path(record["path"])
    return path if path.is_absolute() else project_dir / path


def copy_file(source: Path, output: Path) -> Path:
    if not source.is_file():
        raise RuntimeError(f"bundled demo source is missing: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    return output


def animate_keyframe(job: dict[str, Any], project_dir: Path, output: Path) -> Path:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required to build the demo motion clips")
    source = resolve_input(project_dir, job, "keyframe")
    duration = float(job["params"].get("duration_s", 4))
    fps = int(job["params"].get("fps", 24))
    frames = max(1, round(duration * fps))
    last = max(1, frames - 1)
    beat_id = job.get("meta", {}).get("beat_id", "")

    expressions = {
        "b01": (
            f"1+0.065*on/{last}",
            "iw/2-(iw/zoom/2)",
            "ih/2-(ih/zoom/2)",
        ),
        "b02": (
            "1.07",
            f"(iw-iw/zoom)*on/{last}",
            "ih/2-(ih/zoom/2)",
        ),
        "b03": (
            "1.06",
            "iw/2-(iw/zoom/2)",
            f"(ih-ih/zoom)*(1-on/{last})",
        ),
        "b04": (
            f"1.08-0.08*on/{last}",
            "iw/2-(iw/zoom/2)",
            "ih/2-(ih/zoom/2)",
        ),
    }
    zoom, x_pos, y_pos = expressions.get(
        beat_id,
        (f"1+0.05*on/{last}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    )
    video_filter = (
        "scale=1440:2560:force_original_aspect_ratio=increase,"
        "crop=1440:2560,"
        f"zoompan=z='{zoom}':x='{x_pos}':y='{y_pos}':"
        f"d={frames}:s=720x1280:fps={fps},"
        "format=yuv420p"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-i", str(source), "-frames:v", str(frames),
        "-vf", video_filter, "-an", "-c:v", "libx264", "-preset", "medium",
        "-crf", "18", "-pix_fmt", "yuv420p", str(output),
    ])
    return output


def execute(job: dict[str, Any], project_dir: Path) -> Path:
    output = project_dir / job["output"]["path"]
    job_id = job["id"]
    kind = job["kind"]

    if kind in {"image_generation", "image_edit"}:
        if job_id in STYLE_SOURCES:
            source = project_dir / STYLE_SOURCES[job_id]
        elif job_id.startswith("image:"):
            source = project_dir / "source-media" / "keyframes" / f"{job_id.split(':', 1)[1]}.png"
        else:
            raise RuntimeError(f"no bundled image source for {job_id}")
        return copy_file(source, output)

    if kind in {"image_to_video", "video_edit"}:
        return animate_keyframe(job, project_dir, output)

    if kind == "speech":
        beat_id = job.get("meta", {}).get("beat_id")
        return copy_file(project_dir / "source-media" / "audio" / f"{beat_id}.wav", output)

    if kind == "music":
        return copy_file(project_dir / "source-media" / "audio" / "music-main.wav", output)

    raise RuntimeError(f"unsupported demo job kind: {kind}")
