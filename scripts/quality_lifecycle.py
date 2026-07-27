#!/usr/bin/env python3
"""Bind quality review to one surface, target, report, evidence set, and contact sheet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import production_contract


SURFACES = {
    "asset",
    "composition",
    "subtitle",
    "transition",
    "relationship",
    "semantic-contract",
    "world-motion",
}


class QualityLifecycleError(RuntimeError):
    pass


def _file(path: Path) -> dict[str, str]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise QualityLifecycleError(f"missing quality evidence: {resolved}")
    return {
        "path": str(resolved),
        "content_sha256": production_contract.file_digest(resolved),
    }


def scaffold(
    *,
    surface: str,
    target: str,
    report: Path,
    contact_sheet: Path,
    evidence: list[Path],
    runtime_surface_fingerprint: str,
) -> dict[str, Any]:
    if surface not in SURFACES or not target.strip():
        raise QualityLifecycleError("quality surface and stable target are required")
    if not runtime_surface_fingerprint.startswith("sha256:"):
        raise QualityLifecycleError("runtime surface fingerprint is required")
    payload = {
        "schema_version": 1,
        "surface": surface,
        "target": target.strip(),
        "report": _file(report),
        "contact_sheet": _file(contact_sheet),
        "evidence": [_file(path) for path in evidence],
        "runtime_surface_fingerprint": runtime_surface_fingerprint,
    }
    if not payload["evidence"]:
        raise QualityLifecycleError("at least one evidence file is required")
    payload["input_fingerprint"] = production_contract.canonical_digest(payload)
    payload["status"] = "pending-human-review"
    payload["fingerprint"] = production_contract.canonical_digest(payload)
    return payload


def approve(scaffold_report: dict[str, Any], *, note: str, reviewer: str) -> dict[str, Any]:
    if scaffold_report.get("status") != "pending-human-review":
        raise QualityLifecycleError("only a pending scaffold can be approved")
    if not note.strip() or not reviewer.strip():
        raise QualityLifecycleError("approval requires reviewer and human note")
    decision = {
        "schema_version": 1,
        "surface": scaffold_report["surface"],
        "target": scaffold_report["target"],
        "scaffold_fingerprint": scaffold_report["fingerprint"],
        "input_fingerprint": scaffold_report["input_fingerprint"],
        "reviewer": reviewer.strip(),
        "note": note.strip(),
        "status": "approved",
    }
    decision["fingerprint"] = production_contract.canonical_digest(decision)
    return decision


def verify(scaffold_report: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    current_files: list[dict[str, str]] = []
    for item in (
        scaffold_report["report"],
        scaffold_report["contact_sheet"],
        *scaffold_report["evidence"],
    ):
        current_files.append(_file(Path(item["path"])))
    expected_files = [
        scaffold_report["report"],
        scaffold_report["contact_sheet"],
        *scaffold_report["evidence"],
    ]
    files_current = current_files == expected_files
    scaffold_integrity = scaffold_report.get("fingerprint") == production_contract.canonical_digest({
        key: value for key, value in scaffold_report.items() if key != "fingerprint"
    })
    decision_integrity = decision.get("fingerprint") == production_contract.canonical_digest({
        key: value for key, value in decision.items() if key != "fingerprint"
    })
    passed = (
        files_current
        and scaffold_integrity
        and decision_integrity
        and decision.get("status") == "approved"
        and decision.get("surface") == scaffold_report.get("surface")
        and decision.get("target") == scaffold_report.get("target")
        and decision.get("scaffold_fingerprint") == scaffold_report.get("fingerprint")
        and decision.get("input_fingerprint") == scaffold_report.get("input_fingerprint")
    )
    return {
        "surface": scaffold_report.get("surface"),
        "target": scaffold_report.get("target"),
        "files_current": files_current,
        "scaffold_integrity": scaffold_integrity,
        "decision_integrity": decision_integrity,
        "passed": passed,
        "status": "current-approved" if passed else "stale-or-mismatched",
    }


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QualityLifecycleError(f"{path} must contain an object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("scaffold")
    make.add_argument("--surface", choices=sorted(SURFACES), required=True)
    make.add_argument("--target", required=True)
    make.add_argument("--report", type=Path, required=True)
    make.add_argument("--contact-sheet", type=Path, required=True)
    make.add_argument("--evidence", type=Path, action="append", required=True)
    make.add_argument("--runtime-fingerprint", required=True)
    make.add_argument("--output", type=Path, required=True)
    accept = sub.add_parser("approve")
    accept.add_argument("scaffold", type=Path)
    accept.add_argument("--reviewer", required=True)
    accept.add_argument("--note", required=True)
    accept.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("verify")
    check.add_argument("scaffold", type=Path)
    check.add_argument("decision", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "scaffold":
            value = scaffold(
                surface=args.surface,
                target=args.target,
                report=args.report,
                contact_sheet=args.contact_sheet,
                evidence=args.evidence,
                runtime_surface_fingerprint=args.runtime_fingerprint,
            )
            _write(args.output, value)
        elif args.command == "approve":
            value = approve(
                _read(args.scaffold),
                note=args.note,
                reviewer=args.reviewer,
            )
            _write(args.output, value)
        else:
            value = verify(_read(args.scaffold), _read(args.decision))
            print(json.dumps(value, ensure_ascii=False, indent=2))
            return 0 if value["passed"] else 1
        print(value["fingerprint"])
        return 0
    except (
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
        QualityLifecycleError,
    ) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
