#!/usr/bin/env python3
"""Validate and render deterministic multi-layer paper-collage motion manifests."""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image


TRANSFORM_KEYS = ("x", "y", "scale", "scale_x", "scale_y", "rotation", "opacity")
FOLLOW_KEYS = set(TRANSFORM_KEYS)
EASINGS = {
    "linear",
    "hold",
    "smoothstep",
    "smootherstep",
    "ease-in",
    "ease-out",
    "ease-in-out",
    "back-in",
    "back-out",
    "back-in-out",
    "catmull-rom",
}
MOTION_CLASSES = {
    "camera",
    "atmosphere",
    "rigid-body",
    "hinged-part",
    "major-pose",
    "effect",
}
MOTION_INTENTS = {
    "continuous",
    "entrance",
    "settle",
    "hold",
    "stepped",
}
DEFAULT_TRANSFORM = {
    "x": 0.0,
    "y": 0.0,
    "scale": 1.0,
    "scale_x": 1.0,
    "scale_y": 1.0,
    "rotation": 0.0,
    "opacity": 1.0,
}


class LayerError(RuntimeError):
    pass


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LayerError(f"cannot read layer manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LayerError("layer manifest must be a JSON object")
    return value


def layer_is_animated(layer: dict[str, Any]) -> bool:
    pose_sequence = layer.get("pose_sequence", {})
    if (
        len(layer.get("sprites", [])) > 1
        or len(pose_sequence.get("states", [])) > 1
        or layer.get("motion_path")
        or layer.get("visibility")
        or layer.get("looping_strip")
        or layer.get("motif_field")
    ):
        return True
    keyframes = layer.get("keyframes", [])
    if len(keyframes) < 2:
        return False
    first = {key: float(keyframes[0].get(key, DEFAULT_TRANSFORM[key]))
             for key in TRANSFORM_KEYS}
    return any(
        any(abs(float(frame.get(key, DEFAULT_TRANSFORM[key])) - first[key]) > 1e-6
            for key in TRANSFORM_KEYS)
        for frame in keyframes[1:]
    )


def transform_ranges(layer: dict[str, Any]) -> dict[str, float]:
    keyframes = layer.get("keyframes", [])
    if not keyframes:
        return {key: 0.0 for key in TRANSFORM_KEYS}
    return {
        key: max(frame_value(frame, key) for frame in keyframes)
        - min(frame_value(frame, key) for frame in keyframes)
        for key in TRANSFORM_KEYS
    }


def validate_follow_contract(
    layers_by_id: dict[str, dict[str, Any]],
    duration: float,
    errors: list[str],
) -> None:
    parents: dict[str, str] = {}
    for layer_id, layer in layers_by_id.items():
        follow = layer.get("follow")
        if follow is None:
            continue
        if not isinstance(follow, dict):
            errors.append(f"{layer_id}: follow must be an object")
            continue
        parent = str(follow.get("parent", "")).strip()
        if not parent:
            errors.append(f"{layer_id}: follow.parent is required")
            continue
        if parent == layer_id:
            errors.append(f"{layer_id}: a layer cannot follow itself")
            continue
        if parent not in layers_by_id:
            errors.append(f"{layer_id}: follow parent {parent!r} does not exist")
            continue
        parents[layer_id] = parent
        lag_s = 0.0
        try:
            lag_s = float(follow.get("lag_s", 0.0))
            if lag_s < 0 or lag_s > duration:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"{layer_id}: follow.lag_s must be within the shot")
        inherit = follow.get("inherit", {"x": 1.0, "y": 1.0})
        if not isinstance(inherit, dict) or not inherit:
            errors.append(f"{layer_id}: follow.inherit must be a non-empty object")
            continue
        for key, raw_weight in inherit.items():
            if key not in FOLLOW_KEYS:
                errors.append(f"{layer_id}: follow cannot inherit {key!r}")
                continue
            try:
                weight = float(raw_weight)
                if weight < 0 or weight > 1:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append(
                    f"{layer_id}: follow.inherit.{key} must be from 0 to 1"
                )
        space = str(follow.get("space", "world"))
        if space not in {"world", "rig"}:
            errors.append(f"{layer_id}: follow.space must be world or rig")
        if space == "rig":
            parent_pivot = layers_by_id[parent].get("pivot")
            child_pivot = layer.get("pivot")
            if (
                not isinstance(parent_pivot, list)
                or len(parent_pivot) != 2
                or not isinstance(child_pivot, list)
                or len(child_pivot) != 2
            ):
                errors.append(
                    f"{layer_id}: rig-space follow needs parent and child pivots"
                )
            if lag_s > 1e-6:
                errors.append(
                    f"{layer_id}: rig-space follow cannot lag without separating the joint"
                )
            try:
                full_translation = (
                    float(inherit.get("x", 0.0)) == 1.0
                    and float(inherit.get("y", 0.0)) == 1.0
                )
            except (TypeError, ValueError):
                full_translation = False
            if not full_translation:
                errors.append(
                    f"{layer_id}: rig-space follow must fully inherit x and y"
                )

    for start in parents:
        seen: set[str] = set()
        cursor = start
        while cursor in parents:
            if cursor in seen:
                errors.append(f"{start}: follow hierarchy contains a cycle")
                break
            seen.add(cursor)
            cursor = parents[cursor]


def validate_direction(
    manifest: dict[str, Any],
    layers_by_id: dict[str, dict[str, Any]],
    animated: int,
    errors: list[str],
    warnings: list[str],
) -> None:
    quality = manifest.get("quality", {})
    direction = manifest.get("direction")
    if not quality.get("directed_motion"):
        return
    if not isinstance(direction, dict):
        errors.append("quality.directed_motion requires a direction object")
        return

    required = ("primary_action", "physical_cause", "primary_layers", "phases")
    for key in required:
        if not direction.get(key):
            errors.append(f"direction.{key} is required for directed motion")

    primary_layers = direction.get("primary_layers", [])
    if not isinstance(primary_layers, list) or not primary_layers:
        errors.append("direction.primary_layers must be a non-empty array")
        primary_layers = []
    missing = [str(item) for item in primary_layers if str(item) not in layers_by_id]
    if missing:
        errors.append(f"direction.primary_layers missing: {', '.join(missing)}")
    for layer_id in primary_layers:
        layer = layers_by_id.get(str(layer_id))
        if layer is not None and not layer_is_animated(layer):
            errors.append(f"direction primary layer {layer_id} is not animated")

    phases = direction.get("phases", [])
    duration = float(manifest.get("canvas", {}).get("duration_s", 0.0))
    expected_names = ["anticipation", "action", "settle"]
    if not isinstance(phases, list) or len(phases) != 3:
        errors.append("direction.phases must contain anticipation, action, and settle")
    else:
        names = [str(item.get("name", "")) for item in phases]
        if names != expected_names:
            errors.append(
                "direction.phases must be ordered anticipation, action, settle"
            )
        previous_end = 0.0
        for index, phase in enumerate(phases):
            try:
                start = float(phase["start_s"])
                end = float(phase["end_s"])
            except (KeyError, TypeError, ValueError):
                errors.append(f"direction.phases[{index}] needs numeric start_s/end_s")
                continue
            if end <= start:
                errors.append(f"direction.phases[{index}] must have positive duration")
            if abs(start - previous_end) > 0.02:
                errors.append("direction phases must be contiguous")
            previous_end = end
        if phases and abs(previous_end - duration) > 0.02:
            errors.append("direction phases must cover the full shot duration")

    holds = direction.get("designed_holds", [])
    if holds and not isinstance(holds, list):
        errors.append("direction.designed_holds must be an array")
    elif isinstance(holds, list):
        for index, hold in enumerate(holds):
            try:
                start = float(hold["start_s"])
                end = float(hold["end_s"])
                if start < 0 or end <= start or end > duration + 1e-6:
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                errors.append(
                    f"direction.designed_holds[{index}] needs a valid in-shot range"
                )
            if not str(hold.get("reason", "")).strip():
                errors.append(
                    f"direction.designed_holds[{index}] needs a reason"
                )

    contacts = direction.get("contacts", [])
    if contacts and not isinstance(contacts, list):
        errors.append("direction.contacts must be an array")
    elif isinstance(contacts, list):
        for index, contact in enumerate(contacts):
            layer_id = str(contact.get("layer", "")).strip()
            if layer_id not in layers_by_id:
                errors.append(
                    f"direction.contacts[{index}] names a missing layer"
                )
            if str(contact.get("property", "")) not in {
                "x", "y", "rotation", "scale", "scale_x", "scale_y",
            }:
                errors.append(
                    f"direction.contacts[{index}].property is unsupported"
                )
            try:
                start = float(contact["start_s"])
                end = float(contact["end_s"])
                tolerance = float(contact.get("tolerance", 1.0))
                if start < 0 or end <= start or end > duration + 1e-6:
                    raise ValueError
                if tolerance < 0:
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                errors.append(
                    f"direction.contacts[{index}] needs a valid range and tolerance"
                )

    responses = direction.get("secondary_responses", [])
    if responses and not isinstance(responses, list):
        errors.append("direction.secondary_responses must be an array")
    elif isinstance(responses, list):
        for index, response in enumerate(responses):
            response_layers = response.get("layers", [])
            driver = str(response.get("driven_by", "")).strip()
            if not isinstance(response_layers, list) or not response_layers:
                errors.append(
                    f"direction.secondary_responses[{index}].layers is required"
                )
                continue
            missing_response_layers = [
                str(item)
                for item in response_layers
                if str(item) not in layers_by_id
            ]
            if missing_response_layers:
                errors.append(
                    f"direction.secondary_responses[{index}] missing layers: "
                    f"{', '.join(missing_response_layers)}"
                )
            if driver not in layers_by_id:
                errors.append(
                    f"direction.secondary_responses[{index}].driven_by is missing"
                )
            if not str(response.get("reason", "")).strip():
                errors.append(
                    f"direction.secondary_responses[{index}].reason is required"
                )
            for response_layer in response_layers:
                layer = layers_by_id.get(str(response_layer))
                follow = layer.get("follow", {}) if layer else {}
                if isinstance(follow, dict) and follow.get("parent") != driver:
                    errors.append(
                        f"direction.secondary_responses[{index}] layer "
                        f"{response_layer} does not follow {driver}"
                    )

    density = str(direction.get("motion_density", "medium"))
    limits = {"low": 0.45, "medium": 0.70, "high": 1.0}
    if density not in limits:
        errors.append("direction.motion_density must be low, medium, or high")
    elif layers_by_id:
        ratio = animated / len(layers_by_id)
        if ratio > limits[density]:
            warnings.append(
                f"animated layer ratio {ratio:.0%} exceeds {density} motion-density "
                f"guidance ({limits[density]:.0%}); keep secondary layers still"
            )

    animated_layers = [
        layer for layer in layers_by_id.values() if layer_is_animated(layer)
    ]
    micro_only = 0
    for layer in animated_layers:
        ranges = transform_ranges(layer)
        if (
            ranges["x"] < 2.0
            and ranges["y"] < 2.0
            and ranges["rotation"] < 0.8
            and ranges["scale"] < 0.008
            and ranges["scale_x"] < 0.008
            and ranges["scale_y"] < 0.008
            and ranges["opacity"] < 0.06
            and not layer.get("motion_path")
            and len(layer.get("sprites", [])) < 2
        ):
            micro_only += 1
    if animated_layers and micro_only / len(animated_layers) > 0.5:
        warnings.append(
            "most animated layers only have sub-visible micro-motion; "
            "use one readable primary action instead of ambient jitter"
        )


