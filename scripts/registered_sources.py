#!/usr/bin/env python3
"""Build full-canvas, registration-safe RGBA sources from one transparent board."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from PIL import Image

import production_contract


class RegisteredSourceError(RuntimeError):
    pass


SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegisteredSourceError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RegisteredSourceError("spec must be a JSON object")
    return value


def rectangle(value: Any, label: str) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise RegisteredSourceError(f"{label} must be [x,y,width,height]")
    try:
        x, y, width, height = (int(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise RegisteredSourceError(f"{label} values must be integers") from exc
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise RegisteredSourceError(f"{label} must have non-negative origin and positive size")
    return x, y, width, height


def build(board_path: Path, spec_path: Path, output_dir: Path) -> Path:
    spec = load_object(spec_path)
    canvas_raw = spec.get("canvas")
    if not isinstance(canvas_raw, list) or len(canvas_raw) != 2:
        raise RegisteredSourceError("canvas must be [width,height]")
    canvas = (int(canvas_raw[0]), int(canvas_raw[1]))
    if min(canvas) <= 0:
        raise RegisteredSourceError("canvas dimensions must be positive")
    items = spec.get("items")
    if not isinstance(items, list) or not items:
        raise RegisteredSourceError("items must be a non-empty array")
    try:
        board = Image.open(board_path).convert("RGBA")
    except OSError as exc:
        raise RegisteredSourceError(f"cannot open source board: {exc}") from exc
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise RegisteredSourceError(f"item[{index}] must be an object")
        item_id = str(item.get("id", "")).strip()
        if not SAFE_ID.match(item_id) or item_id in seen:
            raise RegisteredSourceError(
                f"item[{index}].id must be unique and filesystem-safe"
            )
        seen.add(item_id)
        x, y, width, height = rectangle(item.get("source_rect"), f"{item_id}.source_rect")
        if x + width > board.width or y + height > board.height:
            raise RegisteredSourceError(f"{item_id}.source_rect exceeds source board")
        place = item.get("place", [x, y])
        if not isinstance(place, list) or len(place) != 2:
            raise RegisteredSourceError(f"{item_id}.place must be [x,y]")
        place_x, place_y = int(place[0]), int(place[1])
        if (
            place_x < 0
            or place_y < 0
            or place_x + width > canvas[0]
            or place_y + height > canvas[1]
        ):
            raise RegisteredSourceError(f"{item_id} placement exceeds output canvas")
        crop = board.crop((x, y, x + width, y + height))
        layer = Image.new("RGBA", canvas, (0, 0, 0, 0))
        layer.alpha_composite(crop, (place_x, place_y))
        output = output_dir / f"{item_id}.png"
        layer.save(output)
        records.append({
            "id": item_id,
            "path": output.name,
            "role": str(item.get("role", "object")),
            "z": float(item.get("z", index)),
            "source_rect": [x, y, width, height],
            "place": [place_x, place_y],
            "content_sha256": production_contract.file_digest(output),
        })
    manifest = {
        "schema_version": 1,
        "canvas": list(canvas),
        "source_board": {
            "name": board_path.name,
            "content_sha256": production_contract.file_digest(board_path),
        },
        "members": records,
        "registration_fingerprint": production_contract.canonical_digest({
            "canvas": canvas,
            "source": production_contract.file_digest(board_path),
            "items": records,
        }),
    }
    output_manifest = output_dir / "registration.json"
    output_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board")
    parser.add_argument("spec")
    parser.add_argument("output_dir")
    args = parser.parse_args()
    try:
        output = build(
            Path(args.board).resolve(),
            Path(args.spec).resolve(),
            Path(args.output_dir).resolve(),
        )
    except (RegisteredSourceError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"registration: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

