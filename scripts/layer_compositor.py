#!/usr/bin/env python3
"""Validate and render deterministic multi-layer paper-collage motion manifests."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image


TRANSFORM_KEYS = ("x", "y", "scale", "scale_x", "scale_y", "rotation", "opacity")
DEFAULT_TRANSFORM = {
    "x": 0.0,
    "y": 0.0,
    "scale": 1.0,
    "scale_x": 1.0,
    "scale_y": 1.0,
    "rotation": 0.0,
    "opacity": 1.0,
}


class LayerError(RuntimeError):
    pass


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LayerError(f"cannot read layer manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LayerError("layer manifest must be a JSON object")
    return value


def layer_is_animated(layer: dict[str, Any]) -> bool:
    keyframes = layer.get("keyframes", [])
    if len(keyframes) < 2:
        return False
    first = {key: float(keyframes[0].get(key, DEFAULT_TRANSFORM[key]))
             for key in TRANSFORM_KEYS}
    return any(
        any(abs(float(frame.get(key, DEFAULT_TRANSFORM[key])) - first[key]) > 1e-6
            for key in TRANSFORM_KEYS)
        for frame in keyframes[1:]
    )


def validate_manifest(path: Path) -> tuple[list[str], list[str], dict[str, int]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        manifest = load_manifest(path)
    except LayerError as exc:
        return [str(exc)], warnings, {"layers": 0, "animated_layers": 0}

    canvas = manifest.get("canvas", {})
    for key in ("width", "height", "fps", "duration_s"):
        try:
            if float(canvas.get(key, 0)) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"canvas.{key} must be positive")

    layers = manifest.get("layers")
    if not isinstance(layers, list) or not layers:
        return errors + ["layers must be a non-empty array"], warnings, {
            "layers": 0, "animated_layers": 0,
        }

    ids: set[str] = set()
    animated = 0
    for index, layer in enumerate(layers, 1):
        layer_id = str(layer.get("id", "")).strip()
        if not layer_id:
            errors.append(f"layer[{index}] has no id")
        elif layer_id in ids:
            errors.append(f"duplicate layer id: {layer_id}")
        ids.add(layer_id)
        source = path.parent / str(layer.get("path", ""))
        if not source.is_file() or source.stat().st_size <= 0:
            errors.append(f"{layer_id or index}: missing layer image {source}")
        keyframes = layer.get("keyframes")
        if not isinstance(keyframes, list) or not keyframes:
            errors.append(f"{layer_id or index}: keyframes must be non-empty")
            continue
        times: list[float] = []
        for frame in keyframes:
            try:
                times.append(float(frame["t"]))
            except (KeyError, TypeError, ValueError):
                errors.append(f"{layer_id or index}: every keyframe needs numeric t")
                break
        if times and times != sorted(times):
            errors.append(f"{layer_id or index}: keyframe times must be sorted")
        if layer_is_animated(layer):
            animated += 1

    quality = manifest.get("quality", {})
    min_layers = int(quality.get("min_layers", 4))
    min_animated = int(quality.get("min_animated_layers", 3))
    if len(layers) < min_layers:
        errors.append(f"layer count {len(layers)} is below required {min_layers}")
    if animated < min_animated:
        errors.append(f"animated layer count {animated} is below required {min_animated}")
    if len({layer.get("z", 0) for layer in layers}) < min(3, len(layers)):
        warnings.append("fewer than three distinct depth planes")
    return errors, warnings, {"layers": len(layers), "animated_layers": animated}


def smoothstep(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * value * (3.0 - 2.0 * value)


def transform_at(layer: dict[str, Any], time_s: float) -> dict[str, float]:
    frames = layer["keyframes"]
    before = frames[0]
    after = frames[-1]
    for index in range(1, len(frames)):
        if time_s <= float(frames[index]["t"]):
            before, after = frames[index - 1], frames[index]
            break
    start = float(before["t"])
    end = float(after["t"])
    progress = 0.0 if end <= start else (time_s - start) / (end - start)
    if layer.get("easing", "smoothstep") == "smoothstep":
        progress = smoothstep(progress)
    result: dict[str, float] = {}
    for key in TRANSFORM_KEYS:
        left = float(before.get(key, DEFAULT_TRANSFORM[key]))
        right = float(after.get(key, DEFAULT_TRANSFORM[key]))
        result[key] = left + (right - left) * progress
    return result


def apply_transform(source: Image.Image, values: dict[str, float],
                    canvas: tuple[int, int]) -> tuple[Image.Image, tuple[int, int]]:
    bbox = source.getbbox()
    if bbox is None:
        return Image.new("RGBA", (1, 1)), (0, 0)
    crop = source.crop(bbox)
    scale = max(0.01, values["scale"])
    scale_x = max(0.01, values["scale_x"] * scale)
    scale_y = max(0.01, values["scale_y"] * scale)
    width = max(1, round(crop.width * scale_x))
    height = max(1, round(crop.height * scale_y))
    if (width, height) != crop.size:
        crop = crop.resize((width, height), Image.Resampling.LANCZOS)
    rotation = values["rotation"]
    if abs(rotation) > 1e-6:
        crop = crop.rotate(-rotation, resample=Image.Resampling.BICUBIC, expand=True)
    opacity = min(1.0, max(0.0, values["opacity"]))
    if opacity < 0.999:
        alpha = crop.getchannel("A").point(lambda value: round(value * opacity))
        crop.putalpha(alpha)
    center_x = (bbox[0] + bbox[2]) / 2 + values["x"]
    center_y = (bbox[1] + bbox[3]) / 2 + values["y"]
    position = (round(center_x - crop.width / 2), round(center_y - crop.height / 2))
    return crop, position


def render_frame(manifest_path: Path, time_s: float,
                 loaded: list[tuple[dict[str, Any], Image.Image]] | None = None,
                 manifest: dict[str, Any] | None = None) -> Image.Image:
    manifest = manifest or load_manifest(manifest_path)
    canvas_data = manifest["canvas"]
    canvas = (int(canvas_data["width"]), int(canvas_data["height"]))
    frame = Image.new("RGBA", canvas, (0, 0, 0, 0))
    if loaded is None:
        loaded = [
            (layer, Image.open(manifest_path.parent / layer["path"]).convert("RGBA"))
            for layer in sorted(manifest["layers"], key=lambda item: float(item.get("z", 0)))
        ]
    for layer, source in loaded:
        transformed, position = apply_transform(source, transform_at(layer, time_s), canvas)
        frame.alpha_composite(transformed, position)
    return frame


def render_manifest(manifest_path: Path, output: Path) -> Path:
    errors, warnings, stats = validate_manifest(manifest_path)
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        raise LayerError("invalid layer manifest:\n- " + "\n- ".join(errors))
    if not shutil.which("ffmpeg"):
        raise LayerError("ffmpeg is required")
    manifest = load_manifest(manifest_path)
    canvas = manifest["canvas"]
    width, height = int(canvas["width"]), int(canvas["height"])
    fps = int(canvas["fps"])
    duration = float(canvas["duration_s"])
    frame_count = max(1, round(duration * fps))
    loaded = [
        (layer, Image.open(manifest_path.parent / layer["path"]).convert("RGBA"))
        for layer in sorted(manifest["layers"], key=lambda item: float(item.get("z", 0)))
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{width}x{height}",
        "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264", "-preset", "medium",
        "-crf", "18", "-pix_fmt", "yuv420p", str(output),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame_index in range(frame_count):
            time_s = frame_index / fps
            process.stdin.write(
                render_frame(manifest_path, time_s, loaded, manifest).tobytes()
            )
        process.stdin.close()
        return_code = process.wait()
    except Exception:
        process.kill()
        raise
    if return_code:
        raise LayerError(f"ffmpeg failed with exit code {return_code}")
    if not output.is_file() or output.stat().st_size <= 0:
        raise LayerError("layer render produced no output")
    print(
        f"layer render: {output} · {stats['layers']} layers · "
        f"{stats['animated_layers']} animated · {duration:.2f}s"
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--output")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    manifest = Path(args.manifest).resolve()
    try:
        errors, warnings, stats = validate_manifest(manifest)
        for warning in warnings:
            print(f"WARNING: {warning}")
        for error in errors:
            print(f"ERROR: {error}")
        print(f"layers={stats['layers']} animated={stats['animated_layers']}")
        if errors or args.validate:
            return 1 if errors else 0
        output = Path(args.output) if args.output else manifest.with_suffix(".mp4")
        render_manifest(manifest, output.resolve())
        return 0
    except (LayerError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
