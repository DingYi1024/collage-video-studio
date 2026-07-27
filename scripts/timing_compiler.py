#!/usr/bin/env python3
"""Compile measured narration timing into exact beat and shot frame counts."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import narration
import studio


class TimingCompileError(RuntimeError):
    pass


def _digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _positive_float(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise TimingCompileError(f"{label} must be numeric") from exc
    if result <= 0:
        raise TimingCompileError(f"{label} must be positive")
    return result


def _largest_remainder(total: int, weights: list[float]) -> list[int]:
    if total < len(weights):
        raise TimingCompileError(
            f"{total} frames cannot be divided across {len(weights)} shots"
        )
    clean = [max(0.000001, float(weight)) for weight in weights]
    remaining = total - len(clean)
    scale = sum(clean)
    raw = [remaining * weight / scale for weight in clean]
    result = [1 + math.floor(value) for value in raw]
    left = total - sum(result)
    order = sorted(
        range(len(raw)), key=lambda index: (raw[index] - math.floor(raw[index]), -index),
        reverse=True,
    )
    for index in order[:left]:
        result[index] += 1
    return result


def _load_timing(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TimingCompileError(f"cannot read timing manifest {path}: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("segments"), list):
        raise TimingCompileError(f"{path}: timing manifest requires segments[]")
    return value


def _segment_end(segment: dict[str, Any]) -> float:
    candidates = [
        segment.get("pause_end_s"),
        segment.get("speech_end_s"),
        float(segment.get("start_s", 0)) + float(segment.get("speech_duration_s", 0)),
    ]
    valid = [float(value) for value in candidates if value is not None]
    return max(valid, default=0.0)


def _continuous_spans(
    beats: list[dict[str, Any]],
    timing: dict[str, Any],
    language: str,
) -> list[dict[str, Any]]:
    segments = timing["segments"]
    if not segments:
        raise TimingCompileError("continuous timing manifest has no segments")
    result: list[dict[str, Any]] = []
    cursor = 0
    for beat_index, beat in enumerate(beats):
        beat_id = str(beat.get("id") or f"beat-{beat_index + 1:02d}")
        target_units = max(1, narration.text_units(str(beat.get("narration", "")), language))
        start_cursor = cursor
        accumulated = 0
        while cursor < len(segments):
            segment = segments[cursor]
            accumulated += max(
                1,
                int(
                    segment.get("units")
                    or narration.text_units(str(segment.get("text", "")), language)
                ),
            )
            cursor += 1
            if accumulated >= target_units:
                break
        if cursor <= start_cursor:
            raise TimingCompileError(f"{beat_id}: no measured narration segment assigned")
        first = segments[start_cursor]
        last = segments[cursor - 1]
        start_s = float(first.get("start_s", 0))
        end_s = _segment_end(last)
        if end_s <= start_s:
            raise TimingCompileError(f"{beat_id}: invalid measured narration span")
        result.append({
            "beat_id": beat_id,
            "start_s": start_s,
            "end_s": end_s,
            "duration_s": end_s - start_s,
            "segment_start": start_cursor,
            "segment_end": cursor - 1,
        })
    if cursor < len(segments):
        result[-1]["end_s"] = _segment_end(segments[-1])
        result[-1]["duration_s"] = result[-1]["end_s"] - result[-1]["start_s"]
        result[-1]["segment_end"] = len(segments) - 1
    return result


def _segmented_spans(
    root: Path,
    beats: list[dict[str, Any]],
    timing_paths: dict[str, Path],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    cursor_s = 0.0
    for beat_index, beat in enumerate(beats):
        beat_id = str(beat.get("id") or f"beat-{beat_index + 1:02d}")
        path = timing_paths.get(beat_id)
        if path is None:
            raise TimingCompileError(f"missing timing manifest for voice:{beat_id}")
        timing = _load_timing(path)
        duration_s = float(timing.get("timeline_duration_s") or 0)
        if duration_s <= 0:
            duration_s = max((_segment_end(item) for item in timing["segments"]), default=0)
        duration_s = _positive_float(duration_s, f"voice:{beat_id} duration")
        result.append({
            "beat_id": beat_id,
            "start_s": cursor_s,
            "end_s": cursor_s + duration_s,
            "duration_s": duration_s,
            "timing_path": studio.portable_path(root, path),
        })
        cursor_s += duration_s
    return result


def timing_paths_from_state(root: Path) -> dict[str, Path]:
    state = studio.load_state(root)
    result: dict[str, Path] = {}
    for artifact_id, record in state.get("artifacts", {}).items():
        if not artifact_id.startswith("voice:") or not isinstance(record, dict):
            continue
        raw = record.get("metadata", {}).get("timing_path")
        if raw:
            path = studio.resolve_path(root, raw).resolve()
        else:
            path = studio.resolve_path(root, record["path"]).resolve().with_suffix(
                ".timing.json"
            )
        if path.is_file():
            result[artifact_id.split(":", 1)[1]] = path
    return result


def compile_project(
    project: dict[str, Any],
    timing_paths: dict[str, Path],
    root: Path,
    *,
    tail_s: float | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    compiled = copy.deepcopy(project)
    beats = compiled.get("beats")
    if not isinstance(beats, list) or not beats:
        raise TimingCompileError("project requires beats[]")
    fps = int(compiled.get("project", {}).get("fps", 30))
    if fps <= 0:
        raise TimingCompileError("project.fps must be positive")
    language = str(compiled.get("project", {}).get("language", "zh"))
    voice = compiled.get("audio", {}).get("voice", {})
    continuity = str(voice.get("continuity_mode", "segmented"))
    resolved_tail = float(
        tail_s if tail_s is not None else voice.get("visual_tail_s", 0.12)
    )
    if resolved_tail < 0 or resolved_tail > 2:
        raise TimingCompileError("visual_tail_s must be from 0 to 2 seconds")
    if continuity == "continuous":
        path = timing_paths.get("main")
        if path is None:
            raise TimingCompileError("missing timing manifest for voice:main")
        timing = _load_timing(path)
        spans = _continuous_spans(beats, timing, language)
        timing_sources = {"main": studio.portable_path(root, path)}
    elif continuity == "segmented":
        spans = _segmented_spans(root, beats, timing_paths)
        timing_sources = {
            key: studio.portable_path(root, value)
            for key, value in timing_paths.items()
            if key in {str(beat.get("id")) for beat in beats}
        }
    else:
        raise TimingCompileError(
            "audio.voice.continuity_mode must be continuous or segmented"
        )

    cursor_frames = 0
    compiled_spans: list[dict[str, Any]] = []
    for beat, span in zip(beats, spans, strict=True):
        measured_s = float(span["duration_s"])
        beat_frames = max(1, round((measured_s + resolved_tail) * fps))
        shots = beat.get("shots")
        if not isinstance(shots, list) or not shots:
            raise TimingCompileError(f"{span['beat_id']}: requires shots[]")
        shot_weights = [
            _positive_float(
                shot.get("duration_frames", 0) / fps
                if shot.get("duration_frames")
                else shot.get("duration_s", 1),
                f"{span['beat_id']} shot duration",
            )
            for shot in shots
        ]
        shot_frames = _largest_remainder(beat_frames, shot_weights)
        for shot, frames in zip(shots, shot_frames, strict=True):
            shot["duration_frames"] = frames
            shot["duration_s"] = frames / fps
        beat["duration_frames"] = beat_frames
        beat["duration_s"] = beat_frames / fps
        beat["start_frame"] = cursor_frames
        beat["end_frame"] = cursor_frames + beat_frames
        compiled_spans.append({
            **span,
            "measured_duration_s": measured_s,
            "visual_tail_s": resolved_tail,
            "start_frame": cursor_frames,
            "end_frame": cursor_frames + beat_frames,
            "duration_frames": beat_frames,
            "shot_frames": shot_frames,
        })
        cursor_frames += beat_frames

    compiled["project"]["duration_frames"] = cursor_frames
    compiled["project"]["duration_s"] = cursor_frames / fps
    evidence = {
        "schema_version": 1,
        "mode": continuity,
        "fps": fps,
        "duration_frames": cursor_frames,
        "duration_s": cursor_frames / fps,
        "timing_sources": timing_sources,
        "beat_spans": compiled_spans,
    }
    evidence["fingerprint"] = _digest(evidence)
    compiled["compiled_timing"] = evidence
    return compiled, evidence


def compile_project_dir(
    root: Path,
    *,
    output: Path | None = None,
    apply: bool = False,
    tail_s: float | None = None,
) -> tuple[Path, dict[str, Any]]:
    root = root.resolve()
    project_path = root / "project.json"
    project = studio.load_json(project_path)
    compiled, evidence = compile_project(
        project, timing_paths_from_state(root), root, tail_s=tail_s
    )
    target = project_path if apply else (output or root / "build" / "project.timed.json")
    studio.atomic_json(target, compiled)
    studio.atomic_json(root / "build" / "timing-proof.json", evidence)
    if apply:
        state = studio.load_state(root)
        state["approvals"] = {}
        state["timing_compilation"] = evidence
        state["updated_at"] = studio.now_iso()
        studio.atomic_json(studio.state_file(root), state)
    return target, evidence


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rewrite beat and shot durations from measured narration timing."
    )
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--tail", type=float)
    args = parser.parse_args()
    path, evidence = compile_project_dir(
        args.project_dir,
        output=args.output.resolve() if args.output else None,
        apply=args.apply,
        tail_s=args.tail,
    )
    print(
        f"wrote {path} ({evidence['duration_frames']} frames, "
        f"{evidence['duration_s']:.3f}s, {evidence['mode']})"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TimingCompileError, studio.StudioError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