def validate_locomotion_contract(
    manifest: dict[str, Any],
    rig_id: str,
    rig: dict[str, Any],
    root_id: str,
    part_ids: set[str],
    layers_by_id: dict[str, dict[str, Any]],
    duration: float,
    errors: list[str],
) -> None:
    locomotion = rig.get("locomotion")
    if locomotion is None:
        return
    if not isinstance(locomotion, dict):
        errors.append(f"{rig_id}: locomotion must be an object")
        return
    if rig.get("type") != "articulated-paper":
        errors.append(f"{rig_id}: locomotion requires an articulated-paper rig")
        return
    feet = locomotion.get("feet", [])
    if (
        not isinstance(feet, list)
        or len(feet) != 2
        or len({str(item) for item in feet}) != 2
    ):
        errors.append(f"{rig_id}: locomotion.feet must name two distinct foot layers")
        return
    foot_ids = [str(item) for item in feet]
    missing_feet = [foot for foot in foot_ids if foot not in part_ids]
    if missing_feet:
        errors.append(
            f"{rig_id}: locomotion feet are not rig parts: {', '.join(missing_feet)}"
        )
        return
    axis = str(locomotion.get("root_axis", "x"))
    if axis not in {"x", "y"}:
        errors.append(f"{rig_id}: locomotion.root_axis must be x or y")
        axis = "x"
    try:
        min_stride = float(locomotion.get("min_stride_px", 16.0))
        min_contact = float(locomotion.get("min_contact_s", 0.12))
        max_double_support = float(
            locomotion.get("max_double_support_s", 0.2)
        )
        max_plant_drift = float(
            locomotion.get("max_plant_drift_px", 3.0)
        )
        if (
            not all(math.isfinite(value) for value in (
                min_stride, min_contact, max_double_support, max_plant_drift
            ))
            or min_stride <= 0
            or min_contact <= 0
            or max_double_support < 0
            or max_plant_drift < 0
        ):
            raise ValueError
    except (TypeError, ValueError):
        errors.append(
            f"{rig_id}: locomotion thresholds must be finite positive values"
        )
        return

    for foot_id in foot_ids:
        layer = layers_by_id[foot_id]
        if layer.get("motion_class") != "hinged-part":
            errors.append(f"{rig_id}: locomotion foot {foot_id} must be hinged-part")
        cursor = foot_id
        depth = 0
        visited: set[str] = set()
        while cursor != root_id and cursor not in visited:
            visited.add(cursor)
            follow = layers_by_id.get(cursor, {}).get("follow", {})
            cursor = str(follow.get("parent", ""))
            depth += 1
        if cursor != root_id or depth < 2:
            errors.append(
                f"{rig_id}: locomotion foot {foot_id} needs a leg segment "
                f"between the root and foot"
            )

    try:
        root_layer = layers_by_id[root_id]
        start_value = resolved_transform_at(
            root_layer, layers_by_id, 0.0
        )[axis]
        end_value = resolved_transform_at(
            root_layer, layers_by_id, duration
        )[axis]
        stride = abs(end_value - start_value)
        if stride + 1e-6 < min_stride:
            errors.append(
                f"{rig_id}: locomotion root travels {stride:.2f}px on {axis}; "
                f"needs at least {min_stride:.2f}px"
            )
    except (KeyError, LayerError, TypeError, ValueError) as exc:
        errors.append(f"{rig_id}: cannot resolve locomotion root travel ({exc})")

    contacts = manifest.get("direction", {}).get("contacts", [])
    grouped: dict[tuple[str, float, float], dict[str, float]] = {}
    if isinstance(contacts, list):
        for contact in contacts:
            if not isinstance(contact, dict):
                continue
            foot_id = str(contact.get("layer", ""))
            property_name = str(contact.get("property", ""))
            if foot_id not in foot_ids or property_name not in {"x", "y"}:
                continue
            try:
                start = float(contact["start_s"])
                end = float(contact["end_s"])
                tolerance = float(contact.get("tolerance", 1.0))
            except (KeyError, TypeError, ValueError):
                continue
            grouped.setdefault((foot_id, start, end), {})[property_name] = tolerance

    paired_intervals: list[tuple[str, float, float]] = []
    for (foot_id, start, end), properties in grouped.items():
        if {"x", "y"} - set(properties):
            errors.append(
                f"{rig_id}: plant interval {foot_id} {start:.2f}-{end:.2f}s "
                "must lock both x and y"
            )
            continue
        if end - start + 1e-6 < min_contact:
            errors.append(
                f"{rig_id}: plant interval {foot_id} {start:.2f}-{end:.2f}s "
                f"is shorter than {min_contact:.2f}s"
            )
        if max(properties.values()) > max_plant_drift + 1e-6:
            errors.append(
                f"{rig_id}: plant interval {foot_id} allows more than "
                f"{max_plant_drift:.2f}px drift"
            )
        paired_intervals.append((foot_id, start, end))

    for foot_id in foot_ids:
        if not any(interval[0] == foot_id for interval in paired_intervals):
            errors.append(f"{rig_id}: locomotion foot {foot_id} has no x/y plant lock")

    paired_intervals.sort(key=lambda item: (item[1], item[2], item[0]))
    for previous, current in zip(paired_intervals, paired_intervals[1:]):
        if previous[0] == current[0]:
            errors.append(
                f"{rig_id}: plant intervals must alternate feet; "
                f"{previous[0]} appears twice"
            )
        overlap = min(previous[2], current[2]) - max(previous[1], current[1])
        if overlap > max_double_support + 1e-6:
            errors.append(
                f"{rig_id}: double-support overlap {overlap:.2f}s exceeds "
                f"{max_double_support:.2f}s"
            )


