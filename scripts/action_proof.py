#!/usr/bin/env python3
"""Create and approve a fingerprint-bound 3–5 second real-motion proof."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any

import production_contract
import production_remotion
import studio


class ActionProofError(RuntimeError):
    pass


def _paths(root: Path) -> tuple[Path, Path, Path]:
    folder = root / "proofs" / "action"
    return folder, folder / "preview.mp4", folder / "contact-sheet.jpg"


def _contact_sheet(video: Path, output: Path, duration_s: float) -> None:
    interval = max(0.2, duration_s / 6)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-vf",
            (
                f"fps=1/{interval:.6f},scale=480:-1,"
                "tile=3x2:padding=8:margin=8:color=white"
            ),
            "-frames:v",
            "1",
            str(output),
        ],
        check=True,
    )
    if not output.is_file() or output.stat().st_size <= 0:
        raise ActionProofError("action proof contact sheet was not created")


def create(root: Path, manifest: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest = manifest.resolve()
    data = studio.load_json(manifest)
    duration = float(data.get("canvas", {}).get("duration_s", 0))
    if duration < 3:
        raise ActionProofError("action proof source must be at least 3 seconds")
    end_s = min(5.0, duration)
    folder, video, contact = _paths(root)
    folder.mkdir(parents=True, exist_ok=True)
    render_evidence = production_remotion.render_action_sample(
        root, manifest, video
    )
    end_s = float(render_evidence["duration_s"])
    _contact_sheet(video, contact, end_s)
    inputs = {
        "manifest": studio.portable_path(root, manifest),
        "manifest_sha256": production_contract.file_digest(manifest),
        "asset_snapshot": production_contract.composition_asset_snapshot(
            manifest
        ),
        "preview": studio.portable_path(root, video),
        "preview_sha256": production_contract.file_digest(video),
        "contact_sheet": studio.portable_path(root, contact),
        "contact_sheet_sha256": production_contract.file_digest(contact),
        "duration_s": end_s,
        "render_evidence": render_evidence,
    }
    report = {
        "schema_version": 1,
        "kind": "action",
        "project_id": studio.load_project(root)["project"]["id"],
        "status": "pending",
        "passed": False,
        "approval": None,
        "inputs": inputs,
        "input_fingerprint": production_contract.canonical_digest(inputs),
    }
    report["fingerprint"] = production_contract.canonical_digest(report)
    target = folder / "proof.json"
    studio.atomic_json(target, report)
    return report


def approve(root: Path, *, note: str) -> dict[str, Any]:
    if not note.strip():
        raise ActionProofError("action proof approval requires a human note")
    root = root.resolve()
    folder, video, contact = _paths(root)
    target = folder / "proof.json"
    if not target.is_file():
        raise ActionProofError("create the action proof before approval")
    report = studio.load_json(target)
    inputs = report.get("inputs", {})
    manifest = studio.resolve_path(root, str(inputs.get("manifest", ""))).resolve()
    expected = {
        "manifest_sha256": production_contract.file_digest(manifest),
        "preview_sha256": production_contract.file_digest(video),
        "contact_sheet_sha256": production_contract.file_digest(contact),
    }
    for key, value in expected.items():
        if inputs.get(key) != value:
            raise ActionProofError(f"action proof is stale: {key}")
    if (
        inputs.get("asset_snapshot")
        != production_contract.composition_asset_snapshot(manifest)
    ):
        raise ActionProofError("action proof is stale: nested composition media")
    if (
        inputs.get("render_evidence", {}).get("runtime_fingerprint")
        != production_remotion.action_runtime_fingerprint()
    ):
        raise ActionProofError("action proof is stale: Remotion runtime changed")
    report["status"] = "approved"
    report["passed"] = True
    report["approval"] = {"note": note.strip(), "approved_at": studio.now_iso()}
    report["fingerprint"] = production_contract.canonical_digest(
        {key: value for key, value in report.items() if key != "fingerprint"}
    )
    studio.atomic_json(target, report)
    state = studio.load_state(root)
    state.setdefault("proofs", {})["action"] = {
        "path": studio.portable_path(root, target),
        "fingerprint": report["fingerprint"],
        "passed": True,
        "input_fingerprint": report["input_fingerprint"],
    }
    state["updated_at"] = studio.now_iso()
    studio.atomic_json(studio.state_file(root), state)
    return report


def verify(root: Path) -> dict[str, Any]:
    root = root.resolve()
    state = studio.load_state(root)
    record = state.get("proofs", {}).get("action")
    if not isinstance(record, dict) or not record.get("passed"):
        raise ActionProofError("approved action proof is missing")
    path = studio.resolve_path(root, str(record.get("path", ""))).resolve()
    report = studio.load_json(path)
    if report.get("fingerprint") != record.get("fingerprint"):
        raise ActionProofError("action proof registration is stale")
    inputs = report.get("inputs", {})
    checks = {
        "manifest_sha256": production_contract.file_digest(
            studio.resolve_path(root, str(inputs.get("manifest", ""))).resolve()
        ),
        "preview_sha256": production_contract.file_digest(
            studio.resolve_path(root, str(inputs.get("preview", ""))).resolve()
        ),
        "contact_sheet_sha256": production_contract.file_digest(
            studio.resolve_path(root, str(inputs.get("contact_sheet", ""))).resolve()
        ),
    }
    for key, value in checks.items():
        if inputs.get(key) != value:
            raise ActionProofError(f"action proof is stale: {key}")
    manifest = studio.resolve_path(
        root, str(inputs.get("manifest", ""))
    ).resolve()
    if (
        inputs.get("asset_snapshot")
        != production_contract.composition_asset_snapshot(manifest)
    ):
        raise ActionProofError("action proof is stale: nested composition media")
    if (
        inputs.get("render_evidence", {}).get("runtime_fingerprint")
        != production_remotion.action_runtime_fingerprint()
    ):
        raise ActionProofError("action proof is stale: Remotion runtime changed")
    return {"passed": True, "status": "approved", "fingerprint": report["fingerprint"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create_parser = sub.add_parser("create")
    create_parser.add_argument("project_dir", type=Path)
    create_parser.add_argument("manifest", type=Path)
    approve_parser = sub.add_parser("approve")
    approve_parser.add_argument("project_dir", type=Path)
    approve_parser.add_argument("--note", required=True)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "create":
            root = args.project_dir.resolve()
            manifest = args.manifest
            if not manifest.is_absolute():
                manifest = root / manifest
            report = create(root, manifest)
        elif args.command == "approve":
            report = approve(args.project_dir.resolve(), note=args.note)
        else:
            report = verify(args.project_dir.resolve())
        print(f"action proof: {report['status']}")
        return 0
    except (
        OSError,
        ValueError,
        KeyError,
        subprocess.CalledProcessError,
        production_remotion.ProductionRemotionError,
        production_contract.ProductionError,
        ActionProofError,
    ) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
