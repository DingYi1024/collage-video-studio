#!/usr/bin/env python3
"""Derive one auditable registered rear/subject/front family from a complete source sheet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image

import asset_quality
import production_contract


ROLES = ("support-rear", "subject", "support-front")


class RegisteredFamilyError(RuntimeError):
    pass


def _rect(value: Any, label: str) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise RegisteredFamilyError(f"{label} must be [x,y,width,height]")
    x, y, width, height = (int(item) for item in value)
    if min(x, y) < 0 or width <= 0 or height <= 0:
        raise RegisteredFamilyError(f"{label} is invalid")
    return x, y, width, height


def derive(
    source: Path,
    spec: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    if spec.get("source_strategy") != "registered-sheet":
        raise RegisteredFamilyError("family derivation requires registered-sheet")
    cells = spec.get("cells")
    if not isinstance(cells, dict) or set(cells) != {"reference", *ROLES}:
        raise RegisteredFamilyError(
            "cells must contain reference, support-rear, subject, support-front"
        )
    canvas = spec.get("canvas")
    if not isinstance(canvas, list) or len(canvas) != 2:
        raise RegisteredFamilyError("canvas must be [width,height]")
    canvas_size = (int(canvas[0]), int(canvas[1]))
    if min(canvas_size) <= 0:
        raise RegisteredFamilyError("canvas dimensions must be positive")
    image = Image.open(source).convert("RGBA")
    source_sha = production_contract.file_digest(source)
    observation: dict[str, Any] | None = None
    if spec.get("key_policy") == "provider-native-observed":
        observation = asset_quality.observe_key_plane(source)
        if not observation["passed"]:
            raise RegisteredFamilyError("; ".join(observation["issues"]))
    output_dir.mkdir(parents=True, exist_ok=True)
    members: list[dict[str, Any]] = []
    for role in ROLES:
        x, y, width, height = _rect(cells[role], f"cells.{role}")
        if x + width > image.width or y + height > image.height:
            raise RegisteredFamilyError(f"cells.{role} leaves the source sheet")
        cell = image.crop((x, y, x + width, y + height))
        temporary = output_dir / f".{role}-cell.png"
        cell.save(temporary)
        output = output_dir / f"{role}.png"
        key_metadata = None
        if observation:
            key_metadata = asset_quality.remove_observed_key(temporary, output)
            temporary.unlink()
        else:
            cell = cell.resize(canvas_size, Image.Resampling.LANCZOS)
            cell.save(output)
        if Image.open(output).size != canvas_size:
            keyed = Image.open(output).convert("RGBA").resize(
                canvas_size, Image.Resampling.LANCZOS
            )
            keyed.save(output)
        members.append({
            "id": f"{spec['id']}:{role}",
            "role": role,
            "path": str(output),
            "canvas": list(canvas_size),
            "origin": [0, 0],
            "trimmed": False,
            "source_rect": [x, y, width, height],
            "source_sha256": source_sha,
            "content_sha256": production_contract.file_digest(output),
            "key_metadata": key_metadata,
        })
    family_basis = {
        "id": str(spec.get("id", "")).strip(),
        "registration_id": str(spec.get("registration_id", "")).strip(),
        "source_strategy": "registered-sheet",
        "source_sha256": source_sha,
        "canvas": list(canvas_size),
        "members": members,
        "recovery_policy": [
            "local-reprocess",
            "context-preserving-source-edit",
            "complete-source-regeneration",
        ],
        "observation": observation,
    }
    if not family_basis["id"] or not family_basis["registration_id"]:
        raise RegisteredFamilyError("id and registration_id are required")
    family_basis["family_fingerprint"] = production_contract.canonical_digest(
        family_basis
    )
    manifest = output_dir / "registered-family.json"
    manifest.write_text(
        json.dumps(family_basis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return family_basis


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("spec", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        report = derive(args.source.resolve(), spec, args.output.resolve())
        print(
            f"registered family: {report['family_fingerprint']} "
            f"({len(report['members'])} local derivatives)"
        )
        return 0
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        RegisteredFamilyError,
        asset_quality.AssetQualityError,
    ) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
