#!/usr/bin/env python3
"""Validate and prove persistent looping worlds, anchors, occlusion, and trajectories."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageChops, ImageDraw

import production_contract


ASPECTS = ("16:9", "9:16", "1:1")
STRIP_ROLES = ("far", "mid", "ground", "near")
ANCHOR_SPACES = ("screen", "world")


class WorldMotionError(RuntimeError):
    pass


def _nodes(root: dict[str, Any]) -> Iterable[dict[str, Any]]:
    yield root
    for child in root.get("children", []):
        if isinstance(child, dict):
            yield from _nodes(child)


def _number(value: Any, label: str, minimum: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise WorldMotionError(f"{label} must be numeric") from exc
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise WorldMotionError(f"{label} is outside its allowed range")
    return result


def _direction_sign(direction: str) -> int:
    if direction == "left":
        return -1
    if direction == "right":
        return 1
    raise WorldMotionError("world direction must be left or right")


def _source_path(manifest_path: Path, raw: str) -> Path:
    path = Path(raw)
    return path.resolve() if path.is_absolute() else (manifest_path.parent / path).resolve()


def _edge_metrics(image: Image.Image, band: int) -> dict[str, float]:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    band = max(1, min(band, width // 4))
    left = rgba.crop((0, 0, band, height))
    right = rgba.crop((width - band, 0, width, height))
    diff = ImageChops.difference(left, right)
    pixels = getattr(diff, "get_flattened_data", diff.getdata)
    values = list(pixels())
    channel_values = [channel for pixel in values for channel in pixel]
    rgb = [channel for pixel in values for channel in pixel[:3]]
    alpha = [pixel[3] for pixel in values]
    return {
        "rgb_mean": round(sum(rgb) / max(1, len(rgb)), 6),
        "rgb_max": float(max(rgb, default=0)),
        "alpha_mean": round(sum(alpha) / max(1, len(alpha)), 6),
        "alpha_max": float(max(alpha, default=0)),
        "all_channel_max": float(max(channel_values, default=0)),
    }


def _stitch_sheet(image: Image.Image, output: Path) -> None:
    rgba = image.convert("RGBA")
    sheet = Image.new("RGBA", (rgba.width * 3, rgba.height), (0, 0, 0, 0))
    for index in range(3):
        sheet.alpha_composite(rgba, (index * rgba.width, 0))
    brush = ImageDraw.Draw(sheet)
    for x in (rgba.width, rgba.width * 2):
        brush.line((x, 0, x, rgba.height), fill=(255, 56, 56, 180), width=1)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output)


def _validate_world_node(
    manifest_path: Path,
    manifest: dict[str, Any],
    node: dict[str, Any],
    evidence_dir: Path | None,
) -> dict[str, Any]:
    world = node.get("world")
    if not isinstance(world, dict) or world.get("pattern") != "looping-environment":
        raise WorldMotionError(f"{node.get('id', '<world>')}: invalid world contract")
    duration = _number(
        world.get("duration_s", manifest.get("canvas", {}).get("duration_s")),
        "world.duration_s",
        0.001,
    )
    distance_viewports = _number(
        world.get("distance_viewports"), "world.distance_viewports", 1.0
    )
    direction = str(world.get("direction", ""))
    sign = _direction_sign(direction)
    plans = manifest.get("director_plans")
    if not isinstance(plans, dict) or set(plans) != set(ASPECTS):
        raise WorldMotionError("looping world requires 16:9, 9:16, and 1:1 director plans")
    children = [item for item in node.get("children", []) if isinstance(item, dict)]
    by_id = {str(item.get("id")): item for item in children}
    strips = [item for item in children if isinstance(item.get("looping_strip"), dict)]
    roles = [str(item["looping_strip"].get("role", "")) for item in strips]
    if not {"far", "ground"}.issubset(roles):
        raise WorldMotionError("looping world requires at least far and ground strips")
    if len(roles) != len(set(roles)) or any(role not in STRIP_ROLES for role in roles):
        raise WorldMotionError("looping strip roles must be unique far/mid/ground/near values")
    speed_order = {"far": 0, "mid": 1, "ground": 2, "near": 3}
    ordered = sorted(strips, key=lambda item: speed_order[item["looping_strip"]["role"]])
    factors = [
        _number(item["looping_strip"].get("speed_factor"), "speed_factor", 0.001)
        for item in ordered
    ]
    if any(right <= left for left, right in zip(factors, factors[1:])):
        raise WorldMotionError("absolute strip speed must strictly increase with depth")

    participants = world.get("participants")
    if not isinstance(participants, list) or not participants:
        raise WorldMotionError("looping world requires at least one participant")
    participant_ids: set[str] = set()
    tracked = str(world.get("tracked_subject_id", ""))
    for participant in participants:
        target_id = str(participant.get("target_id", ""))
        if not target_id or target_id not in by_id:
            raise WorldMotionError(f"world participant target is missing: {target_id!r}")
        if target_id in participant_ids:
            raise WorldMotionError(f"duplicate world participant: {target_id}")
        participant_ids.add(target_id)
        if participant.get("anchor_space") not in ANCHOR_SPACES:
            raise WorldMotionError(
                f"{target_id}: anchor_space must be screen or world"
            )
    if tracked not in participant_ids:
        raise WorldMotionError("tracked_subject_id must name a declared participant")

    near_ids = {
        str(item.get("id"))
        for item in strips
        if item["looping_strip"].get("role") == "near"
    }
    for relation in world.get("near_occlusions", []):
        occluder = str(relation.get("occluder_id", ""))
        target = str(relation.get("target_id", ""))
        if occluder not in near_ids or target not in participant_ids:
            raise WorldMotionError("near occlusion must bind a near strip to a participant")
        if float(by_id[occluder].get("z", 0)) <= float(by_id[target].get("z", 0)):
            raise WorldMotionError("near occluder must have a higher z than its target")

    strip_reports: list[dict[str, Any]] = []
    for strip in strips:
        contract = strip["looping_strip"]
        path_raw = str(strip.get("path", ""))
        source = _source_path(manifest_path, path_raw)
        if not source.is_file():
            raise WorldMotionError(f"{strip.get('id')}: missing strip source {source}")
        image = Image.open(source).convert("RGBA")
        band = int(contract.get("edge_band_px", 4))
        metrics = _edge_metrics(image, band)
        rgb_limit = _number(contract.get("max_rgb_edge_delta", 3.0), "rgb limit", 0)
        alpha_limit = _number(
            contract.get("max_alpha_edge_delta", 2.0), "alpha limit", 0
        )
        seam_passed = (
            metrics["rgb_max"] <= rgb_limit
            and metrics["alpha_max"] <= alpha_limit
        )
        aspect_coverage: dict[str, Any] = {}
        render_height = _number(
            contract.get("render_height_px"), "render_height_px", 1.0
        )
        resolved_width = image.width / image.height * render_height
        for aspect in ASPECTS:
            viewport = int(plans[aspect].get("width", manifest["canvas"]["width"]))
            overscan = int(contract.get("overscan_px", 2))
            span = resolved_width / viewport
            copies = math.ceil((viewport + 2 * overscan) / resolved_width) + 2
            aspect_coverage[aspect] = {
                "viewport_width": viewport,
                "resolved_tile_width": round(resolved_width, 4),
                "tile_span_viewports": round(span, 6),
                "copy_count": copies,
                "passed": span >= 1.0 and copies >= 3,
            }
        stitch_path = None
        if evidence_dir is not None:
            stitch_path = evidence_dir / f"{strip['id']}-three-tile.png"
            _stitch_sheet(image, stitch_path)
        report = {
            "id": strip["id"],
            "role": contract["role"],
            "source": path_raw,
            "source_sha256": production_contract.file_digest(source),
            "speed_factor": float(contract["speed_factor"]),
            "edge_metrics": metrics,
            "seam_passed": seam_passed,
            "coverage": aspect_coverage,
            "stitch_sheet": (
                stitch_path.name if stitch_path is not None else None
            ),
        }
        report["passed"] = seam_passed and all(
            item["passed"] for item in aspect_coverage.values()
        )
        strip_reports.append(report)

    proof_times = world.get("proof_times_s")
    if (
        not isinstance(proof_times, dict)
        or set(proof_times) != {"before", "seam", "after"}
    ):
        raise WorldMotionError("world proof_times_s must declare before, seam, and after")
    times = [float(proof_times[key]) for key in ("before", "seam", "after")]
    if not (0 <= times[0] < times[1] < times[2] <= duration):
        raise WorldMotionError("world proof times must be ordered inside the scene")
    viewport_width = float(manifest["canvas"]["width"])
    signed_total = sign * distance_viewports * viewport_width
    samples = [
        {
            "kind": kind,
            "at_s": time_s,
            "world_displacement_px": round(signed_total * time_s / duration, 6),
        }
        for kind, time_s in zip(("before", "seam", "after"), times, strict=True)
    ]

    trajectory_reports: list[dict[str, Any]] = []
    for contract in world.get("trajectories", []):
        target = str(contract.get("target_id", ""))
        if target not in participant_ids:
            raise WorldMotionError(f"trajectory target is not a participant: {target}")
        expected = str(contract.get("direction", direction))
        expected_sign = _direction_sign(expected)
        minimum = _number(
            contract.get("min_camera_compensated_delta_px", viewport_width),
            "trajectory minimum",
            0,
        )
        participant = next(
            item for item in participants if item.get("target_id") == target
        )
        anchor_space = participant["anchor_space"]
        actual = signed_total if anchor_space == "world" else 0.0
        direction_passed = actual * expected_sign > 0
        magnitude_passed = abs(actual) >= minimum
        trajectory_reports.append({
            "target_id": target,
            "anchor_space": anchor_space,
            "expected_direction": expected,
            "camera_compensated_delta_px": round(actual, 6),
            "direction_passed": direction_passed,
            "magnitude_passed": magnitude_passed,
            "passed": direction_passed and magnitude_passed,
        })

    final_order = world.get("final_order", [])
    if final_order:
        if set(final_order) != participant_ids or len(final_order) != len(participant_ids):
            raise WorldMotionError("final_order must list every participant exactly once")
        positions = {
            str(item["target_id"]): float(item.get("base_x", 0))
            + (signed_total if item["anchor_space"] == "world" else 0)
            for item in participants
        }
        observed_order = [
            key for key, _ in sorted(positions.items(), key=lambda item: item[1])
        ]
        order_passed = observed_order == final_order
    else:
        observed_order = []
        order_passed = True

    issues: list[str] = []
    issues.extend(
        f"{item['id']}: seam or coverage failed"
        for item in strip_reports
        if not item["passed"]
    )
    issues.extend(
        f"{item['target_id']}: signed trajectory failed"
        for item in trajectory_reports
        if not item["passed"]
    )
    if not order_passed:
        issues.append("declared final participant order was not reached")
    result = {
        "id": node.get("id"),
        "direction": direction,
        "distance_viewports": distance_viewports,
        "duration_s": duration,
        "tracked_subject_id": tracked,
        "participants": participants,
        "near_occlusions": world.get("near_occlusions", []),
        "strips": strip_reports,
        "proof_samples": samples,
        "trajectories": trajectory_reports,
        "declared_final_order": final_order,
        "observed_final_order": observed_order,
        "issues": issues,
        "passed": not issues,
    }
    result["fingerprint"] = production_contract.canonical_digest(result)
    return result


def prove(
    manifest_path: Path,
    output: Path | None = None,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise WorldMotionError("manifest must contain an object")
    composition = manifest.get("composition")
    if not isinstance(composition, dict):
        raise WorldMotionError("manifest.composition must be an object")
    worlds = [
        node
        for node in _nodes(composition)
        if isinstance(node.get("world"), dict)
        and node["world"].get("pattern") == "looping-environment"
    ]
    if not worlds:
        raise WorldMotionError("manifest has no looping-environment world")
    reports = [
        _validate_world_node(manifest_path, manifest, node, evidence_dir)
        for node in worlds
    ]
    report = {
        "schema_version": 1,
        "manifest": manifest_path.name,
        "manifest_sha256": production_contract.file_digest(manifest_path),
        "worlds": reports,
        "issues": [
            f"{item['id']}: {issue}"
            for item in reports
            for issue in item["issues"]
        ],
    }
    report["passed"] = not report["issues"]
    report["fingerprint"] = production_contract.canonical_digest(report)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()
    try:
        report = prove(
            args.manifest.resolve(),
            args.output.resolve() if args.output else None,
            args.evidence_dir.resolve() if args.evidence_dir else None,
        )
        print(
            f"world motion proof: {'passed' if report['passed'] else 'failed'} "
            f"({report['fingerprint'][:18]})"
        )
        return 0 if report["passed"] else 1
    except (OSError, ValueError, KeyError, json.JSONDecodeError, WorldMotionError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