def validate_manifest(path: Path) -> tuple[list[str], list[str], dict[str, int]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        manifest = load_manifest(path)
    except LayerError as exc:
        return [str(exc)], warnings, {"layers": 0, "animated_layers": 0}

    canvas = manifest.get("canvas", {})
    for key in ("width", "height", "fps", "duration_s"):
        try:
            if float(canvas.get(key, 0)) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"canvas.{key} must be positive")
    for key, minimum, maximum in (
        ("oversample", 1, 4),
        ("motion_blur_samples", 1, 4),
    ):
        try:
            value = int(canvas.get(key, 1))
            if value < minimum or value > maximum:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"canvas.{key} must be an integer from {minimum} to {maximum}")
    try:
        shutter = float(canvas.get("shutter", 0.5))
        if shutter < 0 or shutter > 1:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("canvas.shutter must be from 0 to 1")

    layers = manifest.get("layers")
    if not isinstance(layers, list) or not layers:
        return errors + ["layers must be a non-empty array"], warnings, {
            "layers": 0, "animated_layers": 0,
        }

    ids: set[str] = set()
    layers_by_id: dict[str, dict[str, Any]] = {}
    animated = 0
    for index, layer in enumerate(layers, 1):
        layer_id = str(layer.get("id", "")).strip()
        if not layer_id:
            errors.append(f"layer[{index}] has no id")
        elif layer_id in ids:
            errors.append(f"duplicate layer id: {layer_id}")
        ids.add(layer_id)
        if layer_id:
            layers_by_id[layer_id] = layer
        source = path.parent / str(layer.get("path", ""))
        if not source.is_file() or source.stat().st_size <= 0:
            errors.append(f"{layer_id or index}: missing layer image {source}")
        pose_sequence = layer.get("pose_sequence")
        if pose_sequence is not None:
            if not isinstance(pose_sequence, dict):
                errors.append(f"{layer_id or index}: pose_sequence must be an object")
                pose_sequence = {}
            if layer.get("sprites"):
                errors.append(
                    f"{layer_id or index}: use pose_sequence or legacy sprites, not both"
                )
            states = pose_sequence.get("states", [])
            if not isinstance(states, list) or len(states) < 2:
                errors.append(
                    f"{layer_id or index}: pose_sequence.states needs at least two states"
                )
                states = []
            state_ids: set[str] = set()
            state_times: list[float] = []
            for state_index, state in enumerate(states, 1):
                state_id = str(state.get("id", "")).strip()
                if not state_id:
                    errors.append(
                        f"{layer_id or index}: pose state[{state_index}] needs id"
                    )
                elif state_id in state_ids:
                    errors.append(
                        f"{layer_id or index}: duplicate pose state id {state_id}"
                    )
                state_ids.add(state_id)
                state_source = path.parent / str(state.get("path", ""))
                if not state_source.is_file() or state_source.stat().st_size <= 0:
                    errors.append(
                        f"{layer_id or index}: missing pose state image {state_source}"
                    )
                try:
                    state_times.append(float(state["at_s"]))
                except (KeyError, TypeError, ValueError):
                    errors.append(
                        f"{layer_id or index}: pose state[{state_index}] needs numeric at_s"
                    )
            if state_times and state_times != sorted(state_times):
                errors.append(
                    f"{layer_id or index}: pose state times must be sorted"
                )
            playback = str(pose_sequence.get("playback", "once"))
            if playback not in {"once", "loop", "ping-pong"}:
                errors.append(
                    f"{layer_id or index}: pose_sequence.playback must be once, loop, or ping-pong"
                )
            transition = str(pose_sequence.get("transition", "cut"))
            if transition not in {"cut", "crossfade"}:
                errors.append(
                    f"{layer_id or index}: pose_sequence.transition must be cut or crossfade"
                )
            try:
                blend = float(pose_sequence.get("crossfade_s", 0.0))
                if blend < 0 or (transition == "cut" and blend > 0):
                    raise ValueError
            except (TypeError, ValueError):
                errors.append(
                    f"{layer_id or index}: pose_sequence.crossfade_s is invalid"
                )
        visibility = layer.get("visibility")
        if visibility is not None:
            if not isinstance(visibility, dict):
                errors.append(f"{layer_id or index}: visibility must be an object")
            else:
                if not isinstance(visibility.get("initial", True), bool):
                    errors.append(
                        f"{layer_id or index}: visibility.initial must be boolean"
                    )
                events = visibility.get("events", [])
                if not isinstance(events, list):
                    errors.append(
                        f"{layer_id or index}: visibility.events must be an array"
                    )
                else:
                    previous_at = -1.0
                    for event_index, event in enumerate(events, 1):
                        try:
                            at_s = float(event["at_s"])
                            fade_s = float(event.get("fade_s", 0.0))
                            if at_s < previous_at or fade_s < 0:
                                raise ValueError
                            previous_at = at_s
                        except (KeyError, TypeError, ValueError):
                            errors.append(
                                f"{layer_id or index}: visibility event[{event_index}] "
                                "needs sorted at_s and non-negative fade_s"
                            )
                        if not isinstance(event.get("visible"), bool):
                            errors.append(
                                f"{layer_id or index}: visibility event[{event_index}].visible "
                                "must be boolean"
                            )
        looping = layer.get("looping_strip")
        if looping is not None:
            if not isinstance(looping, dict):
                errors.append(f"{layer_id or index}: looping_strip must be an object")
            else:
                if str(looping.get("axis", "x")) not in {"x", "y"}:
                    errors.append(
                        f"{layer_id or index}: looping_strip.axis must be x or y"
                    )
                try:
                    speed = float(looping.get("speed_px_s", 0))
                    if abs(speed) < 1e-6:
                        raise ValueError
                except (TypeError, ValueError):
                    errors.append(
                        f"{layer_id or index}: looping_strip.speed_px_s must be non-zero"
                    )
        motif = layer.get("motif_field")
        if motif is not None:
            if not isinstance(motif, dict):
                errors.append(f"{layer_id or index}: motif_field must be an object")
            else:
                area = motif.get("area")
                try:
                    area_valid = (
                        isinstance(area, list)
                        and len(area) == 4
                        and float(area[2]) > 0
                        and float(area[3]) > 0
                    )
                except (TypeError, ValueError):
                    area_valid = False
                if not area_valid:
                    errors.append(
                        f"{layer_id or index}: motif_field.area must be [x,y,width,height]"
                    )
                try:
                    count = int(motif.get("count", 0))
                    if count < 1 or count > 200:
                        raise ValueError
                except (TypeError, ValueError):
                    errors.append(
                        f"{layer_id or index}: motif_field.count must be 1..200"
                    )
        sprites = layer.get("sprites", [])
        if sprites and not isinstance(sprites, list):
            errors.append(f"{layer_id or index}: sprites must be an array")
            sprites = []
        sprite_times: list[float] = []
        for sprite_index, sprite in enumerate(sprites, 1):
            sprite_source = path.parent / str(sprite.get("path", ""))
            if not sprite_source.is_file() or sprite_source.stat().st_size <= 0:
                errors.append(
                    f"{layer_id or index}: missing sprite image {sprite_source}"
                )
            try:
                sprite_times.append(float(sprite["t"]))
            except (KeyError, TypeError, ValueError):
                errors.append(
                    f"{layer_id or index}: sprite[{sprite_index}] needs numeric t"
                )
        if sprite_times and sprite_times != sorted(sprite_times):
            errors.append(f"{layer_id or index}: sprite times must be sorted")
        if layer.get("sprite_loop") and sprites:
            try:
                sprite_duration = float(layer.get("sprite_duration_s", 0))
                if sprite_duration <= sprite_times[-1]:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append(
                    f"{layer_id or index}: sprite loop duration must exceed last sprite t"
                )
        motion_class = str(layer.get("motion_class", "")).strip()
        if motion_class and motion_class not in MOTION_CLASSES:
            errors.append(
                f"{layer_id or index}: unsupported motion_class {motion_class!r}"
            )
        motion_intent = str(layer.get("motion_intent", "")).strip()
        if motion_intent and motion_intent not in MOTION_INTENTS:
            errors.append(
                f"{layer_id or index}: unsupported motion_intent {motion_intent!r}; "
                f"choose from {', '.join(sorted(MOTION_INTENTS))}"
            )
        transition = str(layer.get("sprite_transition", "crossfade")).strip()
        if transition not in {"cut", "crossfade"}:
            errors.append(
                f"{layer_id or index}: sprite_transition must be cut or crossfade"
            )
        crossfade = max(0.0, float(layer.get("sprite_crossfade_s", 0.0)))
        if motion_class == "major-pose" and crossfade > 0:
            errors.append(
                f"{layer_id or index}: major-pose sprites cannot crossfade; "
                "change pose at a shot cut or behind an occluding paper layer"
            )
        if transition == "cut" and crossfade > 0:
            errors.append(
                f"{layer_id or index}: sprite_transition=cut requires "
                "sprite_crossfade_s=0"
            )
        motion_path = layer.get("motion_path")
        if motion_path is not None:
            points = motion_path.get("points", []) if isinstance(motion_path, dict) else []
            if (
                len(points) != 4
                or any(
                    not isinstance(point, list)
                    or len(point) != 2
                    for point in points
                )
            ):
                errors.append(
                    f"{layer_id or index}: motion_path.points needs four [x, y] pairs"
                )
            try:
                start_s = float(motion_path.get("start_s", 0))
                end_s = float(motion_path["end_s"])
                if end_s <= start_s:
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                errors.append(
                    f"{layer_id or index}: motion_path needs end_s greater than start_s"
                )
        pivot = layer.get("pivot")
        if pivot is not None and (
            not isinstance(pivot, list)
            or len(pivot) != 2
        ):
            errors.append(f"{layer_id or index}: pivot must be [canvas_x, canvas_y]")
        if motion_class == "hinged-part" and pivot is None:
            errors.append(
                f"{layer_id or index}: hinged-part needs a canvas-space pivot"
            )
        anchor = layer.get("anchor")
        if anchor is not None and (
            not isinstance(anchor, list)
            or len(anchor) != 2
        ):
            errors.append(f"{layer_id or index}: anchor must be [x_ratio, y_ratio]")
        keyframes = layer.get("keyframes")
        if not isinstance(keyframes, list) or not keyframes:
            errors.append(f"{layer_id or index}: keyframes must be non-empty")
            continue
        times: list[float] = []
        for frame_index, frame in enumerate(keyframes):
            try:
                times.append(float(frame["t"]))
            except (KeyError, TypeError, ValueError):
                errors.append(f"{layer_id or index}: every keyframe needs numeric t")
                break
            segment_easing = frame.get("ease")
            if segment_easing is not None and str(segment_easing) not in EASINGS:
                errors.append(
                    f"{layer_id or index}: keyframe[{frame_index}].ease "
                    f"{segment_easing!r} is unsupported"
                )
        if times and times != sorted(times):
            errors.append(f"{layer_id or index}: keyframe times must be sorted")
        if len(times) != len(set(times)):
            errors.append(f"{layer_id or index}: keyframe times must be unique")
        easing = str(layer.get("easing", "smoothstep"))
        if easing not in EASINGS:
            errors.append(
                f"{layer_id or index}: unsupported easing {easing!r}; "
                f"choose from {', '.join(sorted(EASINGS))}"
            )
        if layer.get("loop") and times and times[-1] <= times[0]:
            errors.append(f"{layer_id or index}: loop needs a positive keyframe span")
        if motion_class == "rigid-body":
            for frame in keyframes:
                if abs(float(frame.get("scale_x", 1.0)) - 1.0) > 0.08:
                    warnings.append(
                        f"{layer_id or index}: rigid-body scale_x changes more than 8%; "
                        "prefer translation or pivot rotation"
                    )
                    break
                if abs(float(frame.get("scale_y", 1.0)) - 1.0) > 0.08:
                    warnings.append(
                        f"{layer_id or index}: rigid-body scale_y changes more than 8%; "
                        "prefer translation or pivot rotation"
                    )
                    break
        if layer_is_animated(layer):
            animated += 1

    registration = manifest.get("registration")
    if registration is not None:
        if not isinstance(registration, dict):
            errors.append("registration must be an object")
        else:
            members = registration.get("members", [])
            if not isinstance(members, list) or not members:
                errors.append("registration.members must be a non-empty array")
                members = []
            missing_members = [
                str(member) for member in members
                if str(member) not in layers_by_id
            ]
            if missing_members:
                errors.append(
                    "registration references missing layers: "
                    + ", ".join(missing_members)
                )
            expected_size = (
                int(canvas.get("width", 0)),
                int(canvas.get("height", 0)),
            )
            for member in members:
                layer = layers_by_id.get(str(member))
                if not layer:
                    continue
                paths = [str(layer.get("path", ""))]
                pose = layer.get("pose_sequence", {})
                paths.extend(
                    str(item.get("path", ""))
                    for item in pose.get("states", [])
                    if isinstance(item, dict)
                )
                for source_name in paths:
                    source_path = path.parent / source_name
                    if not source_path.is_file():
                        continue
                    try:
                        with Image.open(source_path) as image:
                            actual_size = image.size
                    except OSError as exc:
                        errors.append(
                            f"{member}: cannot inspect registered source "
                            f"{source_name}: {exc}"
                        )
                        continue
                    if actual_size != expected_size:
                        errors.append(
                            f"{member}: registered source {source_name} is "
                            f"{actual_size[0]}x{actual_size[1]}, expected "
                            f"{expected_size[0]}x{expected_size[1]}"
                        )

    duration = float(canvas.get("duration_s", 0.0))
    validate_follow_contract(layers_by_id, duration, errors)
    quality = manifest.get("quality", {})
    min_layers = int(quality.get("min_layers", 4))
    min_animated = int(quality.get("min_animated_layers", 3))
    if len(layers) < min_layers:
        errors.append(f"layer count {len(layers)} is below required {min_layers}")
    if animated < min_animated:
        errors.append(f"animated layer count {animated} is below required {min_animated}")
    if len({layer.get("z", 0) for layer in layers}) < min(3, len(layers)):
        warnings.append("fewer than three distinct depth planes")
    validate_direction(manifest, layers_by_id, animated, errors, warnings)
    rigs = manifest.get("rigs", [])
    if rigs and not isinstance(rigs, list):
        errors.append("rigs must be an array")
        rigs = []
    for rig_index, rig in enumerate(rigs, 1):
        if not isinstance(rig, dict):
            errors.append(f"rig[{rig_index}] must be an object")
            continue
        rig_id = str(rig.get("id", f"rig[{rig_index}]"))
        parts = rig.get("parts", [])
        if not isinstance(parts, list) or len(parts) < 2:
            errors.append(f"{rig_id}: rig parts must name at least two layers")
            continue
        missing = [str(part) for part in parts if str(part) not in layers_by_id]
        if missing:
            errors.append(f"{rig_id}: missing rig layers {', '.join(missing)}")
            continue
        if rig.get("type") == "hinged-paper":
            rig_pivot = rig.get("pivot")
            if not isinstance(rig_pivot, list) or len(rig_pivot) != 2:
                errors.append(f"{rig_id}: hinged-paper rig needs a shared pivot")
                continue
            member_layers = [layers_by_id[str(part)] for part in parts]
            if any(member.get("pivot") != rig_pivot for member in member_layers):
                errors.append(
                    f"{rig_id}: every hinged-paper part must use the shared pivot"
                )
            paths = [member.get("motion_path") for member in member_layers]
            if any(path is not None for path in paths) and any(
                path != paths[0] for path in paths[1:]
            ):
                errors.append(
                    f"{rig_id}: all hinged-paper parts must share one root motion_path"
                )
        if rig.get("type") == "articulated-paper":
            root_id = str(rig.get("root", "")).strip()
            part_ids = {str(part) for part in parts}
            if root_id not in part_ids:
                errors.append(
                    f"{rig_id}: articulated-paper root must be one of its parts"
                )
                continue
            for part_id in part_ids - {root_id}:
                follow = layers_by_id[part_id].get("follow")
                if (
                    not isinstance(follow, dict)
                    or follow.get("space") != "rig"
                    or str(follow.get("parent", "")) not in part_ids
                ):
                    errors.append(
                        f"{rig_id}: {part_id} must rig-follow another part"
                    )
                    continue
                cursor = part_id
                visited: set[str] = set()
                while cursor != root_id:
                    if cursor in visited:
                        break
                    visited.add(cursor)
                    cursor_follow = layers_by_id[cursor].get("follow", {})
                    cursor = str(cursor_follow.get("parent", ""))
                    if cursor not in part_ids:
                        break
                if cursor != root_id:
                    errors.append(
                        f"{rig_id}: {part_id} is not connected to root {root_id}"
                    )
            validate_locomotion_contract(
                manifest,
                rig_id,
                rig,
                root_id,
                part_ids,
                layers_by_id,
                duration,
                errors,
            )
    return errors, warnings, {"layers": len(layers), "animated_layers": animated}


