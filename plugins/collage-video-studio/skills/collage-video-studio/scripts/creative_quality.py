#!/usr/bin/env python3
"""Audit portfolio-level visual diversity, provenance, depth, and shot coverage."""

from __future__ import annotations

import argparse
import math
from collections import Counter
from pathlib import Path
from typing import Any

import production_contract
import studio


ALLOWED_PRIMARY_PROVENANCE = {
    "provider-generated",
    "user-supplied",
    "licensed-stock",
    "commissioned-art",
}
ALLOWED_DERIVATIVE_PROVENANCE = {
    "deterministic-derivative",
    "registered-family-derivative",
    "local-vector",
}
SHOT_SCALES = {"wide", "medium", "close", "detail"}
DEPTH_ROLES = {"rear", "mid", "subject", "front", "near"}
PROFILE_FLOORS: dict[str, dict[str, float | int]] = {
    "draft": {
        "shots_per_beat": 1.0,
        "shot_scales": 2,
        "max_pattern_ratio": 0.75,
        "max_environment_ratio": 0.85,
        "max_prominent_asset_ratio": 0.80,
        "min_environments": 2,
    },
    "balanced": {
        "shots_per_beat": 1.5,
        "shot_scales": 3,
        "max_pattern_ratio": 0.55,
        "max_environment_ratio": 0.67,
        "max_prominent_asset_ratio": 0.60,
        "min_environments": 3,
    },
    "full-depth": {
        "shots_per_beat": 2.0,
        "shot_scales": 3,
        "max_pattern_ratio": 0.45,
        "max_environment_ratio": 0.55,
        "max_prominent_asset_ratio": 0.50,
        "min_environments": 3,
    },
}


class CreativeQualityError(RuntimeError):
    pass


def _artifact_path(root: Path, record: dict[str, Any]) -> Path:
    return studio.resolve_path(root, str(record.get("path", ""))).resolve()


def _provenance_ok(
    artifact_id: str,
    artifacts: dict[str, Any],
    *,
    visiting: set[str] | None = None,
) -> tuple[bool, str]:
    visiting = visiting or set()
    if artifact_id in visiting:
        return False, f"{artifact_id}: provenance cycle"
    record = artifacts.get(artifact_id)
    if not isinstance(record, dict):
        return False, f"{artifact_id}: source artifact is not registered"
    metadata = record.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    if metadata.get("placeholder") is True:
        return False, f"{artifact_id}: placeholder media cannot enter production"
    provenance = str(metadata.get("provenance_class", "")).strip()
    if provenance in ALLOWED_PRIMARY_PROVENANCE:
        if provenance == "provider-generated":
            if not metadata.get("provider") or not metadata.get("model"):
                return (
                    False,
                    f"{artifact_id}: provider-generated media needs provider and model",
                )
        return True, ""
    if provenance in ALLOWED_DERIVATIVE_PROVENANCE:
        raw_sources = metadata.get("source_artifact_ids", [])
        if not isinstance(raw_sources, list) or not raw_sources:
            return (
                False,
                f"{artifact_id}: {provenance} needs source_artifact_ids",
            )
        next_visiting = visiting | {artifact_id}
        failures: list[str] = []
        for source_id in raw_sources:
            passed, detail = _provenance_ok(
                str(source_id), artifacts, visiting=next_visiting
            )
            if not passed:
                failures.append(detail)
        if failures:
            return False, "; ".join(failures)
        return True, ""
    return (
        False,
        f"{artifact_id}: unsupported or missing provenance_class {provenance!r}",
    )


def _layer_role(layer: dict[str, Any]) -> str:
    explicit = str(layer.get("role", "")).lower()
    if explicit:
        return explicit
    identifier = str(layer.get("id", "")).lower()
    for token, role in (
        ("background", "rear"),
        ("rear", "rear"),
        ("far", "rear"),
        ("ground", "mid"),
        ("mid", "mid"),
        ("subject", "subject"),
        ("character", "subject"),
        ("portrait", "subject"),
        ("person", "subject"),
        ("hero", "subject"),
        ("foreground", "front"),
        ("front", "front"),
        ("near", "near"),
    ):
        if token in identifier:
            return role
    return ""


def _prominent_digest(
    root: Path,
    manifest_path: Path,
    layer: dict[str, Any],
) -> str | None:
    if _layer_role(layer) != "subject":
        return None
    raw = layer.get("path")
    if not raw:
        return None
    path = studio.resolve_path(manifest_path.parent, str(raw)).resolve()
    if not path.is_file():
        return None
    return production_contract.file_digest(path)


