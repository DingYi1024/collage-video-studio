#!/usr/bin/env python3
"""Deterministic annotation collision avoidance for editorial compositions."""

from __future__ import annotations

import copy
from typing import Any


Rect = tuple[float, float, float, float]


class AnnotationLayoutError(RuntimeError):
    pass


def _rect(value: Any, label: str) -> Rect:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise AnnotationLayoutError(f"{label} must be [x,y,width,height]")
    try:
        result = tuple(float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise AnnotationLayoutError(f"{label} must be numeric") from exc
    if result[2] <= 0 or result[3] <= 0:
        raise AnnotationLayoutError(f"{label} needs positive width and height")
    return result  # type: ignore[return-value]


def intersects(first: Rect, second: Rect, padding: float = 0.0) -> bool:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    return (
        ax < bx + bw + padding
        and ax + aw + padding > bx
        and ay < by + bh + padding
        and ay + ah + padding > by
    )


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def place(
    target: tuple[float, float],
    size: tuple[float, float],
    canvas: tuple[float, float],
    *,
    preferred: str = "right",
    padding: float = 12.0,
    exclusions: list[Rect] | None = None,
    occupied: list[Rect] | None = None,
) -> Rect:
    tx, ty = target
    width, height = size
    candidates = {
        "right": (tx + padding, ty - height / 2, width, height),
        "left": (tx - width - padding, ty - height / 2, width, height),
        "top": (tx - width / 2, ty - height - padding, width, height),
        "bottom": (tx - width / 2, ty + padding, width, height),
    }
    order = list(dict.fromkeys(
        [preferred, "right", "left", "top", "bottom"]
    ))
    blocked = [*(exclusions or []), *(occupied or [])]
    for direction in order:
        if direction not in candidates:
            continue
        raw = candidates[direction]
        candidate = (
            _clamp(raw[0], padding, canvas[0] - width - padding),
            _clamp(raw[1], padding, canvas[1] - height - padding),
            width,
            height,
        )
        if not any(intersects(candidate, item, padding) for item in blocked):
            return candidate
    step = max(4.0, padding)
    y = padding
    while y <= canvas[1] - height - padding:
        candidate = (
            _clamp(tx + padding, padding, canvas[0] - width - padding),
            y,
            width,
            height,
        )
        if not any(intersects(candidate, item, padding) for item in blocked):
            return candidate
        y += step
    raise AnnotationLayoutError(
        "no collision-free annotation placement exists on the canvas"
    )


def resolve_manifest(manifest: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    result = copy.deepcopy(manifest)
    canvas_data = result.get("canvas", {})
    canvas = (
        float(canvas_data.get("width", 0)),
        float(canvas_data.get("height", 0)),
    )
    if min(canvas) <= 0:
        raise AnnotationLayoutError("canvas width and height must be positive")
    director = result.get("director", {})
    zones = director.get("safe_zones", []) if isinstance(director, dict) else []
    exclusions: list[Rect] = []
    for index, zone in enumerate(zones, 1):
        if str(zone.get("policy", "")) == "exclude":
            exclusions.append(_rect(zone.get("rect"), f"safe_zones[{index}].rect"))
    occupied: list[Rect] = []
    placements: list[dict[str, Any]] = []

    def visit(node: dict[str, Any]) -> None:
        primitive = node.get("primitive")
        if isinstance(primitive, dict) and primitive.get("kind") == "annotation":
            target_raw = primitive.get("target")
            if not isinstance(target_raw, list) or len(target_raw) != 2:
                raise AnnotationLayoutError(
                    f"{node.get('id')}: annotation target must be [x,y]"
                )
            target = (float(target_raw[0]), float(target_raw[1]))
            initial = _rect(
                primitive.get(
                    "label_box",
                    [target[0] + 20, target[1] + 20, 220, 64],
                ),
                f"{node.get('id')}.label_box",
            )
            avoidance = primitive.get("avoidance", {})
            if not isinstance(avoidance, dict):
                raise AnnotationLayoutError(
                    f"{node.get('id')}: avoidance must be an object"
                )
            local_exclusions = list(exclusions)
            for index, item in enumerate(avoidance.get("exclusions", []), 1):
                local_exclusions.append(
                    _rect(item, f"{node.get('id')}.avoidance.exclusions[{index}]")
                )
            placed = place(
                target,
                (initial[2], initial[3]),
                canvas,
                preferred=str(avoidance.get("preferred", "right")),
                padding=float(avoidance.get("padding", 12)),
                exclusions=local_exclusions,
                occupied=occupied,
            )
            primitive["label_box"] = [round(value, 3) for value in placed]
            occupied.append(placed)
            placements.append({
                "id": str(node.get("id")),
                "target": list(target),
                "label_box": primitive["label_box"],
            })
        children = node.get("children", [])
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    visit(child)

    composition = result.get("composition")
    if isinstance(composition, dict):
        visit(composition)
    return result, {
        "annotations": len(placements),
        "placements": placements,
        "exclusions": len(exclusions),
        "passed": True,
    }