def smoothstep(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * value * (3.0 - 2.0 * value)


def smootherstep(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * value * value * (value * (value * 6.0 - 15.0) + 10.0)


def ease(value: float, name: str) -> float:
    value = min(1.0, max(0.0, value))
    if name == "linear" or name == "catmull-rom":
        return value
    if name == "hold":
        return 0.0 if value < 1.0 else 1.0
    if name == "smoothstep":
        return smoothstep(value)
    if name == "smootherstep":
        return smootherstep(value)
    if name == "ease-in":
        return value * value * value
    if name == "ease-out":
        return 1.0 - (1.0 - value) ** 3
    if name == "ease-in-out":
        return (
            4.0 * value * value * value
            if value < 0.5
            else 1.0 - ((-2.0 * value + 2.0) ** 3) / 2.0
        )
    overshoot = 1.70158
    if name == "back-in":
        return (overshoot + 1.0) * value ** 3 - overshoot * value ** 2
    if name == "back-out":
        shifted = value - 1.0
        return 1.0 + (overshoot + 1.0) * shifted ** 3 + overshoot * shifted ** 2
    if name == "back-in-out":
        scaled = overshoot * 1.525
        if value < 0.5:
            return ((2.0 * value) ** 2 * (
                (scaled + 1.0) * 2.0 * value - scaled
            )) / 2.0
        shifted = 2.0 * value - 2.0
        return (
            shifted ** 2 * ((scaled + 1.0) * shifted + scaled) + 2.0
        ) / 2.0
    return value


def frame_value(frame: dict[str, Any], key: str) -> float:
    return float(frame.get(key, DEFAULT_TRANSFORM[key]))


def catmull_rom(left_outer: float, left: float, right: float,
                right_outer: float, value: float) -> float:
    value_2 = value * value
    value_3 = value_2 * value
    return 0.5 * (
        2.0 * left
        + (-left_outer + right) * value
        + (2.0 * left_outer - 5.0 * left + 4.0 * right - right_outer) * value_2
        + (-left_outer + 3.0 * left - 3.0 * right + right_outer) * value_3
    )


def timeline_time(layer: dict[str, Any], time_s: float) -> float:
    frames = layer["keyframes"]
    if not layer.get("loop"):
        return time_s
    start = float(frames[0]["t"])
    end = float(frames[-1]["t"])
    span = end - start
    if span <= 0:
        return time_s
    phase = float(layer.get("phase_s", 0.0))
    return start + ((time_s - start + phase) % span)


def cubic_bezier(points: list[list[float]], value: float) -> tuple[float, float]:
    inverse = 1.0 - value
    weights = (
        inverse ** 3,
        3.0 * inverse * inverse * value,
        3.0 * inverse * value * value,
        value ** 3,
    )
    x = sum(float(points[index][0]) * weights[index] for index in range(4))
    y = sum(float(points[index][1]) * weights[index] for index in range(4))
    return x, y


def cubic_bezier_tangent(points: list[list[float]], value: float) -> tuple[float, float]:
    inverse = 1.0 - value
    x = (
        3.0 * inverse * inverse * (float(points[1][0]) - float(points[0][0]))
        + 6.0 * inverse * value * (float(points[2][0]) - float(points[1][0]))
        + 3.0 * value * value * (float(points[3][0]) - float(points[2][0]))
    )
    y = (
        3.0 * inverse * inverse * (float(points[1][1]) - float(points[0][1]))
        + 6.0 * inverse * value * (float(points[2][1]) - float(points[1][1]))
        + 3.0 * value * value * (float(points[3][1]) - float(points[2][1]))
    )
    return x, y


def motion_path_at(layer: dict[str, Any], time_s: float) -> tuple[float, float, float]:
    path = layer.get("motion_path")
    if not path:
        return 0.0, 0.0, 0.0
    start = float(path.get("start_s", 0.0))
    end = float(path["end_s"])
    span = end - start
    local = time_s + float(path.get("phase_s", 0.0))
    if path.get("loop"):
        local = start + ((local - start) % span)
    progress = (local - start) / span
    progress = ease(progress, str(path.get("easing", "ease-in-out")))
    points = path["points"]
    x, y = cubic_bezier(points, progress)
    rotation = 0.0
    if path.get("orient_to_path"):
        tangent_x, tangent_y = cubic_bezier_tangent(points, progress)
        if abs(tangent_x) > 1e-6 or abs(tangent_y) > 1e-6:
            rotation = math.degrees(math.atan2(tangent_y, tangent_x))
            rotation += float(path.get("rotation_offset", 0.0))
    return x, y, rotation


def visibility_at(layer: dict[str, Any], time_s: float) -> float:
    config = layer.get("visibility")
    if not isinstance(config, dict):
        return 1.0
    current = 1.0 if config.get("initial", True) else 0.0
    for event in config.get("events", []):
        at_s = float(event["at_s"])
        if time_s < at_s:
            break
        target = 1.0 if event["visible"] else 0.0
        fade_s = max(0.0, float(event.get("fade_s", 0.0)))
        if fade_s > 0 and time_s < at_s + fade_s:
            progress = smoothstep((time_s - at_s) / fade_s)
            return current + (target - current) * progress
        current = target
    return current


def transform_at(layer: dict[str, Any], time_s: float) -> dict[str, float]:
    frames = layer["keyframes"]
    world_time_s = time_s
    time_s = timeline_time(layer, time_s)
    before = frames[0]
    after = frames[-1]
    segment = len(frames) - 1
    for index in range(1, len(frames)):
        if time_s <= float(frames[index]["t"]):
            before, after = frames[index - 1], frames[index]
            segment = index
            break
    start = float(before["t"])
    end = float(after["t"])
    progress = 0.0 if end <= start else (time_s - start) / (end - start)
    easing = str(after.get("ease", layer.get("easing", "smoothstep")))
    progress = ease(progress, easing)
    result: dict[str, float] = {}
    for key in TRANSFORM_KEYS:
        left = frame_value(before, key)
        right = frame_value(after, key)
        if easing == "catmull-rom" and len(frames) >= 3:
            if layer.get("loop") and segment == 1:
                left_outer = frame_value(frames[-2], key)
            else:
                left_outer = frame_value(frames[max(0, segment - 2)], key)
            if layer.get("loop") and segment == len(frames) - 1:
                right_outer = frame_value(frames[1], key)
            else:
                right_outer = frame_value(frames[min(len(frames) - 1, segment + 1)], key)
            result[key] = catmull_rom(
                left_outer, left, right, right_outer, progress
            )
        else:
            result[key] = left + (right - left) * progress
    result["opacity"] = min(1.0, max(0.0, result["opacity"]))
    result["opacity"] *= visibility_at(layer, world_time_s)
    path_x, path_y, path_rotation = motion_path_at(layer, time_s)
    result["x"] += path_x
    result["y"] += path_y
    result["rotation"] += path_rotation
    return result


def resolved_transform_at(
    layer: dict[str, Any],
    layers_by_id: dict[str, dict[str, Any]],
    time_s: float,
    cache: dict[tuple[str, float], dict[str, float]] | None = None,
    stack: tuple[str, ...] = (),
) -> dict[str, float]:
    layer_id = str(layer.get("id", ""))
    cache = cache if cache is not None else {}
    cache_key = (layer_id, round(time_s, 6))
    if cache_key in cache:
        return dict(cache[cache_key])
    if layer_id in stack:
        raise LayerError(f"follow hierarchy contains a cycle at {layer_id}")
    result = transform_at(layer, time_s)
    follow = layer.get("follow")
    if isinstance(follow, dict):
        parent_id = str(follow.get("parent", ""))
        parent = layers_by_id.get(parent_id)
        if parent is None:
            raise LayerError(f"{layer_id}: missing follow parent {parent_id!r}")
        lag_s = max(0.0, float(follow.get("lag_s", 0.0)))
        parent_values = resolved_transform_at(
            parent,
            layers_by_id,
            max(0.0, time_s - lag_s),
            cache,
            stack + (layer_id,),
        )
        inherit = follow.get("inherit", {"x": 1.0, "y": 1.0})
        rig_space = str(follow.get("space", "world")) == "rig"
        if rig_space:
            parent_pivot = parent.get("pivot")
            child_pivot = layer.get("pivot")
            if not isinstance(parent_pivot, list) or not isinstance(child_pivot, list):
                raise LayerError(
                    f"{layer_id}: rig-space follow needs parent and child pivots"
                )
            vector_x = float(child_pivot[0]) - float(parent_pivot[0])
            vector_y = float(child_pivot[1]) - float(parent_pivot[1])
            parent_scale = parent_values["scale"]
            vector_x *= parent_scale * parent_values["scale_x"]
            vector_y *= parent_scale * parent_values["scale_y"]
            angle = math.radians(parent_values["rotation"])
            rotated_x = vector_x * math.cos(angle) - vector_y * math.sin(angle)
            rotated_y = vector_x * math.sin(angle) + vector_y * math.cos(angle)
            world_child_x = (
                float(parent_pivot[0]) + parent_values["x"] + rotated_x
            )
            world_child_y = (
                float(parent_pivot[1]) + parent_values["y"] + rotated_y
            )
            result["x"] += (
                world_child_x - float(child_pivot[0])
            ) * float(inherit.get("x", 0.0))
            result["y"] += (
                world_child_y - float(child_pivot[1])
            ) * float(inherit.get("y", 0.0))
        for key, raw_weight in inherit.items():
            if rig_space and key in {"x", "y"}:
                continue
            weight = float(raw_weight)
            if key in {"scale", "scale_x", "scale_y", "opacity"}:
                result[key] *= 1.0 + (parent_values[key] - 1.0) * weight
            else:
                result[key] += parent_values[key] * weight
        result["opacity"] = min(1.0, max(0.0, result["opacity"]))
    cache[cache_key] = dict(result)
    return result


def continuous_keyframe_stalls(layer: dict[str, Any]) -> list[dict[str, Any]]:
    """Find stop-start interior knots on layers explicitly authored for continuous travel."""
    if str(layer.get("motion_intent", "")).strip() != "continuous":
        return []
    frames = layer.get("keyframes", [])
    if len(frames) < 3:
        return []
    layer_easing = str(layer.get("easing", "smoothstep"))
    stalls: list[dict[str, Any]] = []
    for index in range(1, len(frames) - 1):
        left, knot, right = frames[index - 1:index + 2]
        left_dt = float(knot["t"]) - float(left["t"])
        right_dt = float(right["t"]) - float(knot["t"])
        if left_dt <= 0 or right_dt <= 0:
            continue
        incoming = str(knot.get("ease", layer_easing))
        outgoing = str(right.get("ease", layer_easing))

        left_dx = frame_value(knot, "x") - frame_value(left, "x")
        left_dy = frame_value(knot, "y") - frame_value(left, "y")
        right_dx = frame_value(right, "x") - frame_value(knot, "x")
        right_dy = frame_value(right, "y") - frame_value(knot, "y")
        left_distance = math.hypot(left_dx, left_dy)
        right_distance = math.hypot(right_dx, right_dy)
        same_translation_direction = (
            left_distance >= 2.0
            and right_distance >= 2.0
            and (left_dx * right_dx + left_dy * right_dy)
            / (left_distance * right_distance) >= 0.85
        )

        continuous_properties: list[str] = []
        if same_translation_direction:
            continuous_properties.append("translation")
        for key, threshold in (
            ("rotation", 0.8),
            ("scale", 0.008),
            ("scale_x", 0.008),
            ("scale_y", 0.008),
            ("opacity", 0.06),
        ):
            left_delta = frame_value(knot, key) - frame_value(left, key)
            right_delta = frame_value(right, key) - frame_value(knot, key)
            if (
                abs(left_delta) >= threshold
                and abs(right_delta) >= threshold
                and left_delta * right_delta > 0
            ):
                continuous_properties.append(key)
        if not continuous_properties:
            continue

        curves_are_continuous = incoming == outgoing == "catmull-rom"
        if incoming == outgoing == "linear":
            if same_translation_direction:
                left_speed = left_distance / left_dt
                right_speed = right_distance / right_dt
                ratio = max(left_speed, right_speed) / max(
                    1e-6, min(left_speed, right_speed)
                )
                curves_are_continuous = ratio <= 1.25
            else:
                curves_are_continuous = True
                for key in continuous_properties:
                    if key == "translation":
                        continue
                    left_rate = abs(
                        frame_value(knot, key) - frame_value(left, key)
                    ) / left_dt
                    right_rate = abs(
                        frame_value(right, key) - frame_value(knot, key)
                    ) / right_dt
                    ratio = max(left_rate, right_rate) / max(
                        1e-6, min(left_rate, right_rate)
                    )
                    if ratio > 1.25:
                        curves_are_continuous = False
                        break
        if curves_are_continuous:
            continue
        stalls.append({
            "layer": str(layer.get("id", "")),
            "keyframe_index": index,
            "time_s": float(knot["t"]),
            "properties": continuous_properties,
            "incoming_ease": incoming,
            "outgoing_ease": outgoing,
        })
    return stalls


def audit_motion_continuity(manifest: dict[str, Any]) -> dict[str, Any]:
    canvas = manifest["canvas"]
    duration = float(canvas["duration_s"])
    source_fps = int(canvas["fps"])
    audit_config = manifest.get("quality", {}).get("motion_audit", {})
    if audit_config is False:
        return {"enabled": False, "issues": [], "layers": 0, "followers": 0}
    if not isinstance(audit_config, dict):
        audit_config = {}
    sample_fps = max(
        1,
        min(60, int(audit_config.get("sample_fps", source_fps))),
    )
    diagonal = math.hypot(float(canvas["width"]), float(canvas["height"]))
    limits = {
        "speed_px_s": float(audit_config.get("max_speed_px_s", diagonal * 2.4)),
        "rotation_deg_s": float(
            audit_config.get("max_rotation_deg_s", 720.0)
        ),
        "scale_per_s": float(audit_config.get("max_scale_per_s", 3.0)),
        "opacity_per_s": float(audit_config.get("max_opacity_per_s", 8.0)),
    }
    layers_by_id = {
        str(layer["id"]): layer for layer in manifest["layers"]
    }
    samples = max(1, round(duration * sample_fps))
    times = [min(duration, index / sample_fps) for index in range(samples + 1)]
    if times[-1] < duration:
        times.append(duration)
    maxima = {
        "speed_px_s": {"value": 0.0, "layer": ""},
        "rotation_deg_s": {"value": 0.0, "layer": ""},
        "scale_per_s": {"value": 0.0, "layer": ""},
        "opacity_per_s": {"value": 0.0, "layer": ""},
    }
    issues: list[str] = []
    enforce_smooth_keyframes = bool(
        audit_config.get("enforce_smooth_keyframes", False)
    )
    max_interior_stalls = max(
        0, int(audit_config.get("max_interior_stalls", 0))
    )
    interior_stalls: list[dict[str, Any]] = []
    for layer_id, layer in layers_by_id.items():
        if not layer_is_animated(layer) and not layer.get("follow"):
            continue
        values = [
            resolved_transform_at(layer, layers_by_id, time_s)
            for time_s in times
        ]
        layer_maxima = {key: 0.0 for key in maxima}
        for index in range(1, len(values)):
            dt = max(1e-6, times[index] - times[index - 1])
            before, after = values[index - 1], values[index]
            rates = {
                "speed_px_s": math.hypot(
                    after["x"] - before["x"], after["y"] - before["y"]
                ) / dt,
                "rotation_deg_s": abs(
                    after["rotation"] - before["rotation"]
                ) / dt,
                "scale_per_s": max(
                    abs(after[key] - before[key]) / dt
                    for key in ("scale", "scale_x", "scale_y")
                ),
                "opacity_per_s": abs(
                    after["opacity"] - before["opacity"]
                ) / dt,
            }
            for key, value in rates.items():
                layer_maxima[key] = max(layer_maxima[key], value)
                if value > float(maxima[key]["value"]):
                    maxima[key] = {"value": value, "layer": layer_id}
        for key, value in layer_maxima.items():
            if value > limits[key] + 1e-6:
                issues.append(
                    f"{layer_id}: {key} {value:.1f} exceeds {limits[key]:.1f}"
                )
        if enforce_smooth_keyframes:
            interior_stalls.extend(continuous_keyframe_stalls(layer))

    if len(interior_stalls) > max_interior_stalls:
        for stall in interior_stalls:
            issues.append(
                f"{stall['layer']}: continuous {','.join(stall['properties'])} "
                f"stops at interior keyframe {stall['keyframe_index']} "
                f"({stall['time_s']:.2f}s; {stall['incoming_ease']} -> "
                f"{stall['outgoing_ease']}); use catmull-rom or matched linear"
            )

    for index, contact in enumerate(manifest.get("direction", {}).get("contacts", [])):
        layer_id = str(contact["layer"])
        layer = layers_by_id[layer_id]
        property_name = str(contact["property"])
        start = float(contact["start_s"])
        end = float(contact["end_s"])
        tolerance = float(contact.get("tolerance", 1.0))
        contact_times = [
            start + (end - start) * step / max(1, round((end - start) * sample_fps))
            for step in range(max(1, round((end - start) * sample_fps)) + 1)
        ]
        values = [
            resolved_transform_at(layer, layers_by_id, time_s)[property_name]
            for time_s in contact_times
        ]
        drift = max(values) - min(values)
        if drift > tolerance + 1e-6:
            issues.append(
                f"contact[{index}] {layer_id}.{property_name} drifts "
                f"{drift:.2f} after contact; tolerance {tolerance:.2f}"
            )

    locomotion_rigs = [
        rig
        for rig in manifest.get("rigs", [])
        if isinstance(rig, dict) and isinstance(rig.get("locomotion"), dict)
    ]
    plant_intervals = {
        (
            str(contact.get("layer", "")),
            float(contact.get("start_s", 0.0)),
            float(contact.get("end_s", 0.0)),
        )
        for rig in locomotion_rigs
        for contact in manifest.get("direction", {}).get("contacts", [])
        if isinstance(contact, dict)
        and str(contact.get("layer", ""))
        in {str(item) for item in rig["locomotion"].get("feet", [])}
        and str(contact.get("property", "")) in {"x", "y"}
    }
    return {
        "enabled": True,
        "issues": issues,
        "sample_fps": sample_fps,
        "layers": sum(
            layer_is_animated(layer) or bool(layer.get("follow"))
            for layer in layers_by_id.values()
        ),
        "followers": sum(bool(layer.get("follow")) for layer in layers_by_id.values()),
        "rig_followers": sum(
            isinstance(layer.get("follow"), dict)
            and layer["follow"].get("space", "world") == "rig"
            for layer in layers_by_id.values()
        ),
        "locomotion_rigs": len(locomotion_rigs),
        "plant_intervals": len(plant_intervals),
        "interior_stalls": interior_stalls,
        "smooth_keyframes_enforced": enforce_smooth_keyframes,
        "limits": limits,
        "maxima": maxima,
    }


def apply_transform(source: Image.Image, values: dict[str, float],
                    oversample: int = 1,
                    pivot: list[float] | None = None,
                    anchor: list[float] | None = None,
                    ) -> tuple[Image.Image, tuple[int, int]]:
    bbox = source.getbbox()
    if bbox is None:
        return Image.new("RGBA", (1, 1)), (0, 0)
    crop = source.crop(bbox)
    if pivot is not None:
        anchor_x = float(pivot[0]) - bbox[0]
        anchor_y = float(pivot[1]) - bbox[1]
    else:
        anchor = anchor or [0.5, 0.5]
        anchor_x = crop.width * float(anchor[0])
        anchor_y = crop.height * float(anchor[1])
    scale = max(0.01, values["scale"])
    scale_x = max(0.01, values["scale_x"] * scale)
    scale_y = max(0.01, values["scale_y"] * scale)
    width = max(1, round(crop.width * scale_x * oversample))
    height = max(1, round(crop.height * scale_y * oversample))
    anchor_x *= scale_x * oversample
    anchor_y *= scale_y * oversample
    if (width, height) != crop.size:
        crop = crop.resize((width, height), Image.Resampling.LANCZOS)
    rotation = values["rotation"]
    if abs(rotation) > 1e-6:
        radius = math.ceil(max(
            anchor_x,
            crop.width - anchor_x,
            anchor_y,
            crop.height - anchor_y,
        )) + 3
        stage = Image.new("RGBA", (radius * 2, radius * 2), (0, 0, 0, 0))
        stage.alpha_composite(
            crop,
            (round(radius - anchor_x), round(radius - anchor_y)),
        )
        stage = stage.rotate(
            -rotation,
            resample=Image.Resampling.BICUBIC,
            expand=False,
        )
        rotated_bbox = stage.getbbox()
        if rotated_bbox is None:
            return Image.new("RGBA", (1, 1)), (0, 0)
        crop = stage.crop(rotated_bbox)
        anchor_x = radius - rotated_bbox[0]
        anchor_y = radius - rotated_bbox[1]
    opacity = min(1.0, max(0.0, values["opacity"]))
    if opacity < 0.999:
        alpha = crop.getchannel("A").point(lambda value: round(value * opacity))
        crop.putalpha(alpha)
    world_x = (bbox[0] + (
        float(pivot[0]) - bbox[0]
        if pivot is not None else source.crop(bbox).width * float((anchor or [0.5, 0.5])[0])
    ) + values["x"]) * oversample
    world_y = (bbox[1] + (
        float(pivot[1]) - bbox[1]
        if pivot is not None else source.crop(bbox).height * float((anchor or [0.5, 0.5])[1])
    ) + values["y"]) * oversample
    position = (round(world_x - anchor_x), round(world_y - anchor_y))
    return crop, position


def load_layer_sources(
    manifest_path: Path,
    manifest: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Image.Image]]]:
    loaded: list[tuple[dict[str, Any], dict[str, Image.Image]]] = []
    for layer in sorted(manifest["layers"], key=lambda item: float(item.get("z", 0))):
        paths = {str(layer["path"])}
        paths.update(str(item["path"]) for item in layer.get("sprites", []))
        paths.update(
            str(item["path"])
            for item in layer.get("pose_sequence", {}).get("states", [])
        )
        sources = {
            item: Image.open(manifest_path.parent / item).convert("RGBA")
            for item in paths
        }
        loaded.append((layer, sources))
    return loaded


