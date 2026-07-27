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
            "depth": depth,
            "camera_response": {
                "x_multiplier": -depth,
                "y_multiplier": -depth,
                "scale_multiplier": depth,
            },
            "content_sha256": members[source_id].get("content_sha256")
            or production_contract.file_digest(source_path),
        })
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
        "camera": spec.get(
            "camera",
            {"keyframes": [{"t": 0}, {"t": duration_s}]},
        ),
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
        "fingerprint": production_contract.canonical_digest({
            "registration": registration.get("registration_fingerprint"),
            "stack": response,
            "camera": manifest["camera"],
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
