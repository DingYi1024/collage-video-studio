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
EASINGS = {
    "linear",
    "smoothstep",
    "smootherstep",
    "ease-in",
    "ease-out",
    "ease-in-out",
    "catmull-rom",
}
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
    if len(layer.get("sprites", [])) > 1 or layer.get("motion_path"):
        return True
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
    for key, minimum, maximum in (
        ("oversample", 1, 4),
        ("motion_blur_samples", 1, 4),
    ):
        try:
            value = int(canvas.get(key, 1))
            if value < minimum or value > maximum:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"canvas.{key} must be an integer from {minimum} to {maximum}")
    try:
        shutter = float(canvas.get("shutter", 0.5))
        if shutter < 0 or shutter > 1:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("canvas.shutter must be from 0 to 1")

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
        sprites = layer.get("sprites", [])
        if sprites and not isinstance(sprites, list):
            errors.append(f"{layer_id or index}: sprites must be an array")
            sprites = []
        sprite_times: list[float] = []
        for sprite_index, sprite in enumerate(sprites, 1):
            sprite_source = path.parent / str(sprite.get("path", ""))
            if not sprite_source.is_file() or sprite_source.stat().st_size <= 0:
                errors.append(
                    f"{layer_id or index}: missing sprite image {sprite_source}"
                )
            try:
                sprite_times.append(float(sprite["t"]))
            except (KeyError, TypeError, ValueError):
                errors.append(
                    f"{layer_id or index}: sprite[{sprite_index}] needs numeric t"
                )
        if sprite_times and sprite_times != sorted(sprite_times):
            errors.append(f"{layer_id or index}: sprite times must be sorted")
        if layer.get("sprite_loop") and sprites:
            try:
                sprite_duration = float(layer.get("sprite_duration_s", 0))
                if sprite_duration <= sprite_times[-1]:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append(
                    f"{layer_id or index}: sprite loop duration must exceed last sprite t"
                )
        motion_path = layer.get("motion_path")
        if motion_path is not None:
            points = motion_path.get("points", []) if isinstance(motion_path, dict) else []
            if (
                len(points) != 4
                or any(
                    not isinstance(point, list)
                    or len(point) != 2
                    for point in points
                )
            ):
                errors.append(
                    f"{layer_id or index}: motion_path.points needs four [x, y] pairs"
                )
            try:
                start_s = float(motion_path.get("start_s", 0))
                end_s = float(motion_path["end_s"])
                if end_s <= start_s:
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                errors.append(
                    f"{layer_id or index}: motion_path needs end_s greater than start_s"
                )
        pivot = layer.get("pivot")
        if pivot is not None and (
            not isinstance(pivot, list)
            or len(pivot) != 2
        ):
            errors.append(f"{layer_id or index}: pivot must be [canvas_x, canvas_y]")
        anchor = layer.get("anchor")
        if anchor is not None and (
            not isinstance(anchor, list)
            or len(anchor) != 2
        ):
            errors.append(f"{layer_id or index}: anchor must be [x_ratio, y_ratio]")
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
        easing = str(layer.get("easing", "smoothstep"))
        if easing not in EASINGS:
            errors.append(
                f"{layer_id or index}: unsupported easing {easing!r}; "
                f"choose from {', '.join(sorted(EASINGS))}"
            )
        if layer.get("loop") and times and times[-1] <= times[0]:
            errors.append(f"{layer_id or index}: loop needs a positive keyframe span")
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


