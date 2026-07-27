#!/usr/bin/env python3
"""Derive one auditable registered rear/subject/front family from a complete source sheet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

import asset_quality
import production_contract


ROLES = ("support-rear", "subject", "support-front")
FACINGS = {"left", "right", "front", "rear", "three-quarter-left", "three-quarter-right"}


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
    family_kind = str(spec.get("family_kind", "depth"))
    state_specs: list[dict[str, Any]] = []
    if family_kind == "depth":
        if not isinstance(cells, dict) or set(cells) != {"reference", *ROLES}:
            raise RegisteredFamilyError(
                "cells must contain reference, support-rear, subject, support-front"
            )
        descriptors = [{"id": role, "role": role} for role in ROLES]
    elif family_kind == "state":
        state_specs = spec.get("states", [])
        if not isinstance(state_specs, list) or len(state_specs) < 2:
            raise RegisteredFamilyError("state family requires at least two states")
        state_ids = [str(item.get("id", "")).strip() for item in state_specs]
        if not all(state_ids) or len(state_ids) != len(set(state_ids)):
            raise RegisteredFamilyError("state ids must be unique and non-empty")
        if not isinstance(cells, dict) or set(cells) != {"reference", *state_ids}:
            raise RegisteredFamilyError(
                "state cells must contain reference and every declared state id"
            )
        identity_reference_id = str(spec.get("identity_reference_id", "")).strip()
        if not identity_reference_id:
            raise RegisteredFamilyError("state family requires identity_reference_id")
        descriptors = [
            {
                "id": state_id,
                "role": "state",
                "state": item,
            }
            for state_id, item in zip(state_ids, state_specs, strict=True)
        ]
    else:
        raise RegisteredFamilyError("family_kind must be depth or state")
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
    anchor_evidence: list[dict[str, Any]] = []
    for descriptor in descriptors:
        member_id = descriptor["id"]
        role = descriptor["role"]
        x, y, width, height = _rect(cells[member_id], f"cells.{member_id}")
        if x + width > image.width or y + height > image.height:
            raise RegisteredFamilyError(f"cells.{member_id} leaves the source sheet")
        cell = image.crop((x, y, x + width, y + height))
        temporary = output_dir / f".{member_id}-cell.png"
        cell.save(temporary)
        output = output_dir / f"{member_id}.png"
        key_metadata = None
        if observation:
            key_metadata = asset_quality.remove_observed_key(temporary, output)
            temporary.unlink()
        else:
            cell = cell.resize(canvas_size, Image.Resampling.LANCZOS)
            cell.save(output)
            temporary.unlink()
        if Image.open(output).size != canvas_size:
            keyed = Image.open(output).convert("RGBA").resize(
                canvas_size, Image.Resampling.LANCZOS
            )
            keyed.save(output)
        member = {
            "id": f"{spec['id']}:{member_id}",
            "role": role,
            "state_id": member_id if family_kind == "state" else None,
            "path": str(output),
            "canvas": list(canvas_size),
            "origin": [0, 0],
            "trimmed": False,
            "source_rect": [x, y, width, height],
            "source_sha256": source_sha,
            "content_sha256": production_contract.file_digest(output),
            "key_metadata": key_metadata,
        }
        if family_kind == "state":
            state = descriptor["state"]
            facing = str(state.get("facing", "")).strip()
            if facing not in FACINGS:
                raise RegisteredFamilyError(
                    f"{member_id}.facing must be a supported explicit direction"
                )
            anchors = state.get("anchors")
            if not isinstance(anchors, dict) or "identity" not in anchors:
                raise RegisteredFamilyError(
                    f"{member_id}.anchors requires an identity anchor"
                )
            normalized: dict[str, list[float]] = {}
            for anchor_id, point in anchors.items():
                if not isinstance(point, list) or len(point) != 2:
                    raise RegisteredFamilyError(
                        f"{member_id}.anchors.{anchor_id} must be [x,y]"
                    )
                px, py = float(point[0]), float(point[1])
                if not (0 <= px <= canvas_size[0] and 0 <= py <= canvas_size[1]):
                    raise RegisteredFamilyError(
                        f"{member_id}.anchors.{anchor_id} leaves the registered canvas"
                    )
                normalized[str(anchor_id)] = [px, py]
            member["facing"] = facing
            member["anchors"] = normalized
            overlay = Image.open(output).convert("RGBA")
            brush = ImageDraw.Draw(overlay)
            for anchor_id, point in normalized.items():
                px, py = point
                brush.line((px - 7, py, px + 7, py), fill="#ff2a2a", width=2)
                brush.line((px, py - 7, px, py + 7), fill="#ff2a2a", width=2)
                brush.text((px + 8, py - 8), anchor_id, fill="#ff2a2a")
            overlay_path = output_dir / f"{member_id}-anchors.png"
            overlay.save(overlay_path)
            anchor_evidence.append({
                "state_id": member_id,
                "path": str(overlay_path),
                "content_sha256": production_contract.file_digest(overlay_path),
            })
        members.append(member)
    anchor_drift: dict[str, Any] | None = None
    if family_kind == "state":
        points = [member["anchors"]["identity"] for member in members]
        spread_x = max(point[0] for point in points) - min(point[0] for point in points)
        spread_y = max(point[1] for point in points) - min(point[1] for point in points)
        limit = float(spec.get("max_identity_anchor_drift_px", 12.0))
        anchor_drift = {
            "spread_px": [round(spread_x, 4), round(spread_y, 4)],
            "limit_px": limit,
            "passed": max(spread_x, spread_y) <= limit,
        }
        if not anchor_drift["passed"]:
            raise RegisteredFamilyError(
                "identity anchor drift exceeds max_identity_anchor_drift_px"
            )
    family_basis = {
        "id": str(spec.get("id", "")).strip(),
        "family_kind": family_kind,
        "registration_id": str(spec.get("registration_id", "")).strip(),
        "identity_reference_id": (
            str(spec.get("identity_reference_id", "")).strip()
            if family_kind == "state"
            else None
        ),
        "source_strategy": "registered-sheet",
        "source_sha256": source_sha,
        "canvas": list(canvas_size),
        "members": members,
        "anchor_evidence": anchor_evidence,
        "anchor_drift": anchor_drift,
        "recovery_policy": [
            "local-reprocess",
            "full-source-context-masked-edit",
            "complete-source-regeneration",
        ],
        "isolated_member_replacement_allowed": False,
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
