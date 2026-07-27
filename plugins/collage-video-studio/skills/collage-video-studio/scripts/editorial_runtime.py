#!/usr/bin/env python3
"""Compile recursive editorial compositions into deterministic layer manifests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


class EditorialError(RuntimeError):
    pass


TRANSFORM_DEFAULTS = {
    "x": 0.0,
    "y": 0.0,
    "scale": 1.0,
    "scale_x": 1.0,
    "scale_y": 1.0,
    "rotation": 0.0,
    "opacity": 1.0,
}


def _frames(node: dict[str, Any], duration_s: float) -> list[dict[str, Any]]:
    frames = node.get("keyframes")
    if not isinstance(frames, list) or not frames:
        return [{"t": 0.0}, {"t": duration_s}]
    return copy.deepcopy(frames)


def _sample(frames: list[dict[str, Any]], time_s: float) -> dict[str, float]:
    before = frames[0]
    after = frames[-1]
    for index in range(1, len(frames)):
        if time_s <= float(frames[index]["t"]):
            before, after = frames[index - 1], frames[index]
            break
    start = float(before["t"])
    end = float(after["t"])
    progress = 0.0 if end <= start else min(1.0, max(0.0, (time_s - start) / (end - start)))
    # Compiler interpolation stays linear. Runtime easing remains on authored segments.
    return {
        key: float(before.get(key, default))
        + (
            float(after.get(key, default))
            - float(before.get(key, default))
        ) * progress
        for key, default in TRANSFORM_DEFAULTS.items()
    }


def _camera_frames(
    node_frames: list[dict[str, Any]],
    camera_frames: list[dict[str, Any]],
    depth: float,
) -> list[dict[str, Any]]:
    if abs(depth) < 1e-9 or not camera_frames:
        return node_frames
    times = sorted({
        *(float(frame["t"]) for frame in node_frames),
        *(float(frame["t"]) for frame in camera_frames),
    })
    result: list[dict[str, Any]] = []
    for time_s in times:
        own = _sample(node_frames, time_s)
        camera = _sample(camera_frames, time_s)
        own["x"] -= camera["x"] * depth
        own["y"] -= camera["y"] * depth
        own["scale"] *= 1.0 + (camera["scale"] - 1.0) * depth
        own["t"] = time_s
        own["ease"] = "catmull-rom" if len(times) >= 3 else "linear"
        result.append(own)
    return result


def _merge_override(node: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    result = copy.deepcopy(node)
    if not isinstance(override, dict):
        return result
    for key, value in override.items():
        if key == "primitive" and isinstance(value, dict):
            result[key] = {**result.get(key, {}), **copy.deepcopy(value)}
        else:
            result[key] = copy.deepcopy(value)
    return result


def compile_composition(manifest: dict[str, Any]) -> dict[str, Any]:
    """Compile `composition` when present; return old layer manifests unchanged."""
    composition = manifest.get("composition")
    if composition is None:
        return manifest
    if not isinstance(composition, dict):
        raise EditorialError("composition must be an object")
    canvas = manifest.get("canvas", {})
    duration_s = float(canvas.get("duration_s", 0.0))
    if duration_s <= 0:
        raise EditorialError("canvas.duration_s must be positive before compilation")
    camera = manifest.get("camera", {})
    camera_frames = (
        _frames(camera, duration_s)
        if isinstance(camera, dict) and camera.get("keyframes")
        else []
    )
    director = manifest.get("director", {})
    overrides = director.get("node_overrides", {}) if isinstance(director, dict) else {}
    if not isinstance(overrides, dict):
        raise EditorialError("director.node_overrides must be an object")
    layers: list[dict[str, Any]] = []
    seen: set[str] = set()

    def visit(raw: dict[str, Any], parent: str | None, inherited_z: float) -> None:
        if not isinstance(raw, dict):
            raise EditorialError("every composition node must be an object")
        node_id = str(raw.get("id", "")).strip()
        if not node_id or node_id in seen:
            raise EditorialError("composition node ids must be present and unique")
        seen.add(node_id)
        node = _merge_override(raw, overrides.get(node_id))
        node_type = str(node.get("type", "image"))
        if node_type not in {"group", "image", "primitive"}:
            raise EditorialError(f"{node_id}: unsupported node type {node_type!r}")
        z = inherited_z + float(node.get("z", 0.0))
        depth = float(node.get("depth", 0.0))
        if depth < -1.0 or depth > 1.0:
            raise EditorialError(f"{node_id}: depth must be from -1 to 1")
        layer: dict[str, Any] = {
            "id": node_id,
            "z": z,
            "role": str(node.get("role", node_type)),
            "depth": depth,
            "keyframes": _camera_frames(
                _frames(node, duration_s), camera_frames, depth
            ),
        }
        for key in (
            "easing", "motion_class", "motion_intent", "pivot", "anchor",
            "visibility", "pose_sequence", "looping_strip", "motif_field",
            "motion_path", "loop", "phase_s",
        ):
            if key in node:
                layer[key] = copy.deepcopy(node[key])
        if parent:
            follow = copy.deepcopy(node.get("follow", {}))
            follow.setdefault("parent", parent)
            follow.setdefault("lag_s", 0)
            follow.setdefault(
                "inherit",
                {
                    "x": 1,
                    "y": 1,
                    "scale": 1,
                    "scale_x": 1,
                    "scale_y": 1,
                    "rotation": 1,
                    "opacity": 1,
                },
            )
            layer["follow"] = follow
        if node_type == "image":
            layer["path"] = str(node.get("path", ""))
        elif node_type == "primitive":
            primitive = node.get("primitive")
            if not isinstance(primitive, dict):
                raise EditorialError(f"{node_id}: primitive node needs primitive object")
            layer["primitive"] = copy.deepcopy(primitive)
        else:
            # Transparent group layers carry transforms for descendants.
            layer["primitive"] = {"kind": "group"}
        layers.append(layer)
        children = node.get("children", [])
        if node_type != "group" and children:
            raise EditorialError(f"{node_id}: only group nodes may have children")
        if not isinstance(children, list):
            raise EditorialError(f"{node_id}: children must be an array")
        for child in children:
            visit(child, node_id, z)

    visit(composition, None, 0.0)
    edit_points = manifest.get("edit_points", [])
    if not isinstance(edit_points, list):
        raise EditorialError("edit_points must be an array")
    normalized_edit_points: list[dict[str, Any]] = []
    edit_ids: set[str] = set()
    previous_at = -1.0
    for index, raw_point in enumerate(edit_points, 1):
        if not isinstance(raw_point, dict):
            raise EditorialError(f"edit_points[{index}] must be an object")
        point_id = str(raw_point.get("id", "")).strip()
        target = str(raw_point.get("target", "")).strip()
        try:
            at_s = float(raw_point["at_s"])
        except (KeyError, TypeError, ValueError) as exc:
            raise EditorialError(
                f"edit_points[{index}].at_s must be numeric"
            ) from exc
        if (
            not point_id or point_id in edit_ids or target not in seen
            or at_s < previous_at or at_s < 0 or at_s > duration_s
        ):
            raise EditorialError(
                f"edit_points[{index}] needs unique id, existing target, and "
                "sorted at_s inside the composition"
            )
        edit_ids.add(point_id)
        previous_at = at_s
        normalized_edit_points.append({
            "id": point_id,
            "at_s": at_s,
            "target": target,
            "action": str(raw_point.get("action", "review")),
            "note": str(raw_point.get("note", "")),
        })
    result = copy.deepcopy(manifest)
    result["layers"] = layers
    result["compiled_editorial"] = {
        "node_count": len(layers),
        "director_id": (
            str(director.get("id", "")) if isinstance(director, dict) else ""
        ),
        "camera_coupled": bool(camera_frames),
        "edit_points": normalized_edit_points,
    }
    return result


def load_and_compile(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EditorialError(f"cannot read editorial manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EditorialError("editorial manifest must be a JSON object")
    return compile_composition(value)