def smootherstep(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * value * value * (value * (value * 6.0 - 15.0) + 10.0)


def ease(value: float, name: str) -> float:
    value = min(1.0, max(0.0, value))
    if name == "linear" or name == "catmull-rom":
        return value
    if name == "smoothstep":
        return smoothstep(value)
    if name == "smootherstep":
        return smootherstep(value)
    if name == "ease-in":
        return value * value * value
    if name == "ease-out":
        return 1.0 - (1.0 - value) ** 3
    if name == "ease-in-out":
        return (
            4.0 * value * value * value
            if value < 0.5
            else 1.0 - ((-2.0 * value + 2.0) ** 3) / 2.0
        )
    return value


def frame_value(frame: dict[str, Any], key: str) -> float:
    return float(frame.get(key, DEFAULT_TRANSFORM[key]))


def catmull_rom(left_outer: float, left: float, right: float,
                right_outer: float, value: float) -> float:
    value_2 = value * value
    value_3 = value_2 * value
    return 0.5 * (
        2.0 * left
        + (-left_outer + right) * value
        + (2.0 * left_outer - 5.0 * left + 4.0 * right - right_outer) * value_2
        + (-left_outer + 3.0 * left - 3.0 * right + right_outer) * value_3
    )


def timeline_time(layer: dict[str, Any], time_s: float) -> float:
    frames = layer["keyframes"]
    if not layer.get("loop"):
        return time_s
    start = float(frames[0]["t"])
    end = float(frames[-1]["t"])
    span = end - start
    if span <= 0:
        return time_s
    phase = float(layer.get("phase_s", 0.0))
    return start + ((time_s - start + phase) % span)


def cubic_bezier(points: list[list[float]], value: float) -> tuple[float, float]:
    inverse = 1.0 - value
    weights = (
        inverse ** 3,
        3.0 * inverse * inverse * value,
        3.0 * inverse * value * value,
        value ** 3,
    )
    x = sum(float(points[index][0]) * weights[index] for index in range(4))
    y = sum(float(points[index][1]) * weights[index] for index in range(4))
    return x, y


def cubic_bezier_tangent(points: list[list[float]], value: float) -> tuple[float, float]:
    inverse = 1.0 - value
    x = (
        3.0 * inverse * inverse * (float(points[1][0]) - float(points[0][0]))
        + 6.0 * inverse * value * (float(points[2][0]) - float(points[1][0]))
        + 3.0 * value * value * (float(points[3][0]) - float(points[2][0]))
    )
    y = (
        3.0 * inverse * inverse * (float(points[1][1]) - float(points[0][1]))
        + 6.0 * inverse * value * (float(points[2][1]) - float(points[1][1]))
        + 3.0 * value * value * (float(points[3][1]) - float(points[2][1]))
    )
    return x, y


def motion_path_at(layer: dict[str, Any], time_s: float) -> tuple[float, float, float]:
    path = layer.get("motion_path")
    if not path:
        return 0.0, 0.0, 0.0
    start = float(path.get("start_s", 0.0))
    end = float(path["end_s"])
    span = end - start
    local = time_s + float(path.get("phase_s", 0.0))
    if path.get("loop"):
        local = start + ((local - start) % span)
    progress = (local - start) / span
    progress = ease(progress, str(path.get("easing", "ease-in-out")))
    points = path["points"]
    x, y = cubic_bezier(points, progress)
    rotation = 0.0
    if path.get("orient_to_path"):
        tangent_x, tangent_y = cubic_bezier_tangent(points, progress)
        if abs(tangent_x) > 1e-6 or abs(tangent_y) > 1e-6:
            rotation = math.degrees(math.atan2(tangent_y, tangent_x))
            rotation += float(path.get("rotation_offset", 0.0))
    return x, y, rotation


def transform_at(layer: dict[str, Any], time_s: float) -> dict[str, float]:
    frames = layer["keyframes"]
    time_s = timeline_time(layer, time_s)
    before = frames[0]
    after = frames[-1]
    segment = len(frames) - 1
    for index in range(1, len(frames)):
        if time_s <= float(frames[index]["t"]):
            before, after = frames[index - 1], frames[index]
            segment = index
            break
    start = float(before["t"])
    end = float(after["t"])
    progress = 0.0 if end <= start else (time_s - start) / (end - start)
    easing = str(layer.get("easing", "smoothstep"))
    progress = ease(progress, easing)
    result: dict[str, float] = {}
    for key in TRANSFORM_KEYS:
        left = frame_value(before, key)
        right = frame_value(after, key)
        if easing == "catmull-rom" and len(frames) >= 3:
            if layer.get("loop") and segment == 1:
                left_outer = frame_value(frames[-2], key)
            else:
                left_outer = frame_value(frames[max(0, segment - 2)], key)
            if layer.get("loop") and segment == len(frames) - 1:
                right_outer = frame_value(frames[1], key)
            else:
                right_outer = frame_value(frames[min(len(frames) - 1, segment + 1)], key)
            result[key] = catmull_rom(
                left_outer, left, right, right_outer, progress
            )
        else:
            result[key] = left + (right - left) * progress
    result["opacity"] = min(1.0, max(0.0, result["opacity"]))
    path_x, path_y, path_rotation = motion_path_at(layer, time_s)
    result["x"] += path_x
    result["y"] += path_y
    result["rotation"] += path_rotation
    return result


def apply_transform(source: Image.Image, values: dict[str, float],
                    oversample: int = 1,
                    pivot: list[float] | None = None,
                    anchor: list[float] | None = None,
                    ) -> tuple[Image.Image, tuple[int, int]]:
    bbox = source.getbbox()
    if bbox is None:
        return Image.new("RGBA", (1, 1)), (0, 0)
    crop = source.crop(bbox)
    if pivot is not None:
        anchor_x = float(pivot[0]) - bbox[0]
        anchor_y = float(pivot[1]) - bbox[1]
    else:
        anchor = anchor or [0.5, 0.5]
        anchor_x = crop.width * float(anchor[0])
        anchor_y = crop.height * float(anchor[1])
    scale = max(0.01, values["scale"])
    scale_x = max(0.01, values["scale_x"] * scale)
    scale_y = max(0.01, values["scale_y"] * scale)
    width = max(1, round(crop.width * scale_x * oversample))
    height = max(1, round(crop.height * scale_y * oversample))
    anchor_x *= scale_x * oversample
    anchor_y *= scale_y * oversample
    if (width, height) != crop.size:
        crop = crop.resize((width, height), Image.Resampling.LANCZOS)
    rotation = values["rotation"]
    if abs(rotation) > 1e-6:
        radius = math.ceil(max(
            anchor_x,
            crop.width - anchor_x,
            anchor_y,
            crop.height - anchor_y,
        )) + 3
        stage = Image.new("RGBA", (radius * 2, radius * 2), (0, 0, 0, 0))
        stage.alpha_composite(
            crop,
            (round(radius - anchor_x), round(radius - anchor_y)),
        )
        stage = stage.rotate(
            -rotation,
            resample=Image.Resampling.BICUBIC,
            expand=False,
        )
        rotated_bbox = stage.getbbox()
        if rotated_bbox is None:
            return Image.new("RGBA", (1, 1)), (0, 0)
        crop = stage.crop(rotated_bbox)
        anchor_x = radius - rotated_bbox[0]
        anchor_y = radius - rotated_bbox[1]
    opacity = min(1.0, max(0.0, values["opacity"]))
    if opacity < 0.999:
        alpha = crop.getchannel("A").point(lambda value: round(value * opacity))
        crop.putalpha(alpha)
    world_x = (bbox[0] + (
        float(pivot[0]) - bbox[0]
        if pivot is not None else source.crop(bbox).width * float((anchor or [0.5, 0.5])[0])
    ) + values["x"]) * oversample
    world_y = (bbox[1] + (
        float(pivot[1]) - bbox[1]
        if pivot is not None else source.crop(bbox).height * float((anchor or [0.5, 0.5])[1])
    ) + values["y"]) * oversample
    position = (round(world_x - anchor_x), round(world_y - anchor_y))
    return crop, position


def load_layer_sources(
    manifest_path: Path,
    manifest: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Image.Image]]]:
    loaded: list[tuple[dict[str, Any], dict[str, Image.Image]]] = []
    for layer in sorted(manifest["layers"], key=lambda item: float(item.get("z", 0))):
        paths = {str(layer["path"])}
        paths.update(str(item["path"]) for item in layer.get("sprites", []))
        sources = {
            item: Image.open(manifest_path.parent / item).convert("RGBA")
            for item in paths
        }
        loaded.append((layer, sources))
    return loaded