def _ratio(counter: Counter[str], total: int) -> float:
    if total <= 0 or not counter:
        return 0.0
    return max(counter.values()) / total


def audit(root: Path, *, strict: bool = True) -> dict[str, Any]:
    root = root.resolve()
    project = studio.load_project(root)
    state = studio.load_state(root)
    production = production_contract.profile_config(project)
    profile = str(production["profile"] if production else "draft")
    floors = PROFILE_FLOORS[profile]
    artifacts = state.get("artifacts", {})
    if not isinstance(artifacts, dict):
        artifacts = {}

    issues: list[str] = []
    warnings: list[str] = []
    packages: list[dict[str, Any]] = []
    scales: Counter[str] = Counter()
    patterns: Counter[str] = Counter()
    environments: Counter[str] = Counter()
    prominent: Counter[str] = Counter()
    depth_counts: Counter[str] = Counter()
    covered_beats: Counter[str] = Counter()

    expected = list(studio.iter_shots(project))
    for beat, shot in expected:
        shot_id = str(shot.get("id", "")).strip()
        beat_id = str(beat.get("id", "")).strip()
        artifact_id = studio.artifact_key("layers", beat, shot)
        record = artifacts.get(artifact_id, {})
        if not isinstance(record, dict):
            issues.append(f"{artifact_id}: layer package is not registered")
            continue
        manifest_path = _artifact_path(root, record)
        if not manifest_path.is_file():
            issues.append(f"{artifact_id}: layer manifest is missing")
            continue
        manifest = studio.load_json(manifest_path)
        asset_snapshot = production_contract.composition_asset_snapshot(
            manifest_path
        )
        if not asset_snapshot["passed"]:
            issues.append(f"{artifact_id}: nested composition media is missing")
        creative = manifest.get("creative", {})
        if not isinstance(creative, dict):
            creative = {}
        if creative.get("production_ready") is not True:
            issues.append(f"{artifact_id}: creative.production_ready must be true")
        director_plans = manifest.get("director_plans", {})
        missing_aspects = sorted(
            {"16:9", "9:16", "1:1"}
            - (
                set(director_plans)
                if isinstance(director_plans, dict)
                else set()
            )
        )
        if missing_aspects:
            issues.append(
                f"{artifact_id}: responsive director plans missing "
                + ", ".join(missing_aspects)
            )
        scale = str(
            creative.get("shot_scale")
            or shot.get("shot_scale")
            or shot.get("direction", {}).get("shot_scale")
            or ""
        ).strip()
        if scale not in SHOT_SCALES:
            issues.append(
                f"{artifact_id}: shot_scale must be wide, medium, close, or detail"
            )
        else:
            scales[scale] += 1
        pattern = str(creative.get("composition_pattern", "")).strip()
        environment = str(creative.get("environment_id", "")).strip()
        if not pattern:
            issues.append(f"{artifact_id}: composition_pattern is required")
        else:
            patterns[pattern] += 1
        if not environment:
            issues.append(f"{artifact_id}: environment_id is required")
        else:
            environments[environment] += 1
        source_ids = creative.get("source_artifact_ids", [])
        if not isinstance(source_ids, list) or not source_ids:
            issues.append(f"{artifact_id}: source_artifact_ids is required")
            source_ids = []
        provenance_failures: list[str] = []
        for source_id in source_ids:
            passed, detail = _provenance_ok(str(source_id), artifacts)
            if not passed:
                provenance_failures.append(detail)
        issues.extend(provenance_failures)

        roles = Counter(
            role
            for layer in manifest.get("layers", [])
            if isinstance(layer, dict) and (role := _layer_role(layer))
        )
        for role, count in roles.items():
            depth_counts[role] += count
        required_roles = {"rear", "subject", "front"}
        if profile == "draft":
            required_roles = {"rear", "subject"}
        missing_roles = sorted(required_roles - set(roles))
        if missing_roles:
            issues.append(
                f"{artifact_id}: missing visible depth roles {', '.join(missing_roles)}"
            )
        for layer in manifest.get("layers", []):
            if not isinstance(layer, dict):
                continue
            digest = _prominent_digest(root, manifest_path, layer)
            if digest:
                prominent[digest] += 1
        covered_beats[beat_id] += 1
        packages.append({
            "artifact_id": artifact_id,
            "beat_id": beat_id,
            "shot_id": shot_id,
            "manifest": studio.portable_path(root, manifest_path),
            "manifest_sha256": production_contract.file_digest(manifest_path),
            "asset_fingerprint": asset_snapshot["fingerprint"],
            "shot_scale": scale,
            "composition_pattern": pattern,
            "environment_id": environment,
            "source_artifact_ids": [str(value) for value in source_ids],
            "depth_roles": dict(roles),
        })

    shot_count = len(expected)
    beat_count = max(1, len(project.get("beats", [])))
    shots_per_beat = shot_count / beat_count
    if shots_per_beat + 1e-9 < float(floors["shots_per_beat"]):
        issues.append(
            f"{profile}: {shots_per_beat:.2f} shots/beat is below "
            f"{float(floors['shots_per_beat']):.2f}"
        )
    if len(scales) < int(floors["shot_scales"]):
        issues.append(
            f"{profile}: needs {int(floors['shot_scales'])} shot scales; "
            f"found {sorted(scales)}"
        )
    required_environments = min(
        int(floors["min_environments"]),
        max(1, math.ceil(beat_count / 2)),
    )
    if len(environments) < required_environments:
        issues.append(
            f"{profile}: needs at least {required_environments} environments; "
            f"found {len(environments)}"
        )
    pattern_ratio = _ratio(patterns, shot_count)
    environment_ratio = _ratio(environments, shot_count)
    prominent_ratio = _ratio(prominent, shot_count)
    if pattern_ratio > float(floors["max_pattern_ratio"]):
        issues.append(
            f"dominant composition pattern repeats in {pattern_ratio:.1%} of shots"
        )
    if environment_ratio > float(floors["max_environment_ratio"]):
        issues.append(
            f"dominant environment repeats in {environment_ratio:.1%} of shots"
        )
    if prominent_ratio > float(floors["max_prominent_asset_ratio"]):
        issues.append(
            f"identical prominent subject asset repeats in {prominent_ratio:.1%} "
            "of shots; author registered pose/state variation"
        )
    if shot_count and len(packages) != shot_count:
        issues.append(
            f"composition coverage {len(packages)}/{shot_count} shots"
        )

    production_attempts = [
        item
        for item in state.get("attempts", [])
        if isinstance(item, dict)
        and item.get("group") == "visual_source"
        and not str(item.get("job_id", "")).startswith("style:")
    ]
    if strict and not production_attempts:
        warnings.append(
            "no metered production visual attempts were recorded; "
            "user-supplied or licensed sources must carry explicit provenance"
        )

    metrics = {
        "profile": profile,
        "beats": beat_count,
        "shots": shot_count,
        "packages": len(packages),
        "shots_per_beat": shots_per_beat,
        "shot_scales": dict(scales),
        "composition_patterns": dict(patterns),
        "environments": dict(environments),
        "depth_roles": dict(depth_counts),
        "dominant_pattern_ratio": pattern_ratio,
        "dominant_environment_ratio": environment_ratio,
        "identical_prominent_asset_ratio": prominent_ratio,
        "production_visual_attempts": len(production_attempts),
    }
    report = {
        "schema_version": 1,
        "kind": "creative-quality",
        "project_id": project["project"]["id"],
        "standard": "portfolio",
        "packages": packages,
        "metrics": metrics,
        "issues": sorted(set(issues)),
        "warnings": sorted(set(warnings)),
        "passed": not issues,
        "status": "passed" if not issues else "failed",
        "input_fingerprint": production_contract.canonical_digest({
            "project": production_contract.file_digest(root / "project.json"),
            "packages": [
                (item["artifact_id"], item["manifest_sha256"])
                for item in packages
            ],
            "package_assets": [
                (item["artifact_id"], item["asset_fingerprint"])
                for item in packages
            ],
            "artifact_provenance": {
                key: value.get("metadata", {})
                for key, value in sorted(artifacts.items())
                if isinstance(value, dict)
            },
        }),
    }
    report["fingerprint"] = production_contract.canonical_digest(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("qa/creative-quality.json"),
    )
    parser.add_argument("--no-strict", action="store_true")
    args = parser.parse_args()
    root = args.project_dir.resolve()
    try:
        report = audit(root, strict=not args.no_strict)
        output = args.output
        if not output.is_absolute():
            output = root / output
        studio.atomic_json(output, report)
        print(
            f"creative quality: {report['status']} "
            f"({len(report['issues'])} issue(s))"
        )
        return 0 if report["passed"] else 1
    except (OSError, ValueError, KeyError, CreativeQualityError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
