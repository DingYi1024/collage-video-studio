#!/usr/bin/env python3
"""Create and accept source-bound narration gain decisions."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import production_contract


class CalibrationError(RuntimeError):
    pass


def source_fingerprint(project: dict[str, Any], preflight: dict[str, Any]) -> str:
    return production_contract.canonical_digest({
        "audio": project.get("audio"),
        "compiled_timing": project.get("compiled_timing"),
        "preflight_source": preflight.get("source_sha256"),
        "measured_lufs": preflight.get("measured_lufs"),
        "true_peak_db": preflight.get("true_peak_db"),
    })


def propose(project: dict[str, Any], preflight: dict[str, Any]) -> dict[str, Any]:
    measured = float(preflight.get("measured_lufs"))
    peak = float(preflight.get("true_peak_db"))
    target = float(project.get("audio", {}).get("target_lufs", -18.0))
    current = float(project.get("audio", {}).get("narration_gain_db", 0.0))
    gain = max(-6.0, min(6.0, target - measured))
    if peak + gain > -0.5:
        gain = -0.5 - peak
    recommended = round(current + gain, 2)
    passed = abs(target - measured) <= 2.0 and peak <= -0.5
    result = {
        "schema_version": 1,
        "status": "not-required" if passed else "proposed",
        "source_fingerprint": source_fingerprint(project, preflight),
        "current_gain_db": current,
        "recommended_gain_db": recommended,
        "preflight": copy.deepcopy(preflight),
        "accepted": None,
    }
    result["fingerprint"] = production_contract.canonical_digest(result)
    return result


def accept(
    project: dict[str, Any],
    proposal: dict[str, Any],
    fingerprint: str,
    note: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if proposal.get("status") != "proposed":
        raise CalibrationError("only a failing preflight proposal needs acceptance")
    if fingerprint != proposal.get("source_fingerprint"):
        raise CalibrationError("audio sources or timing changed; regenerate calibration")
    if not str(note).strip():
        raise CalibrationError("calibration acceptance requires a human note")
    updated = copy.deepcopy(project)
    updated.setdefault("audio", {})["narration_gain_db"] = float(
        proposal["recommended_gain_db"]
    )
    decision = copy.deepcopy(proposal)
    decision["status"] = "accepted"
    decision["accepted"] = {"note": note.strip()}
    decision["fingerprint"] = production_contract.canonical_digest({
        key: value for key, value in decision.items() if key != "fingerprint"
    })
    return updated, decision


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CalibrationError(f"{path} must contain an object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    proposal = sub.add_parser("propose")
    proposal.add_argument("project", type=Path)
    proposal.add_argument("preflight", type=Path)
    proposal.add_argument("--output", type=Path, required=True)
    acceptance = sub.add_parser("accept")
    acceptance.add_argument("project", type=Path)
    acceptance.add_argument("proposal", type=Path)
    acceptance.add_argument("--fingerprint", required=True)
    acceptance.add_argument("--note", required=True)
    acceptance.add_argument("--output-project", type=Path, required=True)
    acceptance.add_argument("--output-decision", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "propose":
            result = propose(_read(args.project), _read(args.preflight))
            _write(args.output, result)
        else:
            project, result = accept(
                _read(args.project),
                _read(args.proposal),
                args.fingerprint,
                args.note,
            )
            _write(args.output_project, project)
            _write(args.output_decision, result)
        print(f"audio calibration: {result['status']}")
        return 0
    except (OSError, json.JSONDecodeError, CalibrationError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
