#!/usr/bin/env python3
"""Build style, composition, and proof-moment evidence with stale detection."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import asset_quality
import layer_compositor
import production_contract
import proof_review
import runtime_fingerprint
import semantic_qa
import studio
import world_motion


class ProofSystemError(RuntimeError):
    pass


def _style_input_fingerprint(
    root: Path, project: dict[str, Any], state: dict[str, Any]
) -> str:
    candidates: list[dict[str, Any]] = []
    for theme in project.get("creative", {}).get("candidate_themes", []):
        theme_id = str(theme.get("id", ""))
        record = state.get("artifacts", {}).get(f"style:{theme_id}", {})
        path = studio.resolve_path(root, record.get("path", "")).resolve()
        candidates.append({
            "theme": theme,
            "artifact": (
                production_contract.file_digest(path) if path.is_file() else None
            ),
        })
    return production_contract.canonical_digest(candidates)


def _write(path: Path, report: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    studio.atomic_json(path, report)
    return path


def _register(root: Path, kind: str, report_path: Path, report: dict[str, Any]) -> None:
    state = studio.load_state(root)
    state.setdefault("proofs", {})[kind] = {
        "path": studio.portable_path(root, report_path),
        "fingerprint": report["fingerprint"],
        "status": report["status"],
        "passed": report["passed"],
        "updated_at": studio.now_iso(),
    }
    state["updated_at"] = studio.now_iso()
    studio.atomic_json(studio.state_file(root), state)


def style_proof(
    root: Path,
    *,
    approve: str | None = None,
) -> dict[str, Any]:
    project = studio.load_json(root / "project.json")
    themes = project.get("creative", {}).get("candidate_themes", [])
    if not isinstance(themes, list) or len(themes) != 3:
        raise ProofSystemError("style proof requires exactly three candidate themes")
    theme_ids = [str(theme.get("id", "")) for theme in themes]
    if not all(theme_ids) or len(set(theme_ids)) != 3:
        raise ProofSystemError("candidate theme ids must be three unique values")
    state = studio.load_state(root)
    candidates: list[dict[str, Any]] = []
    representative_beats: set[str] = set()
    issues: list[str] = []
    for theme_id in theme_ids:
        artifact_id = f"style:{theme_id}"
        record = state.get("artifacts", {}).get(artifact_id)
        if not isinstance(record, dict):
            issues.append(f"missing {artifact_id}")
            continue
        path = studio.resolve_path(root, record["path"]).resolve()
        if not path.is_file():
            issues.append(f"missing preview file for {artifact_id}")
            continue
        metadata = record.get("metadata", {})
        representative = str(metadata.get("representative_beat_id", ""))
        if not representative:
            issues.append(f"{artifact_id} lacks representative_beat_id")
        else:
            representative_beats.add(representative)
        declared_theme = str(metadata.get("candidate_theme_id", theme_id))
        if declared_theme != theme_id:
            issues.append(f"{artifact_id} declares candidate theme {declared_theme}")
        candidates.append({
            "theme_id": theme_id,
            "artifact_id": artifact_id,
            "path": studio.portable_path(root, path),
            "content_sha256": production_contract.file_digest(path),
            "representative_beat_id": representative,
        })
    if len(representative_beats) > 1:
        issues.append("style candidates do not show the same representative beat")
    if approve and approve not in theme_ids:
        raise ProofSystemError(f"approved theme must be one of {theme_ids}")
    status = (
        "approved"
        if approve and not issues and len(candidates) == 3
        else "pending-human-review"
    )
    payload = {
        "kind": "style",
        "project_id": project.get("project", {}).get("id"),
        "candidate_themes": themes,
        "candidates": candidates,
        "representative_beat_id": (
            next(iter(representative_beats)) if len(representative_beats) == 1 else None
        ),
        "approved_theme_id": approve,
        "issues": issues,
        "status": status,
        "passed": status == "approved",
        "input_fingerprint": _style_input_fingerprint(root, project, state),
    }
    payload["fingerprint"] = production_contract.canonical_digest(payload)
    return payload


def composition_proof(
    root: Path,
    manifest_path: Path,
    *,
    forced: bool = False,
) -> dict[str, Any]:
    project = studio.load_json(root / "project.json")
    manifest = studio.load_json(manifest_path)
    quality = asset_quality.audit_composition_manifest(manifest_path)
    semantic = (
        semantic_qa.audit(project, manifest, root)
        if project.get("semantic_contracts")
        else {
            "contracts": [],
            "issues": [],
            "passed": True,
            "status": "not-declared",
        }
    )
    layout = manifest.get("director", {}).get("annotation_layout", {})
    layout_issues = list(layout.get("issues", [])) if isinstance(layout, dict) else []
    edit_points = manifest.get("edit_points", [])
    world = None
    try:
        world = world_motion.prove(
            manifest_path,
            evidence_dir=root / "proofs" / "composition" / "world",
        )
    except world_motion.WorldMotionError:
        world = None
    issues = list(quality.get("issues", [])) + list(semantic.get("issues", []))
    issues.extend(layout_issues)
    if world is not None:
        issues.extend(world.get("issues", []))
    if not edit_points:
        issues.append("composition has no unified edit points")
    evidence: list[dict[str, Any]] = []
    if not issues:
        duration = float(manifest.get("canvas", {}).get("duration_s", 0))
        samples: list[tuple[str, float]] = [
            ("establish", min(duration, max(0.0, duration * 0.08))),
            ("final", min(duration, max(0.0, duration * 0.88))),
        ]
        for item in edit_points:
            samples.append((str(item.get("id", "edit-point")), float(item["at_s"])))
        for item in manifest.get("proof_moments", []):
            if isinstance(item, dict) and item.get("at_s") is not None:
                samples.append((str(item.get("id", "proof")), float(item["at_s"])))
        seen_samples: set[tuple[str, int]] = set()
        evidence_dir = root / "proofs" / "composition" / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        for sample_id, at_s in samples:
            frame_key = (sample_id, round(at_s * 1000))
            if frame_key in seen_samples:
                continue
            seen_samples.add(frame_key)
            safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", sample_id).strip("-")
            target = evidence_dir / f"{safe_id or 'sample'}-{round(at_s * 1000):06d}.png"
            frame = layer_compositor.render_frame(
                manifest_path, min(duration, max(0.0, at_s))
            )
            frame.save(target)
            evidence.append({
                "id": sample_id,
                "at_s": at_s,
                "path": studio.portable_path(root, target),
                "content_sha256": production_contract.file_digest(target),
            })
    report = {
        "kind": "composition",
        "manifest": studio.portable_path(root, manifest_path),
        "manifest_sha256": production_contract.file_digest(manifest_path),
        "quality": quality,
        "semantic": semantic,
        "annotation_layout": layout,
        "edit_points": edit_points,
        "world_motion": world,
        "issues": issues,
        "evidence": evidence,
        "status": "passed" if not issues else "failed",
        "passed": not issues,
        "cache": {"forced": forced, "reused": False},
        "input_fingerprint": production_contract.canonical_digest({
            "manifest_sha256": production_contract.file_digest(manifest_path),
            "semantic_contracts": project.get("semantic_contracts"),
            "runtime_surface": runtime_fingerprint.build(
                Path(__file__).resolve().parents[1]
            )["surfaces"]["composition"]["fingerprint"],
        }),
    }
    report["fingerprint"] = production_contract.canonical_digest(report)
    return report


def moment_proof(
    root: Path,
    video: Path,
    editorial_plan: Path,
    output_dir: Path,
    review: Path | None = None,
) -> dict[str, Any]:
    raw_path = proof_review.extract(video, editorial_plan, output_dir)
    raw = studio.load_json(raw_path)
    raw["video"] = studio.portable_path(root, video)
    raw["editorial_plan"] = studio.portable_path(root, editorial_plan)
    decisions: dict[str, bool] = {}
    if review:
        value = studio.load_json(review)
        decisions = {
            str(key): bool(status)
            for key, status in value.get("decisions", {}).items()
        }
    issues: list[str] = []
    for moment in raw["proof_moments"]:
        decision = decisions.get(str(moment["id"]))
        moment["review_status"] = (
            "approved" if decision is True
            else "rejected" if decision is False
            else "pending-human-review"
        )
        if decision is not True:
            issues.append(f"{moment['id']}: {moment['review_status']}")
    report = {
        "kind": "moment",
        **raw,
        "review": studio.portable_path(root, review) if review else None,
        "issues": issues,
        "status": "approved" if not issues else "pending-human-review",
        "passed": not issues,
        "input_fingerprint": production_contract.canonical_digest({
            "video_sha256": production_contract.file_digest(video),
            "editorial_plan_sha256": production_contract.file_digest(editorial_plan),
            "review_sha256": (
                production_contract.file_digest(review) if review else None
            ),
        }),
    }
    report["fingerprint"] = production_contract.canonical_digest(report)
    return report


def proof_current(root: Path, kind: str) -> bool:
    state = studio.load_state(root)
    record = state.get("proofs", {}).get(kind)
    if not isinstance(record, dict):
        return False
    path = studio.resolve_path(root, record.get("path", "")).resolve()
    if not path.is_file():
        return False
    report = studio.load_json(path)
    integrity = (
        record.get("fingerprint") == report.get("fingerprint")
        and report.get("fingerprint")
        == production_contract.canonical_digest({
            key: value for key, value in report.items() if key != "fingerprint"
        })
    )
    if not integrity:
        return False
    for evidence in report.get("evidence", []):
        evidence_path = studio.resolve_path(root, evidence.get("path", "")).resolve()
        if (
            not evidence_path.is_file()
            or production_contract.file_digest(evidence_path)
            != evidence.get("content_sha256")
        ):
            return False
    project = studio.load_json(root / "project.json")
    if kind == "style":
        current_input = _style_input_fingerprint(root, project, state)
    elif kind == "composition":
        manifest = studio.resolve_path(root, report.get("manifest", "")).resolve()
        if not manifest.is_file():
            return False
        current_input = production_contract.canonical_digest({
            "manifest_sha256": production_contract.file_digest(manifest),
            "semantic_contracts": project.get("semantic_contracts"),
            "runtime_surface": runtime_fingerprint.build(
                Path(__file__).resolve().parents[1]
            )["surfaces"]["composition"]["fingerprint"],
        })
    else:
        video = studio.resolve_path(root, report.get("video", "")).resolve()
        editorial = studio.resolve_path(
            root, report.get("editorial_plan", "")
        ).resolve()
        if not video.is_file() or not editorial.is_file():
            return False
        review_path = (
            studio.resolve_path(root, report["review"]).resolve()
            if report.get("review")
            else None
        )
        if review_path is not None and not review_path.is_file():
            return False
        current_input = production_contract.canonical_digest({
            "video_sha256": production_contract.file_digest(video),
            "editorial_plan_sha256": production_contract.file_digest(editorial),
            "review_sha256": (
                production_contract.file_digest(review_path)
                if review_path is not None else None
            ),
        })
    return current_input == report.get("input_fingerprint")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--register", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)
    style = subparsers.add_parser("style")
    style.add_argument("--approve")
    composition = subparsers.add_parser("composition")
    composition.add_argument("manifest", type=Path)
    composition.add_argument("--force", action="store_true")
    moment = subparsers.add_parser("moment")
    moment.add_argument("video", type=Path)
    moment.add_argument("editorial_plan", type=Path)
    moment.add_argument("--review", type=Path)
    current = subparsers.add_parser("current")
    current.add_argument("kind", choices=["style", "composition", "moment"])
    args = parser.parse_args()
    root = args.project_dir.resolve()
    try:
        if args.command == "current":
            is_current = proof_current(root, args.kind)
            print("current" if is_current else "stale")
            return 0 if is_current else 1
        output_dir = root / "proofs" / args.command
        if args.command == "style":
            report = style_proof(root, approve=args.approve)
        elif args.command == "composition":
            requested_manifest = args.manifest.resolve()
            if not args.force and proof_current(root, "composition"):
                state = studio.load_state(root)
                record = state.get("proofs", {}).get("composition", {})
                current_report = studio.load_json(
                    studio.resolve_path(root, record.get("path", "")).resolve()
                )
                recorded_manifest = studio.resolve_path(
                    root, current_report.get("manifest", "")
                ).resolve()
                if recorded_manifest == requested_manifest:
                    print(
                        "composition proof: reused "
                        f"({record.get('path')}, {record.get('fingerprint', '')[:12]})"
                    )
                    return 0
            report = composition_proof(
                root, requested_manifest, forced=bool(args.force)
            )
        else:
            report = moment_proof(
                root,
                args.video.resolve(),
                args.editorial_plan.resolve(),
                output_dir / "frames",
                args.review.resolve() if args.review else None,
            )
        report_path = _write(output_dir / "proof.json", report)
        if args.register:
            _register(root, args.command, report_path, report)
        print(
            f"{args.command} proof: {report['status']} "
            f"({report_path}, {report['fingerprint'][:12]})"
        )
        return 0 if report["passed"] else 1
    except (
        OSError,
        ValueError,
        KeyError,
        studio.StudioError,
        ProofSystemError,
        proof_review.ProofReviewError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