def sprite_at(
    layer: dict[str, Any],
    sources: dict[str, Image.Image],
    time_s: float,
) -> tuple[Image.Image, dict[str, Any]]:
    sprites = layer.get("sprites", [])
    if not sprites:
        return sources[str(layer["path"])], layer
    local = time_s + float(layer.get("sprite_phase_s", 0.0))
    duration = float(layer.get("sprite_duration_s", 0.0))
    if layer.get("sprite_loop") and duration > 0:
        local %= duration
    current_index = 0
    for index, sprite in enumerate(sprites):
        if local >= float(sprite["t"]):
            current_index = index
        else:
            break
    current = sprites[current_index]
    next_index = current_index + 1
    next_time: float | None = None
    if next_index < len(sprites):
        next_time = float(sprites[next_index]["t"])
    elif layer.get("sprite_loop") and duration > 0:
        next_index = 0
        next_time = duration
    blend_s = max(0.0, float(layer.get("sprite_crossfade_s", 0.0)))
    if (
        next_time is not None
        and blend_s > 0
        and local >= next_time - blend_s
    ):
        progress = min(1.0, max(0.0, (local - (next_time - blend_s)) / blend_s))
        next_sprite = sprites[next_index]
        current_image = sources[str(current["path"])]
        next_image = sources[str(next_sprite["path"])]
        if current_image.size != next_image.size:
            size = (
                max(current_image.width, next_image.width),
                max(current_image.height, next_image.height),
            )
            current_stage = Image.new("RGBA", size, (0, 0, 0, 0))
            next_stage = Image.new("RGBA", size, (0, 0, 0, 0))
            current_stage.alpha_composite(current_image, (0, 0))
            next_stage.alpha_composite(next_image, (0, 0))
            current_image, next_image = current_stage, next_stage
        return Image.blend(current_image, next_image, progress), next_sprite
    return sources[str(current["path"])], current


