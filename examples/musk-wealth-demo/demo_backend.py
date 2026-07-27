#!/usr/bin/env python3
"""Deterministic layered adapter for the Musk wealth-path demonstration."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import layer_compositor


STYLE_SOURCES = {
    "style:archive-ledger": "source-media/styles/archive-ledger.png",
    "style:industrial-paper": "source-media/styles/industrial-paper.png",
    "style:market-poster": "source-media/styles/market-poster.png",
}


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


def copy_layer_pack(job: dict[str, Any], project_dir: Path, output: Path) -> Path:
    pack_id = job["id"].split(":", 1)[1]
    source_dir = project_dir / "source-media" / "layers" / pack_id
    if not (source_dir / "layers.json").is_file():
        raise RuntimeError(f"bundled layer pack is missing: {source_dir}")
    if output.parent.exists():
        shutil.rmtree(output.parent)
    shutil.copytree(source_dir, output.parent)
    return output


def execute(job: dict[str, Any], project_dir: Path) -> Path:
    output = project_dir / job["output"]["path"]
    job_id = job["id"]
    kind = job["kind"]
    if kind in {"image_generation", "image_edit"}:
        if job_id in STYLE_SOURCES:
            source = project_dir / STYLE_SOURCES[job_id]
        elif job_id.startswith("image:"):
            source = (
                project_dir / "source-media" / "keyframes"
                / f"{job_id.split(':', 1)[1]}.png"
            )
        else:
            raise RuntimeError(f"no bundled image source for {job_id}")
        return copy_file(source, output)
    if kind == "layer_package":
        return copy_layer_pack(job, project_dir, output)
    if kind == "layers_to_video":
        manifest = resolve_input(project_dir, job, "layer_manifest")
        return layer_compositor.render_manifest(manifest, output)
    if kind in {"image_to_video", "video_edit"}:
        raise RuntimeError("this demo requires the layered motion pipeline")
    if kind == "speech":
        copy_file(project_dir / "source-media" / "audio" / "main.wav", output)
        timing_source = (
            project_dir / "source-media" / "audio" / "main.timing.json"
        )
        timing_output = output.with_suffix(".timing.json")
        copy_file(timing_source, timing_output)
        return {
            "path": output,
            "metadata": {
                "timing_path": timing_output,
                "provider": "bundled-demonstration",
                "model": "continuous-edited-narration",
                "duration_s": None,
            },
        }
    if kind == "music":
        return copy_file(
            project_dir / "source-media" / "audio" / "music-main.wav", output
        )
    raise RuntimeError(f"unsupported demo job kind: {kind}")
