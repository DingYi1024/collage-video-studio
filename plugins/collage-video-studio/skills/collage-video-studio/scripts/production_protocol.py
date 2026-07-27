#!/usr/bin/env python3
"""Compile production scenarios, rhythmic storyboards, source families, and proof dependencies."""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any

import production_contract


ASPECTS = ("16:9", "9:16", "1:1")
SCENARIOS = ("draft", "balanced", "full-depth")
RELATIONSHIPS = {
    "free",
    "supported-subject",
    "registered-environment",
    "registered-depth-stack",
    "looping-environment",
}
MOTION_CAPABILITIES = {"rigid-locked", "bounded-relative"}
SOURCE_STRATEGIES = {
    "local-vector",
    "single-cutout",
    "registered-sheet",
    "full-context-edits",
    "registered-state-sheet",
    "seamless-strip",
}
PROOF_KINDS = {"establish", "action", "peak", "final"}


class ProtocolError(RuntimeError):
    pass


def _require_id(value: Any, label: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ProtocolError(f"{label} requires a stable id")
    return result


def _number(value: Any, label: str, minimum: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"{label} must be numeric") from exc
    if not math.isfinite(result) or result < minimum:
        raise ProtocolError(f"{label} must be at least {minimum}")
    return result


def _unique(items: list[dict[str, Any]], label: str) -> None:
    identifiers = [_require_id(item.get("id"), label) for item in items]
    if len(identifiers) != len(set(identifiers)):
        raise ProtocolError(f"{label} ids must be unique")


def _envelope(raw: Any, label: str) -> dict[str, list[float]]:
    if not isinstance(raw, dict) or set(raw) != set(ASPECTS):
        raise ProtocolError(f"{label} must declare exactly {', '.join(ASPECTS)}")
    result: dict[str, list[float]] = {}
    for aspect in ASPECTS:
        value = raw[aspect]
        if not isinstance(value, list) or len(value) != 4:
            raise ProtocolError(f"{label}.{aspect} must be [left,top,right,bottom]")
        rect = [float(item) for item in value]
        if any(not math.isfinite(item) or item < 0 or item > 1 for item in rect):
            raise ProtocolError(f"{label}.{aspect} values must be normalized")
        if rect[0] > rect[2] or rect[1] > rect[3]:
            raise ProtocolError(f"{label}.{aspect} has inverted bounds")
        result[aspect] = rect
    return result


def compile_source_package(raw: dict[str, Any]) -> dict[str, Any]:
    """Turn one relationship intent into an auditable complete-source decision."""
    package_id = _require_id(raw.get("id"), "source package")
    relationship = str(raw.get("relationship", "free"))
    if relationship not in RELATIONSHIPS:
        raise ProtocolError(f"{package_id}: unsupported relationship {relationship!r}")
    capability = str(raw.get("motion_capability", "rigid-locked"))
    if capability not in MOTION_CAPABILITIES:
        raise ProtocolError(f"{package_id}: unsupported motion capability")
    strategy = str(raw.get("source_strategy", "local-vector"))
    if strategy not in SOURCE_STRATEGIES:
        raise ProtocolError(f"{package_id}: unsupported source strategy")
    roles = [str(item) for item in raw.get("roles", [])]
    required_roles: set[str] = set()
    if relationship in {"supported-subject", "registered-depth-stack"}:
        required_roles = {"support-rear", "subject", "support-front"}
    elif relationship == "registered-environment":
        required_roles = {"environment-upper", "environment-lower"}
    elif relationship == "looping-environment":
        required_roles = {"far", "ground"}
    if not required_roles.issubset(roles):
        missing = ", ".join(sorted(required_roles - set(roles)))
        raise ProtocolError(f"{package_id}: missing complete roles: {missing}")
    if len(roles) != len(set(roles)):
        raise ProtocolError(f"{package_id}: roles must be unique")
    if capability == "bounded-relative":
        if relationship != "registered-depth-stack":
            raise ProtocolError(
                f"{package_id}: bounded-relative is reserved for a registered depth stack"
            )
        if strategy not in {"registered-sheet", "full-context-edits"}:
            raise ProtocolError(
                f"{package_id}: relative layers require one complete registered source family"
            )
    reveal = (
        _envelope(raw.get("reveal_envelope"), f"{package_id}.reveal_envelope")
        if relationship == "registered-depth-stack"
        else None
    )
    subject_travel = raw.get("subject_travel_envelope")
    if subject_travel is not None:
        if relationship != "registered-depth-stack":
            raise ProtocolError(
                f"{package_id}: subject travel belongs only to a registered depth stack"
            )
        subject_travel = _envelope(
            subject_travel, f"{package_id}.subject_travel_envelope"
        )
    provider_calls = {
        "local-vector": 0,
        "single-cutout": 1,
        "registered-sheet": 1,
        "full-context-edits": 4,
        "registered-state-sheet": 1,
        "seamless-strip": 1,
    }[strategy]
    derivatives = (
        len(roles)
        if strategy in {"registered-sheet", "registered-state-sheet"}
        else 0
    )
    avoided = max(0, derivatives - provider_calls)
    result = {
        "id": package_id,
        "relationship": relationship,
        "motion_capability": capability,
        "source_strategy": strategy,
        "roles": roles,
        "registration_id": (
            _require_id(raw.get("registration_id"), f"{package_id}.registration")
            if relationship != "free"
            else None
        ),
        "reveal_envelope": reveal,
        "subject_travel_envelope": subject_travel,
        "accounting": {
            "provider_calls": provider_calls,
            "local_derivatives": derivatives,
            "isolated_calls_avoided": avoided,
        },
        "recovery_order": [
            "local-reprocess",
            "context-preserving-source-edit",
            "complete-source-regeneration",
        ],
    }
    result["fingerprint"] = production_contract.canonical_digest(result)
    return result


def compile_source_packages(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, list):
        raise ProtocolError("source_packages must be an array")
    packages = [compile_source_package(item) for item in raw]
    _unique(packages, "source package")
    totals = {
        key: sum(item["accounting"][key] for item in packages)
        for key in ("provider_calls", "local_derivatives", "isolated_calls_avoided")
    }
    result = {"packages": packages, "totals": totals}
    result["fingerprint"] = production_contract.canonical_digest(result)
    return result


def _semantic_actions(project: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    for beat_index, beat in enumerate(project.get("beats", []), 1):
        beat_id = str(beat.get("id") or f"beat-{beat_index:02d}")
        declared = beat.get("semantic_actions")
        if declared is None:
            declared = [beat.get("claim") or beat.get("narration")]
        if not isinstance(declared, list):
            raise ProtocolError(f"{beat_id}.semantic_actions must be an array")
        for action_index, action in enumerate(declared, 1):
            text = str(action or "").strip()
            if text:
                actions.append(f"{beat_id}:{action_index}:{text}")
    if not actions:
        raise ProtocolError("the common story needs at least one semantic action")
    return actions


def _source_stats(project: dict[str, Any]) -> dict[str, int]:
    compiled = compile_source_packages(project.get("source_packages", []))
    state_families = {
        str(treatment.get("state_family_id"))
        for beat in project.get("beats", [])
        for treatment in beat.get("treatments", [])
        if treatment.get("state_family_id")
    }
    return {
        "structural_calls": int(compiled["totals"]["provider_calls"]),
        "state_sheet_calls": len(state_families),
        "local_derivatives": int(compiled["totals"]["local_derivatives"]),
        "isolated_calls_avoided": int(compiled["totals"]["isolated_calls_avoided"]),
        "state_families": len(state_families),
        "relative_families": sum(
            item["motion_capability"] == "bounded-relative"
            for item in compiled["packages"]
        ),
    }


def compile_scenarios(project: dict[str, Any]) -> dict[str, Any]:
    """Create exactly three comparable plans before any quota-consuming call."""
    actions = _semantic_actions(project)
    stats = _source_stats(project)
    scene_count = len(project.get("beats", []))
    if scene_count < 1:
        raise ProtocolError("scenarios require at least one beat")
    definitions = {
        "draft": {"reserve": 1, "motion_floor": 1, "relative_floor": 0},
        "balanced": {"reserve": 2, "motion_floor": 2, "relative_floor": 0},
        "full-depth": {"reserve": 4, "motion_floor": 3, "relative_floor": 1},
    }
    options: list[dict[str, Any]] = []
    for profile in SCENARIOS:
        config = production_contract.PROFILES[profile]
        definition = definitions[profile]
        expected = stats["structural_calls"] + stats["state_sheet_calls"]
        ceiling = int(config["attempt_limits"]["visual_source"])
        approved_cap = min(ceiling, expected + definition["reserve"])
        option = {
            "id": profile,
            "story_action_ids": actions,
            "scene_count": scene_count,
            "profile_promise": {
                "semantic_actions": len(actions),
                "animated_scenes": min(scene_count, definition["motion_floor"]),
                "state_families": stats["state_families"],
                "relative_layer_families": max(
                    stats["relative_families"], definition["relative_floor"]
                ),
            },
            "provider_accounting": {
                "expected_calls": expected,
                "recovery_reserve": max(0, approved_cap - expected),
                "human_approved_cap": approved_cap,
                "profile_ceiling": ceiling,
                "local_derivatives": stats["local_derivatives"],
                "isolated_calls_avoided": stats["isolated_calls_avoided"],
            },
        }
        option["fingerprint"] = production_contract.canonical_digest(option)
        options.append(option)
    result = {
        "schema_version": 1,
        "project_id": project.get("project", {}).get("id"),
        "common_story_fingerprint": production_contract.canonical_digest(actions),
        "options": options,
    }
    result["fingerprint"] = production_contract.canonical_digest(result)
    return result


def approve_scenario(
    scenarios: dict[str, Any], option_id: str, note: str
) -> dict[str, Any]:
    if not str(note).strip():
        raise ProtocolError("scenario approval requires an attributable note")
    options = scenarios.get("options", [])
    if len(options) != 3 or [item.get("id") for item in options] != list(SCENARIOS):
        raise ProtocolError("scenario document must contain draft, balanced, full-depth")
    selected = next((item for item in options if item["id"] == option_id), None)
    if selected is None:
        raise ProtocolError(f"unknown scenario {option_id!r}")
    return {
        "scenario_id": option_id,
        "scenario_fingerprint": selected["fingerprint"],
        "document_fingerprint": scenarios["fingerprint"],
        "budget": copy.deepcopy(selected["provider_accounting"]),
        "profile_promise": copy.deepcopy(selected["profile_promise"]),
        "note": note.strip(),
    }


def _proofs(beat: dict[str, Any], duration: float) -> list[dict[str, Any]]:
    raw = beat.get("proof_moments")
    if not raw:
        raw = [
            {"id": f"{beat['id']}-establish", "kind": "establish", "progress": 0.08},
            {"id": f"{beat['id']}-action", "kind": "action", "progress": 0.52},
            {"id": f"{beat['id']}-final", "kind": "final", "progress": 0.88},
        ]
    if not isinstance(raw, list) or len(raw) < 3:
        raise ProtocolError(f"{beat['id']}: requires at least three proof moments")
    result: list[dict[str, Any]] = []
    for item in raw:
        kind = str(item.get("kind", "action"))
        if kind not in PROOF_KINDS:
            raise ProtocolError(f"{beat['id']}: unsupported proof kind {kind!r}")
        progress = float(item.get("progress", item.get("offset_s", 0) / duration))
        if progress < 0 or progress > 1:
            raise ProtocolError(f"{beat['id']}: proof progress must be normalized")
        result.append({
            "id": _require_id(item.get("id"), f"{beat['id']} proof"),
            "kind": kind,
            "progress": progress,
            "checks": list(item.get("checks", ["composition-readable"])),
        })
    result.sort(key=lambda item: item["progress"])
    if result[-1]["kind"] != "final" or result[-1]["progress"] < 0.82:
        raise ProtocolError(f"{beat['id']}: final proof must be last and at/after 0.82")
    _unique(result, f"{beat['id']} proof")
    return result


def _rhythm(beat: dict[str, Any], duration: float) -> list[dict[str, Any]]:
    raw = beat.get("rhythm")
    if not raw:
        raw = [
            {"id": f"{beat['id']}-setup", "from": 0.0, "to": 0.28, "intent": "setup"},
            {"id": f"{beat['id']}-develop", "from": 0.28, "to": 0.74, "intent": "develop"},
            {"id": f"{beat['id']}-land", "from": 0.74, "to": 1.0, "intent": "land"},
        ]
    if not isinstance(raw, list) or len(raw) < 3:
        raise ProtocolError(f"{beat['id']}: rhythmic storyboard needs at least three beats")
    result: list[dict[str, Any]] = []
    cursor = 0.0
    for item in raw:
        start = float(item.get("from", cursor))
        end = float(item.get("to", start))
        if abs(start - cursor) > 0.0001 or end <= start or end > 1.0:
            raise ProtocolError(f"{beat['id']}: rhythm must cover 0..1 without gaps")
        result.append({
            "id": _require_id(item.get("id"), f"{beat['id']} rhythm"),
            "from": start,
            "to": end,
            "from_s": round(start * duration, 4),
            "to_s": round(end * duration, 4),
            "intent": str(item.get("intent", "develop")),
        })
        cursor = end
    if abs(cursor - 1.0) > 0.0001:
        raise ProtocolError(f"{beat['id']}: rhythm must end at 1")
    return result


def compile_storyboard(
    project: dict[str, Any],
    scenarios: dict[str, Any],
    decision: dict[str, Any],
) -> dict[str, Any]:
    selected = next(
        (
            item for item in scenarios.get("options", [])
            if item.get("id") == decision.get("scenario_id")
        ),
        None,
    )
    if (
        selected is None
        or decision.get("scenario_fingerprint") != selected.get("fingerprint")
        or decision.get("document_fingerprint") != scenarios.get("fingerprint")
    ):
        raise ProtocolError("scenario decision is stale or does not match the options")
    source_packages = compile_source_packages(project.get("source_packages", []))
    source_package_ids = {
        item["id"] for item in source_packages["packages"]
    }
    scenes: list[dict[str, Any]] = []
    cursor = 0.0
    actions = _semantic_actions(project)
    seen_actions: set[str] = set()
    for index, raw in enumerate(project.get("beats", []), 1):
        beat = copy.deepcopy(raw)
        beat["id"] = _require_id(beat.get("id") or f"beat-{index:02d}", "beat")
        duration = _number(beat.get("duration_s"), f"{beat['id']}.duration_s", 0.1)
        proofs = _proofs(beat, duration)
        rhythm = _rhythm(beat, duration)
        treatments = beat.get("treatments", [])
        if not isinstance(treatments, list) or not treatments:
            raise ProtocolError(f"{beat['id']}: treatments must be non-empty")
        for treatment in treatments:
            target = _require_id(treatment.get("target_id"), f"{beat['id']} treatment")
            if not str(treatment.get("visible_change", "")).strip():
                raise ProtocolError(f"{beat['id']}:{target}: visible_change is required")
            if not str(treatment.get("mechanism", "")).strip():
                raise ProtocolError(f"{beat['id']}:{target}: mechanism is required")
        beat_actions = [
            item for item in actions if item.startswith(f"{beat['id']}:")
        ]
        seen_actions.update(beat_actions)
        declared_package_ids = list(beat.get("source_package_ids", []))
        unknown_packages = set(declared_package_ids) - source_package_ids
        if unknown_packages:
            raise ProtocolError(
                f"{beat['id']}: unknown source packages "
                + ", ".join(sorted(unknown_packages))
            )
        scenes.append({
            "id": beat["id"],
            "start_s": round(cursor, 4),
            "duration_s": duration,
            "end_s": round(cursor + duration, 4),
            "semantic_action_ids": beat_actions,
            "rhythm": rhythm,
            "proof_moments": proofs,
            "treatments": treatments,
            "source_package_ids": declared_package_ids,
            "audio_cues": list(beat.get("audio_cues", [])),
        })
        cursor += duration
    missing = set(actions) - seen_actions
    if missing:
        raise ProtocolError("storyboard does not visibly execute every semantic action")
    transitions: list[dict[str, Any]] = []
    for index in range(max(0, len(scenes) - 1)):
        incoming = project["beats"][index + 1]
        transitions.append({
            "id": f"{scenes[index]['id']}--{scenes[index + 1]['id']}",
            "from": scenes[index]["id"],
            "to": scenes[index + 1]["id"],
            "intent": str(incoming.get("transition_intent", "continuity")),
            "rationale": str(
                incoming.get("transition_rationale", "continue the approved story")
            ),
        })
    result = {
        "schema_version": 1,
        "status": "compiled",
        "project_id": project.get("project", {}).get("id"),
        "scenario": copy.deepcopy(decision),
        "duration_s": round(cursor, 4),
        "scenes": scenes,
        "scene_transitions": transitions,
        "source_packages": source_packages,
        "responsive_profiles": list(ASPECTS),
    }
    result["fingerprint"] = production_contract.canonical_digest(result)
    return result


def validate_fulfillment(
    storyboard: dict[str, Any], execution: dict[str, Any]
) -> dict[str, Any]:
    promise = storyboard.get("scenario", {}).get("profile_promise", {})
    actual = execution.get("fulfillment", {})
    checks: dict[str, bool] = {}
    for key in (
        "semantic_actions",
        "animated_scenes",
        "state_families",
        "relative_layer_families",
    ):
        checks[key] = int(actual.get(key, 0)) >= int(promise.get(key, 0))
    report = {
        "storyboard_fingerprint": storyboard.get("fingerprint"),
        "execution_fingerprint": production_contract.canonical_digest(execution),
        "checks": checks,
        "passed": all(checks.values()),
    }
    report["fingerprint"] = production_contract.canonical_digest(report)
    return report


def derive_fulfillment(project: dict[str, Any]) -> dict[str, Any]:
    actions = _semantic_actions(project)
    state_families: set[str] = set()
    animated_scenes = 0
    for beat in project.get("beats", []):
        treatments = beat.get("treatments", [])
        if any(
            str(item.get("mechanism", "")).strip().lower()
            not in {"", "static", "static-hold"}
            for item in treatments
            if isinstance(item, dict)
        ):
            animated_scenes += 1
        state_families.update(
            str(item["state_family_id"])
            for item in treatments
            if isinstance(item, dict) and item.get("state_family_id")
        )
    packages = compile_source_packages(project.get("source_packages", []))
    relative = sum(
        item["motion_capability"] == "bounded-relative"
        for item in packages["packages"]
    )
    execution = {
        "fulfillment": {
            "semantic_actions": len(actions),
            "animated_scenes": animated_scenes,
            "state_families": len(state_families),
            "relative_layer_families": relative,
        },
        "source_package_fingerprint": packages["fingerprint"],
    }
    execution["fingerprint"] = production_contract.canonical_digest(execution)
    return execution


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProtocolError(f"{path} must contain an object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    scenarios = sub.add_parser("scenarios")
    scenarios.add_argument("project", type=Path)
    scenarios.add_argument("--output", type=Path, required=True)
    approve = sub.add_parser("approve")
    approve.add_argument("scenarios", type=Path)
    approve.add_argument("option", choices=SCENARIOS)
    approve.add_argument("--note", required=True)
    approve.add_argument("--output", type=Path, required=True)
    storyboard = sub.add_parser("storyboard")
    storyboard.add_argument("project", type=Path)
    storyboard.add_argument("scenarios", type=Path)
    storyboard.add_argument("decision", type=Path)
    storyboard.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "scenarios":
            report = compile_scenarios(_read(args.project))
        elif args.command == "approve":
            report = approve_scenario(_read(args.scenarios), args.option, args.note)
        else:
            report = compile_storyboard(
                _read(args.project), _read(args.scenarios), _read(args.decision)
            )
        _write(args.output, report)
        print(f"{args.command}: {args.output} ({report.get('fingerprint', '')[:16]})")
        return 0
    except (OSError, json.JSONDecodeError, ProtocolError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
