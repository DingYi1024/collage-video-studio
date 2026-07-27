#!/usr/bin/env python3
"""Compile preview feedback while protecting approved meaning and invalidating dependents."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

import editorial_contract
import production_contract


PROTECTED = {
    "project",
    "creative",
    "semantic_contracts",
    "production",
    "source_packages",
}
DIRECTING_FIELDS = {
    "shots",
    "treatments",
    "rhythm",
    "proof_moments",
    "events",
    "transition_intent",
    "transition_mechanism",
    "transition_duration_s",
    "transition_motivation",
    "transition_rationale",
}


class RevisionError(RuntimeError):
    pass


def concept_fingerprint(project: dict[str, Any]) -> str:
    return production_contract.canonical_digest({
        key: project.get(key) for key in sorted(PROTECTED)
    })


def apply_directing(
    approved: dict[str, Any], candidate: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    before = concept_fingerprint(approved)
    after = concept_fingerprint(candidate)
    if before != after:
        raise RevisionError("directing-only revision changed protected meaning or budget")
    approved_beats = approved.get("beats", [])
    candidate_beats = candidate.get("beats", [])
    if [item.get("id") for item in approved_beats] != [
        item.get("id") for item in candidate_beats
    ]:
        raise RevisionError("directing-only revision cannot add, remove, or reorder beats")
    updated = copy.deepcopy(approved)
    changes: list[str] = []
    for target, source in zip(updated["beats"], candidate_beats, strict=True):
        for field in DIRECTING_FIELDS:
            if source.get(field) != target.get(field):
                target[field] = copy.deepcopy(source.get(field))
                changes.append(f"{target.get('id')}:{field}")
    if not changes:
        raise RevisionError("directing revision is a no-op")
    compiled = editorial_contract.compile_project(updated)
    record = {
        "mode": "directing-only",
        "concept_fingerprint": before,
        "changed_fields": sorted(changes),
        "compiled_fingerprint": production_contract.canonical_digest(compiled),
        "invalidates": [
            "composition",
            "moment",
            "preview",
            "final",
            "assets-ready-seal",
        ],
        "preserves": ["story-approval", "style-approval", "provider-budget"],
    }
    record["fingerprint"] = production_contract.canonical_digest(record)
    return updated, record


def apply_semantic(
    approved: dict[str, Any],
    candidate: dict[str, Any],
    authorization: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    allowed = set(authorization.get("allowed_beat_ids", []))
    note = str(authorization.get("note", "")).strip()
    evidence = authorization.get("equivalent_quality_evidence", [])
    if not allowed or not note or not evidence:
        raise RevisionError(
            "semantic revision requires allowed beats, note, and equivalent evidence"
        )
    if approved.get("production") != candidate.get("production"):
        raise RevisionError("semantic revision cannot change the approved provider budget")
    old = {item.get("id"): item for item in approved.get("beats", [])}
    new = {item.get("id"): item for item in candidate.get("beats", [])}
    changed = {key for key in old | new if old.get(key) != new.get(key)}
    if not changed or not changed.issubset(allowed):
        raise RevisionError("semantic changes exceed the authorized beat set")
    record = {
        "mode": "semantic-authorized",
        "allowed_beat_ids": sorted(allowed),
        "changed_beat_ids": sorted(changed),
        "note": note,
        "equivalent_quality_evidence": evidence,
        "before_concept_fingerprint": concept_fingerprint(approved),
        "after_concept_fingerprint": concept_fingerprint(candidate),
        "invalidates": [
            "style",
            "assets",
            "composition",
            "moment",
            "preview",
            "final",
            "assets-ready-seal",
        ],
        "preserves": ["provider-budget"],
    }
    record["fingerprint"] = production_contract.canonical_digest(record)
    return copy.deepcopy(candidate), record


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RevisionError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("approved", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--output-project", type=Path, required=True)
    parser.add_argument("--output-record", type=Path, required=True)
    args = parser.parse_args()
    try:
        approved = _read(args.approved)
        candidate = _read(args.candidate)
        if args.authorization:
            project, record = apply_semantic(
                approved, candidate, _read(args.authorization)
            )
        else:
            project, record = apply_directing(approved, candidate)
        for path, value in (
            (args.output_project, project),
            (args.output_record, record),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        print(f"preview revision: {record['mode']} ({record['fingerprint']})")
        return 0
    except (
        OSError,
        json.JSONDecodeError,
        RevisionError,
        editorial_contract.ContractError,
    ) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