def pose_at(
    layer: dict[str, Any],
    sources: dict[str, Image.Image],
    time_s: float,
) -> tuple[Image.Image, dict[str, Any]] | None:
    sequence = layer.get("pose_sequence")
    if not isinstance(sequence, dict):
        return None
    states = sequence.get("states", [])
    if not states:
        return None
    local = time_s + float(sequence.get("phase_s", 0.0))
    first = float(states[0]["at_s"])
    last = float(states[-1]["at_s"])
    span = max(0.0, last - first)
    playback = str(sequence.get("playback", "once"))
    if span > 0 and playback == "loop":
        local = first + ((local - first) % span)
    elif span > 0 and playback == "ping-pong":
        cycle = span * 2.0
        offset = (local - first) % cycle
        local = first + (offset if offset <= span else cycle - offset)
    current_index = 0
    for index, state in enumerate(states):
        if local >= float(state["at_s"]):
            current_index = index
        else:
            break
    current = states[current_index]
    next_index = current_index + 1
    if next_index >= len(states):
        if playback == "loop" and span > 0:
            next_index = 0
            next_time = last
        else:
            next_time = None
    else:
        next_time = float(states[next_index]["at_s"])
    blend_s = max(0.0, float(sequence.get("crossfade_s", 0.0)))
    if (
        sequence.get("transition", "cut") == "crossfade"
        and next_time is not None
        and blend_s > 0
        and local >= next_time - blend_s
    ):
        progress = min(
            1.0,
            max(0.0, (local - (next_time - blend_s)) / blend_s),
        )
        next_state = states[next_index]
        current_image = sources[str(current["path"])]
        next_image = sources[str(next_state["path"])]
        if current_image.size != next_image.size:
            raise LayerError(
                f"{layer.get('id')}: registered pose states have different canvas sizes"
            )
        return Image.blend(current_image, next_image, progress), next_state
    return sources[str(current["path"])], current


