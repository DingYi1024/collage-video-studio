#!/usr/bin/env python3
"""Prove that a masked provider repair preserved the complete registered source context."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

import production_contract


class ContextRepairError(RuntimeError):
    pass


def _rect(value: Any, label: str) -> tuple[int, int, int, int]:
    if not isinstance(value, list) or len(value) != 4:
        raise ContextRepairError(f"{label} must be [x,y,width,height]")
    x, y, width, height = (int(item) for item in value)
    if min(x, y) < 0 or width <= 0 or height <= 0:
        raise ContextRepairError(f"{label} is invalid")
    return x, y, width, height


def prove(original: Path, repaired: Path, spec: dict[str, Any]) -> dict[str, Any]:
    source = Image.open(original).convert("RGBA")
    candidate = Image.open(repaired).convert("RGBA")
    if source.size != candidate.size:
        raise ContextRepairError("repair must preserve the complete source canvas")
    mask = _rect(spec.get("mask"), "mask")
    x, y, width, height = mask
    if x + width > source.width or y + height > source.height:
        raise ContextRepairError("mask leaves the source canvas")
    mask_image = Image.new("L", source.size, 0)
    mask_image.paste(255, (x, y, x + width, y + height))
    outside_mask = ImageChops.invert(mask_image)
    outside_diff = ImageChops.difference(source, candidate)
    channels = outside_diff.split()
    channel_delta = channels[0]
    for channel in channels[1:]:
        channel_delta = ImageChops.lighter(channel_delta, channel)
    outside_changed = Image.composite(
        channel_delta, Image.new("L", source.size), outside_mask
    )
    outside_bbox = outside_changed.getbbox()
    inside_diff = Image.composite(
        channel_delta, Image.new("L", source.size), mask_image
    )
    inside_bbox = inside_diff.getbbox()
    accepted_checks: list[dict[str, Any]] = []
    for index, raw in enumerate(spec.get("accepted_regions", []), 1):
        rect = _rect(raw.get("rect"), f"accepted_regions[{index}].rect")
        rx, ry, rw, rh = rect
        if rx + rw > source.width or ry + rh > source.height:
            raise ContextRepairError("accepted region leaves the source canvas")
        overlap = not (
            rx + rw <= x or x + width <= rx or ry + rh <= y or y + height <= ry
        )
        unchanged = (
            ImageChops.difference(
                source.crop((rx, ry, rx + rw, ry + rh)),
                candidate.crop((rx, ry, rx + rw, ry + rh)),
            ).getbbox()
            is None
        )
        accepted_checks.append({
            "id": str(raw.get("id") or f"accepted-{index}"),
            "rect": list(rect),
            "overlaps_mask": overlap,
            "unchanged": unchanged,
            "passed": unchanged and not overlap,
        })
    issues: list[str] = []
    if outside_bbox is not None:
        issues.append("pixels outside the declared repair mask changed")
    if inside_bbox is None:
        issues.append("the declared repair mask produced no visible change")
    issues.extend(
        f"{item['id']}: accepted context changed or overlaps the repair mask"
        for item in accepted_checks
        if not item["passed"]
    )
    report = {
        "schema_version": 1,
        "family_fingerprint": str(spec.get("family_fingerprint", "")),
        "original": str(original.resolve()),
        "original_sha256": production_contract.file_digest(original),
        "repaired": str(repaired.resolve()),
        "repaired_sha256": production_contract.file_digest(repaired),
        "mask": list(mask),
        "outside_unchanged": outside_bbox is None,
        "inside_changed": inside_bbox is not None,
        "accepted_regions": accepted_checks,
        "issues": issues,
        "passed": not issues,
    }
    if not report["family_fingerprint"]:
        raise ContextRepairError("family_fingerprint is required")
    report["fingerprint"] = production_contract.canonical_digest(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("repaired", type=Path)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        report = prove(args.original.resolve(), args.repaired.resolve(), spec)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"context repair: {'passed' if report['passed'] else 'failed'}")
        return 0 if report["passed"] else 1
    except (OSError, ValueError, json.JSONDecodeError, ContextRepairError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
