#!/usr/bin/env python3
"""Compile and audit provider-neutral editorial direction contracts."""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any

import editorial_runtime
import annotation_layout
import narration


class ContractError(RuntimeError):
    pass


TRANSITION_ROUTES = {
    "continuity": {"mechanism": "paper-slide", "duration_s": 0.45},
    "location-change": {"mechanism": "paper-wipe", "duration_s": 0.50},
    "time-passage": {"mechanism": "page-turn", "duration_s": 0.70},
    "focus-reveal": {"mechanism": "paper-iris", "duration_s": 0.55},
    "chapter-reset": {"mechanism": "paper-shutters", "duration_s": 0.65},
    "impact": {"mechanism": "cut", "duration_s": 0.0, "motivation": "impact"},
    # Existing v3 authoring names remain readable while compiling into v4 recipes.
    "reveal": {"mechanism": "paper-wipe", "duration_s": 0.45},
    "compare": {"mechanism": "matched-cut", "duration_s": 0.0, "motivation": "rhythmic"},
    "traverse": {"mechanism": "paper-slide", "duration_s": 0.45},
    "explain": {"mechanism": "layer-build", "duration_s": 0.40},
    "emphasize": {"mechanism": "paper-iris", "duration_s": 0.50},
    "change-time": {"mechanism": "page-turn", "duration_s": 0.70},
    "change-place": {"mechanism": "paper-wipe", "duration_s": 0.50},
}

ASPECT_CANVASES = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
}

CONTRACT_KINDS = {"identity", "topology", "mechanism", "infographic"}
EVIDENCE_KINDS = {"source", "reference", "registered-source", "data", "manual"}


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{path} must contain a JSON object")
    return value