def render_frame(manifest_path: Path, time_s: float,
                 loaded: list[tuple[dict[str, Any], dict[str, Image.Image]]] | None = None,
                 manifest: dict[str, Any] | None = None) -> Image.Image:
    manifest = manifest or load_manifest(manifest_path)
    canvas_data = manifest["canvas"]
    canvas = (int(canvas_data["width"]), int(canvas_data["height"]))
    oversample = int(canvas_data.get("oversample", 1))
    render_canvas = (canvas[0] * oversample, canvas[1] * oversample)
    frame = Image.new("RGBA", render_canvas, (0, 0, 0, 0))
    if loaded is None:
        loaded = load_layer_sources(manifest_path, manifest)
    for layer, sources in loaded:
        source, sprite = sprite_at(layer, sources, time_s)
        transformed, position = apply_transform(
            source,
            transform_at(layer, time_s),
            oversample,
            sprite.get("pivot", layer.get("pivot")),
            sprite.get("anchor", layer.get("anchor")),
        )
        frame.alpha_composite(transformed, position)
    if oversample > 1:
        frame = frame.resize(canvas, Image.Resampling.LANCZOS)
    return frame


def render_motion_blur_frame(
    manifest_path: Path,
    frame_index: int,
    fps: int,
    loaded: list[tuple[dict[str, Any], dict[str, Image.Image]]],
    manifest: dict[str, Any],
) -> Image.Image:
    canvas = manifest["canvas"]
    samples = int(canvas.get("motion_blur_samples", 1))
    if samples <= 1:
        return render_frame(manifest_path, frame_index / fps, loaded, manifest)
    shutter = float(canvas.get("shutter", 0.5))
    rendered: list[Image.Image] = []
    for sample in range(samples):
        position = (sample + 0.5) / samples - 0.5
        time_s = max(0.0, (frame_index + position * shutter) / fps)
        rendered.append(render_frame(manifest_path, time_s, loaded, manifest))
    result = rendered[0]
    for index, sample in enumerate(rendered[1:], 2):
        result = Image.blend(result, sample, 1.0 / index)
    return result


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
    loaded = load_layer_sources(manifest_path, manifest)
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
            process.stdin.write(
                render_motion_blur_frame(
                    manifest_path, frame_index, fps, loaded, manifest
                ).tobytes()
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