def sprite_at(
    layer: dict[str, Any],
    sources: dict[str, Image.Image],
    time_s: float,
) -> tuple[Image.Image, dict[str, Any]]:
    posed = pose_at(layer, sources, time_s)
    if posed is not None:
        return posed
    sprites = layer.get("sprites", [])
    if not sprites:
        return sources[str(layer["path"])], layer
    local = time_s + float(layer.get("sprite_phase_s", 0.0))
    duration = float(layer.get("sprite_duration_s", 0.0))
    if layer.get("sprite_loop") and duration > 0:
        local %= duration
    current_index = 0
    for index, sprite in enumerate(sprites):
        if local >= float(sprite["t"]):
            current_index = index
        else:
            break
    current = sprites[current_index]
    next_index = current_index + 1
    next_time: float | None = None
    if next_index < len(sprites):
        next_time = float(sprites[next_index]["t"])
    elif layer.get("sprite_loop") and duration > 0:
        next_index = 0
        next_time = duration
    blend_s = max(0.0, float(layer.get("sprite_crossfade_s", 0.0)))
    if (
        next_time is not None
        and blend_s > 0
        and local >= next_time - blend_s
    ):
        progress = min(1.0, max(0.0, (local - (next_time - blend_s)) / blend_s))
        next_sprite = sprites[next_index]
        current_image = sources[str(current["path"])]
        next_image = sources[str(next_sprite["path"])]
        if current_image.size != next_image.size:
            size = (
                max(current_image.width, next_image.width),
                max(current_image.height, next_image.height),
            )
            current_stage = Image.new("RGBA", size, (0, 0, 0, 0))
            next_stage = Image.new("RGBA", size, (0, 0, 0, 0))
            current_stage.alpha_composite(current_image, (0, 0))
            next_stage.alpha_composite(next_image, (0, 0))
            current_image, next_image = current_stage, next_stage
        return Image.blend(current_image, next_image, progress), next_sprite
    return sources[str(current["path"])], current