def _write(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def validate_semantic_contracts(
    contracts: list[dict[str, Any]] | None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if contracts is None:
        return errors, ["semantic_contracts not declared"]
    if not isinstance(contracts, list) or not contracts:
        return ["semantic_contracts must be a non-empty array"], warnings
    seen: set[str] = set()
    for index, contract in enumerate(contracts, 1):
        if not isinstance(contract, dict):
            errors.append(f"semantic_contracts[{index}] must be an object")
            continue
        contract_id = str(contract.get("id", "")).strip()
        if not contract_id:
            errors.append(f"semantic_contracts[{index}] needs id")
        elif contract_id in seen:
            errors.append(f"duplicate semantic contract id: {contract_id}")
        seen.add(contract_id)
        kind = str(contract.get("kind", "")).strip()
        if kind not in CONTRACT_KINDS:
            errors.append(
                f"{contract_id or index}: kind must be one of {sorted(CONTRACT_KINDS)}"
            )
        claim = str(contract.get("claim", "")).strip()
        if len(claim) < 3:
            errors.append(f"{contract_id or index}: claim is required")
        evidence = contract.get("evidence", [])
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{contract_id or index}: evidence must be non-empty")
            continue
        for evidence_index, item in enumerate(evidence, 1):
            if not isinstance(item, dict):
                errors.append(
                    f"{contract_id or index}: evidence[{evidence_index}] must be an object"
                )
                continue
            if str(item.get("kind", "")) not in EVIDENCE_KINDS:
                errors.append(
                    f"{contract_id or index}: evidence[{evidence_index}].kind "
                    f"must be one of {sorted(EVIDENCE_KINDS)}"
                )
            if not str(item.get("ref", "")).strip():
                errors.append(
                    f"{contract_id or index}: evidence[{evidence_index}].ref is required"
                )
        protected = contract.get("protected_features", [])
        if kind in {"identity", "topology"} and not protected:
            warnings.append(
                f"{contract_id or index}: declare protected_features for visual QA"
            )
        automated = contract.get("automated_checks", [])
        if not isinstance(automated, list) or not automated:
            warnings.append(
                f"{contract_id or index}: no automated semantic checks declared"
            )
    return errors, warnings


def route_transitions(beats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    routed: list[dict[str, Any]] = []
    for index, beat in enumerate(beats):
        item = copy.deepcopy(beat)
        if index:
            intent = str(item.get("transition_intent", "reveal")).strip()
            if intent not in TRANSITION_ROUTES:
                raise ContractError(
                    f"{item.get('id', index)}: unsupported transition_intent {intent!r}"
                )
            route = TRANSITION_ROUTES[intent]
            duration = float(
                item.get("transition_duration_s", route["duration_s"])
            )
            mechanism = str(
                item.get("transition_mechanism") or route["mechanism"]
            )
            cutlike = mechanism in {"cut", "matched-cut"}
            if cutlike and duration != 0:
                raise ContractError(f"{item.get('id', index)}: a cut must be zero seconds")
            if not cutlike and not 0.2 <= duration <= 1.5:
                raise ContractError(
                    f"{item.get('id', index)}: animated boundary must be 0.2..1.5s"
                )
            rationale = str(item.get("transition_rationale", "")).strip()
            if not rationale:
                rationale = "execute the approved narrative relationship"
            item["transition"] = {
                "intent": intent,
                "mechanism": mechanism,
                "duration_s": duration,
                "motivation": str(
                    item.get("transition_motivation")
                    or route.get("motivation", "narrative")
                ),
                "rationale": rationale,
            }
        routed.append(item)
    return routed


def compile_narration_timeline(project: dict[str, Any]) -> dict[str, Any]:
    """Allocate visual time from speech evidence instead of fixed shot lengths."""
    pmeta = project.get("project", {})
    language = str(pmeta.get("language", "zh"))
    voice = project.get("audio", {}).get("voice", {})
    profile = str(voice.get("profile", "conversational"))
    rate = narration.parse_rate_multiplier(str(voice.get("rate", "+0%")))
    units_rate = {
        "zh": 4.2, "ja": 5.0, "ko": 4.0, "en": 2.7,
        "fr": 2.6, "de": 2.4, "es": 2.8, "pt": 2.8, "it": 2.8,
    }.get(narration.normalize_language(language), 2.6)
    config = project.get("editorial_timing", {})
    intro_s = float(config.get("intro_hold_s", 0.35))
    outro_s = float(config.get("outro_hold_s", 0.45))
    visual_tail_s = float(config.get("visual_tail_s", 0.18))
    min_beat_s = float(config.get("min_beat_s", 1.2))
    max_beat_s = float(config.get("max_beat_s", 12.0))
    measured = config.get("measured_voice_s", {})
    if not isinstance(measured, dict):
        raise ContractError("editorial_timing.measured_voice_s must be an object")
    cursor = intro_s
    compiled: list[dict[str, Any]] = []
    for index, raw in enumerate(project.get("beats", []), 1):
        beat_id = str(raw.get("id") or f"beat-{index:02d}")
        text = str(raw.get("narration", "")).strip()
        if not text:
            duration_s = float(raw.get("designed_silent_hold_s", min_beat_s))
            source = "designed-silence"
            plan: list[dict[str, Any]] = []
        else:
            plan = narration.build_prosody_plan(
                text, voice.get("prosody", {}), language, profile
            )
            estimated_s = (
                sum(int(part["units"]) for part in plan)
                / max(0.1, units_rate * rate)
                + sum(float(part["pause_after_s"]) for part in plan)
            )
            measured_s = measured.get(beat_id)
            duration_s = (
                float(measured_s) + visual_tail_s
                if measured_s is not None
                else estimated_s + visual_tail_s
            )
            source = "measured-voice" if measured_s is not None else "estimated-voice"
        duration_s = min(max_beat_s, max(min_beat_s, duration_s))
        compiled.append({
            "id": beat_id,
            "start_s": round(cursor, 3),
            "duration_s": round(duration_s, 3),
            "end_s": round(cursor + duration_s, 3),
            "duration_source": source,
            "phrase_count": len(plan),
            "planned_pause_s": round(
                sum(float(part["pause_after_s"]) for part in plan), 3
            ),
        })
        cursor += duration_s
    total_s = cursor + outro_s
    return {
        "intro_hold_s": intro_s,
        "outro_hold_s": outro_s,
        "beats": compiled,
        "duration_s": round(total_s, 3),
        "duration_authority": "measured voice when available; otherwise prosody estimate",
    }


def compile_director_variants(
    manifest: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    plans = manifest.get("director_plans")
    if not isinstance(plans, dict) or not plans:
        raise ContractError("director_plans must declare at least one aspect")
    variants: dict[str, dict[str, Any]] = {}
    base_director = manifest.get("director", {})
    for aspect, plan in plans.items():
        if aspect not in ASPECT_CANVASES:
            raise ContractError(f"unsupported director aspect {aspect!r}")
        if not isinstance(plan, dict):
            raise ContractError(f"director_plans.{aspect} must be an object")
        value = copy.deepcopy(manifest)
        value.pop("director_plans", None)
        width, height = ASPECT_CANVASES[aspect]
        canvas = value.setdefault("canvas", {})
        canvas["width"] = int(plan.get("width", width))
        canvas["height"] = int(plan.get("height", height))
        value["director"] = {
            **(base_director if isinstance(base_director, dict) else {}),
            "id": str(plan.get("id", f"director-{aspect.replace(':', 'x')}")),
            "aspect": aspect,
            "safe_zones": copy.deepcopy(plan.get("safe_zones", [])),
            "node_overrides": copy.deepcopy(plan.get("node_overrides", {})),
        }
        value, annotation_audit = annotation_layout.resolve_manifest(value)
        compiled = editorial_runtime.compile_composition(value)
        compiled["director"]["layout_audit"] = audit_safe_zones(compiled)
        compiled["director"]["annotation_layout"] = annotation_audit
        variants[aspect] = compiled
    return variants


def _rect(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        x, y, width, height = map(float, value)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    return x, y, width, height


def _intersects(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def audit_safe_zones(manifest: dict[str, Any]) -> dict[str, Any]:
    director = manifest.get("director", {})
    canvas = manifest.get("canvas", {})
    width = float(canvas.get("width", 0))
    height = float(canvas.get("height", 0))
    zones = director.get("safe_zones", []) if isinstance(director, dict) else []
    issues: list[str] = []
    parsed: list[tuple[str, tuple[float, float, float, float], str]] = []
    for index, zone in enumerate(zones, 1):
        zone_id = str(zone.get("id") or f"zone-{index}")
        rect = _rect(zone.get("rect"))
        policy = str(zone.get("policy", "contain"))
        if rect is None or policy not in {"contain", "exclude"}:
            issues.append(f"{zone_id}: invalid rect or policy")
            continue
        x, y, w, h = rect
        if x < 0 or y < 0 or x + w > width or y + h > height:
            issues.append(f"{zone_id}: outside canvas")
        parsed.append((zone_id, rect, policy))
    for first_index, first in enumerate(parsed):
        for second in parsed[first_index + 1:]:
            if first[2] == second[2] == "contain" and _intersects(first[1], second[1]):
                issues.append(f"{first[0]} overlaps {second[0]}")
    return {"zones": len(parsed), "issues": issues, "passed": not issues}


def build_proof_moments(project: dict[str, Any]) -> list[dict[str, Any]]:
    moments: list[dict[str, Any]] = []
    cursor = 0.0
    for index, beat in enumerate(project.get("beats", []), 1):
        beat_id = str(beat.get("id") or f"beat-{index:02d}")
        duration = float(beat.get("duration_s", 0))
        for proof_index, proof in enumerate(beat.get("proof_moments", []), 1):
            if not isinstance(proof, dict):
                raise ContractError(f"{beat_id}: proof_moments must contain objects")
            offset = float(proof.get("offset_s", duration * 0.5))
            if offset < 0 or offset > duration:
                raise ContractError(f"{beat_id}: proof moment falls outside beat")
            moment_id = str(proof.get("id") or f"{beat_id}-proof-{proof_index}")
            checks = proof.get("checks", [])
            if not isinstance(checks, list) or not checks:
                raise ContractError(f"{moment_id}: checks must be non-empty")
            moments.append({
                "id": moment_id,
                "beat_id": beat_id,
                "at_s": round(cursor + offset, 3),
                "frame": math.floor((cursor + offset) * float(
                    project.get("delivery", {}).get("fps", 30)
                )),
                "checks": copy.deepcopy(checks),
            })
        cursor += duration
    return moments


def compile_av_events(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep visible action and its sound/proof binding in one event catalog."""
    events: list[dict[str, Any]] = []
    proof_ids = {
        str(item["id"]) for item in build_proof_moments(project)
    }
    seen: set[str] = set()
    cursor = 0.0
    for beat_index, beat in enumerate(project.get("beats", []), 1):
        beat_id = str(beat.get("id") or f"beat-{beat_index:02d}")
        duration = float(beat.get("duration_s", 0))
        for event_index, raw in enumerate(beat.get("events", []), 1):
            event_id = str(raw.get("id") or f"{beat_id}-event-{event_index}")
            if event_id in seen:
                raise ContractError(f"duplicate audiovisual event id {event_id}")
            seen.add(event_id)
            progress = float(raw.get("progress", 0.5))
            end_progress = float(raw.get("end_progress", progress))
            if not 0 <= progress <= end_progress <= 1:
                raise ContractError(f"{event_id}: event progress is invalid")
            kind = str(raw.get("kind", "emphasis"))
            if kind not in {"emphasis", "visibility", "hold"}:
                raise ContractError(f"{event_id}: unsupported event kind")
            proof_id = str(raw.get("proof_id", "")).strip()
            if proof_id and proof_id not in proof_ids:
                raise ContractError(f"{event_id}: unknown proof_id {proof_id}")
            sound = raw.get("sound")
            if sound is not None and not proof_id:
                raise ContractError(f"{event_id}: sound events require a proof binding")
            events.append({
                "id": event_id,
                "beat_id": beat_id,
                "kind": kind,
                "target_id": str(raw.get("target_id", "scene")),
                "from_s": round(cursor + progress * duration, 4),
                "to_s": round(cursor + end_progress * duration, 4),
                "visual": copy.deepcopy(raw.get("visual", {})),
                "sound": copy.deepcopy(sound),
                "proof_id": proof_id or None,
            })
        cursor += duration
    return events


def transition_proof_samples(project: dict[str, Any]) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    cursor = 0.0
    routed = route_transitions(project.get("beats", []))
    for index, beat in enumerate(routed):
        duration = float(beat.get("duration_s", 0))
        if index:
            transition = beat["transition"]
            boundary = cursor
            span = float(transition["duration_s"])
            epsilon = max(1 / float(project.get("project", {}).get("fps", 30)), span / 2)
            samples.append({
                "id": f"{routed[index - 1].get('id')}--{beat.get('id')}",
                "intent": transition["intent"],
                "mechanism": transition["mechanism"],
                "before_s": round(max(0, boundary - epsilon), 4),
                "at_s": round(boundary, 4),
                "after_s": round(boundary + epsilon, 4),
                "checks": [
                    "opaque-boundary",
                    "no-semantic-crossfade",
                    "direction-matches-intent",
                ],
            })
        cursor += duration
    return samples


def compile_project(project: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(project)
    errors, warnings = validate_semantic_contracts(
        result.get("semantic_contracts")
    )
    if errors:
        raise ContractError("semantic contract errors:\n- " + "\n- ".join(errors))
    result["beats"] = route_transitions(result.get("beats", []))
    result["compiled_editorial_timing"] = compile_narration_timeline(result)
    result["compiled_proof_moments"] = build_proof_moments(result)
    result["compiled_av_events"] = compile_av_events(result)
    result["compiled_transition_proofs"] = transition_proof_samples(result)
    result["editorial_audit"] = {
        "semantic_contracts": len(result.get("semantic_contracts", [])),
        "warnings": warnings,
        "transition_routes": max(0, len(result.get("beats", [])) - 1),
        "proof_moments": len(result["compiled_proof_moments"]),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--kind", choices=("project", "composition"), default="project"
    )
    args = parser.parse_args()
    source = _read(Path(args.input).resolve())
    output = Path(args.output).resolve()
    if args.kind == "project":
        _write(output, compile_project(source))
        print(f"editorial project: {output}")
    else:
        variants = compile_director_variants(source)
        output.mkdir(parents=True, exist_ok=True)
        for aspect, value in variants.items():
            target = output / f"composition-{aspect.replace(':', 'x')}.json"
            _write(target, value)
            print(f"director variant {aspect}: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
