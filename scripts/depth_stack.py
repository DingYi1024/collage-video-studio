#!/usr/bin/env python3
"""Compile registered full-canvas source families into camera-coupled depth stacks."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import editorial_runtime
import production_contract


class DepthStackError(RuntimeError):
    pass


ASPECTS = ("16:9", "9:16", "1:1")
STACK_ROLES = ("support-rear", "subject", "support-front")


def _responsive_envelope(value: Any, label: str) -> dict[str, list[float]]:
    if not isinstance(value, dict) or set(value) != set(ASPECTS):
        raise DepthStackError(f"{label} must declare exactly {', '.join(ASPECTS)}")
    result: dict[str, list[float]] = {}
    for aspect in ASPECTS:
        rect = value[aspect]
        if not isinstance(rect, list) or len(rect) != 4:
            raise DepthStackError(f"{label}.{aspect} must be a normalized rectangle")
        parsed = [float(item) for item in rect]
        if (
            any(item < 0 or item > 1 for item in parsed)
            or parsed[0] > parsed[2]
            or parsed[1] > parsed[3]
        ):
            raise DepthStackError(f"{label}.{aspect} is invalid")
        result[aspect] = parsed
    return result


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DepthStackError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DepthStackError(f"{path} must contain an object")
    return value


def compile_stack(
    registration_path: Path,
    spec_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    registration = _read(registration_path)
    spec = _read(spec_path)
    members = {
        str(item.get("id")): item
        for item in registration.get("members", [])
        if isinstance(item, dict) and item.get("id")
    }
    stack = spec.get("stack")
    if not isinstance(stack, list) or not stack:
        raise DepthStackError("stack must be a non-empty array")
    canvas_raw = registration.get("canvas")
    if not isinstance(canvas_raw, list) or len(canvas_raw) != 2:
        raise DepthStackError("registration canvas must be [width,height]")
    width, height = int(canvas_raw[0]), int(canvas_raw[1])
    duration_s = float(spec.get("duration_s", 4.0))
    fps = int(spec.get("fps", 30))
    if min(width, height, duration_s, fps) <= 0:
        raise DepthStackError("canvas, duration, and fps must be positive")
    children: list[dict[str, Any]] = []
    registration_members: list[str] = []
    seen: set[str] = set()
    response: list[dict[str, Any]] = []
    for index, raw in enumerate(stack, 1):
        if not isinstance(raw, dict):
            raise DepthStackError(f"stack[{index}] must be an object")
        layer_id = str(raw.get("id") or raw.get("source_id") or "")
        source_id = str(raw.get("source_id") or layer_id)
        if not layer_id or layer_id in seen:
            raise DepthStackError("stack ids must be present and unique")
        if source_id not in members:
            raise DepthStackError(f"{layer_id}: unknown registered source {source_id}")
        seen.add(layer_id)
        depth = float(raw.get("depth", 0))
        if depth < -1 or depth > 1:
            raise DepthStackError(f"{layer_id}: depth must be from -1 to 1")
        source_path = registration_path.parent / str(members[source_id]["path"])
        if not source_path.is_file():
            raise DepthStackError(f"{layer_id}: registered file is missing")
        member_canvas = members[source_id].get("canvas", canvas_raw)
        if [int(item) for item in member_canvas] != [width, height]:
            raise DepthStackError(f"{layer_id}: member canvas breaks registration")
        if bool(members[source_id].get("trimmed", False)):
            raise DepthStackError(f"{layer_id}: registered members must not be trimmed")
        portable = Path(os.path.relpath(source_path, output_path.parent)).as_posix()
        child = {
            "id": layer_id,
            "type": "image",
            "path": portable,
            "role": str(raw.get("role", members[source_id].get("role", "object"))),
            "z": float(raw.get("z", members[source_id].get("z", index))),
            "depth": depth,
            "keyframes": raw.get(
                "keyframes",
                [{"t": 0}, {"t": duration_s}],
            ),
        }
        children.append(child)
        registration_members.append(layer_id)
        response.append({
            "id": layer_id,
            "source_id": source_id,
            "role": child["role"],
            "depth": depth,
            "camera_response": {
                "x_multiplier": -depth,
                "y_multiplier": -depth,
                "scale_multiplier": depth,
            },
            "content_sha256": members[source_id].get("content_sha256")
            or production_contract.file_digest(source_path),
        })
    roles = [item["role"] for item in response]
    if roles != list(STACK_ROLES):
        raise DepthStackError(
            "registered depth stack order must be support-rear, subject, support-front"
        )
    depths = [float(item["depth"]) for item in response]
    if any(left >= right for left, right in zip(depths, depths[1:])):
        raise DepthStackError("registered depth depths must increase rear to front")
    reveal_envelope = _responsive_envelope(
        spec.get("reveal_envelope"), "reveal_envelope"
    )
    subject_travel = (
        _responsive_envelope(
            spec["subject_travel_envelope"], "subject_travel_envelope"
        )
        if spec.get("subject_travel_envelope") is not None
        else None
    )
    camera = spec.get(
        "camera",
        {"keyframes": [{"t": 0}, {"t": duration_s}]},
    )
    camera_frames = camera.get("keyframes", []) if isinstance(camera, dict) else []
    camera_visible = any(
        abs(float(frame.get("x", 0))) > 0.5
        or abs(float(frame.get("y", 0))) > 0.5
        or abs(float(frame.get("scale", 1)) - 1) > 0.002
        for frame in camera_frames
    )
    if not camera_visible or len(set(depths)) < 2:
        raise DepthStackError(
            "camera-coupled depth requires visible camera motion and distinct depths"
        )
    manifest = {
        "canvas": {
            "width": width,
            "height": height,
            "fps": fps,
            "duration_s": duration_s,
            "background": str(spec.get("background", "#171411")),
            "oversample": int(spec.get("oversample", 1)),
            "motion_blur_samples": int(spec.get("motion_blur_samples", 1)),
        },
        "camera": camera,
        "quality": spec.get(
            "quality",
            {
                "min_layers": len(children) + 1,
                "min_animated_layers": max(1, len(children)),
            },
        ),
        "registration": {
            "source_manifest": Path(
                os.path.relpath(registration_path, output_path.parent)
            ).as_posix(),
            "members": registration_members,
            "fingerprint": registration.get("registration_fingerprint"),
        },
        "composition": {
            "id": str(spec.get("id", "registered-depth-stack")),
            "type": "group",
            "children": children,
        },
    }
    compiled = editorial_runtime.compile_composition(manifest)
    compiled["registered_depth_stack"] = {
        "schema_version": 1,
        "layers": response,
        "camera_coupled": bool(
            isinstance(manifest["camera"], dict)
            and manifest["camera"].get("keyframes")
        ),
        "motion_capability": str(
            spec.get("motion_capability", "bounded-relative")
        ),
        "reveal_envelope": reveal_envelope,
        "subject_travel_envelope": subject_travel,
        "proof_extremes": [
            {
                "aspect": aspect,
                "reveal": reveal_envelope[aspect],
                "subject_travel": (
                    subject_travel[aspect] if subject_travel else None
                ),
            }
            for aspect in ASPECTS
        ],
        "fingerprint": production_contract.canonical_digest({
            "registration": registration.get("registration_fingerprint"),
            "stack": response,
            "camera": manifest["camera"],
            "reveal_envelope": reveal_envelope,
            "subject_travel_envelope": subject_travel,
        }),
    }
    return compiled


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registration")
    parser.add_argument("spec")
    parser.add_argument("output")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    try:
        result = compile_stack(
            Path(args.registration).resolve(),
            Path(args.spec).resolve(),
            output,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (DepthStackError, editorial_runtime.EditorialError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2
    print(f"registered depth stack: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