def render_frame(manifest_path: Path, time_s: float,
                 loaded: list[tuple[dict[str, Any], dict[str, Image.Image]]] | None = None,
                 manifest: dict[str, Any] | None = None) -> Image.Image:
    manifest = manifest or load_manifest(manifest_path)
    canvas_data = manifest["canvas"]
    canvas = (int(canvas_data["width"]), int(canvas_data["height"]))
    oversample = int(canvas_data.get("oversample", 1))
    render_canvas = (canvas[0] * oversample, canvas[1] * oversample)
    frame = Image.new("RGBA", render_canvas, (0, 0, 0, 0))
    if loaded is None:
        loaded = load_layer_sources(manifest_path, manifest)
    layers_by_id = {
        str(layer["id"]): layer for layer, _ in loaded
    }
    transform_cache: dict[tuple[str, float], dict[str, float]] = {}
    for layer, sources in loaded:
        source, sprite = sprite_at(layer, sources, time_s)
        values = resolved_transform_at(
            layer, layers_by_id, time_s, transform_cache
        )
        pivot = sprite.get("pivot", layer.get("pivot"))
        anchor = sprite.get("anchor", layer.get("anchor"))
        motif = layer.get("motif_field")
        looping = layer.get("looping_strip")
        if isinstance(motif, dict):
            area = [float(value) for value in motif["area"]]
            scale_range = motif.get("scale_range", [0.75, 1.15])
            drift = motif.get("drift_px", [8.0, 16.0])
            spin = float(motif.get("spin_deg", 6.0))
            seed = int(motif.get("seed", 0))
            count = int(motif["count"])
            stagger = max(0.0, float(motif.get("stagger_s", 0.04)))
            base_bbox = source.getbbox()
            if base_bbox is None:
                continue
            base_x = (base_bbox[0] + base_bbox[2]) / 2.0
            base_y = (base_bbox[1] + base_bbox[3]) / 2.0
            for motif_index in range(count):
                rng = random.Random(seed + motif_index * 104729)
                target_x = area[0] + rng.random() * area[2]
                target_y = area[1] + rng.random() * area[3]
                local_values = dict(values)
                local_values["x"] += target_x - base_x
                local_values["y"] += target_y - base_y
                local_values["scale"] *= (
                    float(scale_range[0])
                    + rng.random() * (
                        float(scale_range[1]) - float(scale_range[0])
                    )
                )
                phase = rng.random() * math.tau
                local_values["x"] += float(drift[0]) * math.sin(time_s * 0.9 + phase)
                local_values["y"] += float(drift[1]) * math.sin(time_s * 0.7 + phase)
                local_values["rotation"] += spin * math.sin(time_s * 0.8 + phase)
                if stagger > 0:
                    local_values["opacity"] *= smoothstep(
                        (time_s - motif_index * stagger) / max(0.08, stagger)
                    )
                transformed, position = apply_transform(
                    source, local_values, oversample, pivot, anchor
                )
                frame.alpha_composite(transformed, position)
        elif isinstance(looping, dict):
            local_values = dict(values)
            start_s = float(looping.get("start_s", 0.0))
            end_s = float(looping.get("end_s", canvas_data["duration_s"]))
            active_time = min(end_s, max(start_s, time_s)) - start_s
            axis = str(looping.get("axis", "x"))
            travel = (
                float(looping["speed_px_s"]) * active_time
                + float(looping.get("phase_px", 0.0))
            )
            local_values[axis] += travel
            transformed, position = apply_transform(
                source, local_values, oversample, pivot, anchor
            )
            spacing = float(looping.get("spacing_px", 0.0)) * oversample
            extent = (
                transformed.width if axis == "x" else transformed.height
            ) + spacing
            canvas_extent = render_canvas[0] if axis == "x" else render_canvas[1]
            copies = max(2, math.ceil(canvas_extent / max(1.0, extent)) + 2)
            phase_position = (
                position[0] if axis == "x" else position[1]
            )
            wrapped = phase_position % max(1.0, extent)
            for copy_index in range(-1, copies):
                offset = round(wrapped + copy_index * extent)
                copy_position = (
                    (offset, position[1])
                    if axis == "x"
                    else (position[0], offset)
                )
                frame.alpha_composite(transformed, copy_position)
        else:
            transformed, position = apply_transform(
                source, values, oversample, pivot, anchor
            )
            frame.alpha_composite(transformed, position)
    if oversample > 1:
        frame = frame.resize(canvas, Image.Resampling.LANCZOS)
    return frame


