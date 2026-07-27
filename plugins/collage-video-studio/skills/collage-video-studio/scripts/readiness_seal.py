#!/usr/bin/env python3
"""Create and verify a render-readiness seal over every delivery-critical surface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import production_contract
import runtime_fingerprint
import studio


REQUIRED_SURFACES = (
    "project",
    "storyboard",
    "assets",
    "audio",
    "timing",
    "subtitles",
    "composition-proof",
    "style-proof",
    "runtime",
)


class ReadinessSealError(RuntimeError):
    pass


def _artifact_snapshot(root: Path, state: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for artifact_id, record in sorted(state.get("artifacts", {}).items()):
        if not isinstance(record, dict):
            continue
        path = studio.resolve_path(root, str(record.get("path", ""))).resolve()
        if not path.is_file():
            raise ReadinessSealError(f"missing registered artifact: {artifact_id}")
        result.append({
            "id": artifact_id,
            "path": studio.portable_path(root, path),
            "content_sha256": production_contract.file_digest(path),
            "job_fingerprint": record.get("job_fingerprint")
            or record.get("metadata", {}).get("job_fingerprint"),
            "timing_path": record.get("metadata", {}).get("timing_path"),
        })
    return result


def _proof_snapshot(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    proofs: dict[str, Any] = {}
    for kind in ("style", "composition"):
        record = state.get("proofs", {}).get(kind)
        if not isinstance(record, dict) or not record.get("passed"):
            raise ReadinessSealError(f"{kind} proof is missing or not passed")
        path = studio.resolve_path(root, str(record.get("path", ""))).resolve()
        if not path.is_file():
            raise ReadinessSealError(f"{kind} proof file is missing")
        report = studio.load_json(path)
        if report.get("fingerprint") != record.get("fingerprint"):
            raise ReadinessSealError(f"{kind} proof registration is stale")
        proofs[kind] = {
            "path": studio.portable_path(root, path),
            "content_sha256": production_contract.file_digest(path),
            "fingerprint": report.get("fingerprint"),
        }
    return proofs


def _surface_file(root: Path, path: Path, label: str) -> dict[str, str]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ReadinessSealError(f"missing {label} surface: {resolved}")
    return {
        "path": studio.portable_path(root, resolved),
        "content_sha256": production_contract.file_digest(resolved),
    }


def build_inputs(
    root: Path,
    *,
    subtitle_manifest: Path,
    composition_manifest: Path,
) -> dict[str, Any]:
    project = studio.load_project(root)
    state = studio.load_state(root)
    skill_root = Path(__file__).resolve().parents[1]
    runtime_path = skill_root / "runtime-build.json"
    current_runtime = runtime_fingerprint.build(skill_root)
    if runtime_path.is_file():
        recorded_runtime = studio.load_json(runtime_path)
        if recorded_runtime.get("fingerprint") != current_runtime.get("fingerprint"):
            raise ReadinessSealError("runtime-build.json is stale")
    artifacts = _artifact_snapshot(root, state)
    voice = [item for item in artifacts if item["id"].startswith("voice:")]
    if not voice:
        raise ReadinessSealError("readiness seal requires registered narration audio")
    timing_files: list[dict[str, str]] = []
    for item in voice:
        raw = item.get("timing_path")
        if not raw:
            raise ReadinessSealError(f"{item['id']} has no measured timing manifest")
        timing_path = studio.resolve_path(root, str(raw)).resolve()
        timing_files.append(_surface_file(root, timing_path, f"{item['id']} timing"))
    storyboard_path = root / "build" / "storyboard.json"
    proofs = _proof_snapshot(root, state)
    result = {
        "project": _surface_file(root, root / "project.json", "project"),
        "storyboard": _surface_file(root, storyboard_path, "storyboard"),
        "assets": {
            "artifacts": artifacts,
            "fingerprint": production_contract.canonical_digest(artifacts),
        },
        "audio": {
            "voice_artifact_ids": [item["id"] for item in voice],
            "fingerprint": production_contract.canonical_digest(voice),
        },
        "timing": {
            "files": timing_files,
            "fingerprint": production_contract.canonical_digest(timing_files),
        },
        "subtitles": _surface_file(root, subtitle_manifest, "subtitle manifest"),
        "composition-proof": proofs["composition"],
        "style-proof": proofs["style"],
        "composition": _surface_file(
            root, composition_manifest, "composition manifest"
        ),
        "runtime": {
            "path": studio.portable_path(root, runtime_path),
            "fingerprint": current_runtime["fingerprint"],
            "surface_fingerprints": {
                key: value["fingerprint"]
                for key, value in current_runtime["surfaces"].items()
            },
        },
        "approvals": {
            gate: state.get("approvals", {}).get(gate)
            for gate in ("story", "style")
        },
        "production": project.get("production"),
    }
    missing_approvals = [
        gate for gate, record in result["approvals"].items()
        if not isinstance(record, dict)
    ]
    if missing_approvals:
        raise ReadinessSealError(
            "missing approvals: " + ", ".join(missing_approvals)
        )
    return result


def create(
    root: Path,
    *,
    subtitle_manifest: Path,
    composition_manifest: Path,
    note: str,
    output: Path | None = None,
) -> dict[str, Any]:
    if not note.strip():
        raise ReadinessSealError("readiness sealing requires a human-attributable note")
    inputs = build_inputs(
        root,
        subtitle_manifest=subtitle_manifest,
        composition_manifest=composition_manifest,
    )
    report = {
        "schema_version": 1,
        "status": "sealed",
        "project_id": studio.load_project(root)["project"]["id"],
        "created_at": studio.now_iso(),
        "note": note.strip(),
        "required_surfaces": list(REQUIRED_SURFACES),
        "inputs": inputs,
        "input_fingerprint": production_contract.canonical_digest(inputs),
    }
    report["fingerprint"] = production_contract.canonical_digest(report)
    target = output or root / "build" / "readiness-seal.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    studio.atomic_json(target, report)
    state = studio.load_state(root)
    state["readiness_seal"] = {
        "path": studio.portable_path(root, target),
        "fingerprint": report["fingerprint"],
        "input_fingerprint": report["input_fingerprint"],
        "status": "sealed",
    }
    state["updated_at"] = studio.now_iso()
    studio.atomic_json(studio.state_file(root), state)
    return report


def verify(root: Path) -> dict[str, Any]:
    state = studio.load_state(root)
    record = state.get("readiness_seal")
    if not isinstance(record, dict):
        raise ReadinessSealError("readiness seal is not registered")
    path = studio.resolve_path(root, str(record.get("path", ""))).resolve()
    if not path.is_file():
        raise ReadinessSealError("registered readiness seal file is missing")
    report = studio.load_json(path)
    stored_integrity = production_contract.canonical_digest({
        key: value for key, value in report.items() if key != "fingerprint"
    })
    if stored_integrity != report.get("fingerprint"):
        raise ReadinessSealError("readiness seal content was modified")
    inputs = report.get("inputs", {})
    subtitle_path = studio.resolve_path(
        root, inputs.get("subtitles", {}).get("path", "")
    )
    composition_path = studio.resolve_path(
        root, inputs.get("composition", {}).get("path", "")
    )
    current = build_inputs(
        root,
        subtitle_manifest=subtitle_path,
        composition_manifest=composition_path,
    )
    current_fingerprint = production_contract.canonical_digest(current)
    passed = (
        current_fingerprint == report.get("input_fingerprint")
        and record.get("fingerprint") == report.get("fingerprint")
    )
    return {
        "path": str(path),
        "recorded_input_fingerprint": report.get("input_fingerprint"),
        "current_input_fingerprint": current_fingerprint,
        "passed": passed,
        "status": "current" if passed else "stale",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    seal = sub.add_parser("seal")
    seal.add_argument("project_dir", type=Path)
    seal.add_argument("--subtitles", type=Path, required=True)
    seal.add_argument("--composition", type=Path, required=True)
    seal.add_argument("--note", required=True)
    seal.add_argument("--output", type=Path)
    check = sub.add_parser("verify")
    check.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    try:
        root = args.project_dir.resolve()
        if args.command == "seal":
            report = create(
                root,
                subtitle_manifest=args.subtitles.resolve(),
                composition_manifest=args.composition.resolve(),
                note=args.note,
                output=args.output.resolve() if args.output else None,
            )
            print(f"readiness seal: {report['fingerprint']}")
            return 0
        report = verify(root)
        print(f"readiness seal: {report['status']}")
        return 0 if report["passed"] else 1
    except (
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
        studio.StudioError,
        ReadinessSealError,
    ) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