def render_motion_blur_frame(
    manifest_path: Path,
    frame_index: int,
    fps: int,
    loaded: list[tuple[dict[str, Any], dict[str, Image.Image]]],
    manifest: dict[str, Any],
) -> Image.Image:
    canvas = manifest["canvas"]
    samples = int(canvas.get("motion_blur_samples", 1))
    if samples <= 1:
        return render_frame(manifest_path, frame_index / fps, loaded, manifest)
    shutter = float(canvas.get("shutter", 0.5))
    rendered: list[Image.Image] = []
    for sample in range(samples):
        position = (sample + 0.5) / samples - 0.5
        time_s = max(0.0, (frame_index + position * shutter) / fps)
        rendered.append(render_frame(manifest_path, time_s, loaded, manifest))
    result = rendered[0]
    for index, sample in enumerate(rendered[1:], 2):
        result = Image.blend(result, sample, 1.0 / index)
    return result


def render_manifest(manifest_path: Path, output: Path) -> Path:
    errors, warnings, stats = validate_manifest(manifest_path)
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        raise LayerError("invalid layer manifest:\n- " + "\n- ".join(errors))
    if not shutil.which("ffmpeg"):
        raise LayerError("ffmpeg is required")
    manifest = load_manifest(manifest_path)
    canvas = manifest["canvas"]
    width, height = int(canvas["width"]), int(canvas["height"])
    fps = int(canvas["fps"])
    duration = float(canvas["duration_s"])
    frame_count = max(1, round(duration * fps))
    loaded = load_layer_sources(manifest_path, manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{width}x{height}",
        "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264", "-preset", "medium",
        "-crf", "18", "-pix_fmt", "yuv420p", str(output),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame_index in range(frame_count):
            process.stdin.write(
                render_motion_blur_frame(
                    manifest_path, frame_index, fps, loaded, manifest
                ).tobytes()
            )
        process.stdin.close()
        return_code = process.wait()
    except Exception:
        process.kill()
        raise
    if return_code:
        raise LayerError(f"ffmpeg failed with exit code {return_code}")
    if not output.is_file() or output.stat().st_size <= 0:
        raise LayerError("layer render produced no output")
    print(
        f"layer render: {output} · {stats['layers']} layers · "
        f"{stats['animated_layers']} animated · {duration:.2f}s"
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--output")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument(
        "--audit",
        action="store_true",
        help="sample resolved transforms and fail on jumps or contact drift",
    )
    args = parser.parse_args()
    manifest = Path(args.manifest).resolve()
    try:
        errors, warnings, stats = validate_manifest(manifest)
        for warning in warnings:
            print(f"WARNING: {warning}")
        for error in errors:
            print(f"ERROR: {error}")
        print(f"layers={stats['layers']} animated={stats['animated_layers']}")
        if args.audit and not errors:
            audit = audit_motion_continuity(load_manifest(manifest))
            print(json.dumps(audit, ensure_ascii=False, indent=2))
            if audit["issues"]:
                return 1
        if errors or args.validate or args.audit:
            return 1 if errors else 0
        output = Path(args.output) if args.output else manifest.with_suffix(".mp4")
        render_manifest(manifest, output.resolve())
        return 0
    except (LayerError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
