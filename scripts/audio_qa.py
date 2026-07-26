#!/usr/bin/env python3
"""Inspect narration assets for long internal, leading, trailing, or cross-clip silence."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULTS = {
    "silence_threshold_db": -42.0,
    "min_detect_s": 0.12,
    "min_sentence_pause_s": 0.16,
    "max_phrase_gap_s": 0.50,
    "max_unbroken_s": 5.50,
    "min_boundary_coverage": 0.75,
    "max_leading_s": 0.25,
    "max_trailing_s": 0.60,
    "max_silence_ratio": 0.25,
}


class AudioQaError(RuntimeError):
    pass


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(command, text=True, capture_output=True, check=False)
    if proc.returncode:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise AudioQaError(detail or f"command failed: {' '.join(command)}")
    return proc


def media_duration(path: Path) -> float:
    proc = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    try:
        return float(proc.stdout.strip())
    except ValueError as exc:
        raise AudioQaError(f"ffprobe returned an invalid duration for {path}") from exc


def config_with_defaults(raw: dict[str, Any] | None = None) -> dict[str, float]:
    config = dict(DEFAULTS)
    for key, default in DEFAULTS.items():
        if raw is None or key not in raw:
            continue
        try:
            value = float(raw[key])
        except (TypeError, ValueError) as exc:
            raise AudioQaError(f"audio.voice.qa.{key} must be numeric") from exc
        if key == "silence_threshold_db":
            if value >= 0:
                raise AudioQaError(f"audio.voice.qa.{key} must be negative")
        elif key in {"max_silence_ratio", "min_boundary_coverage"}:
            if value < 0 or value > 1:
                raise AudioQaError(f"audio.voice.qa.{key} must be from 0 to 1")
        elif value < 0:
            raise AudioQaError(f"audio.voice.qa.{key} cannot be negative")
        config[key] = value
    return config


def silence_intervals(
    path: Path,
    duration_s: float,
    threshold_db: float,
    minimum_s: float,
) -> list[dict[str, float]]:
    proc = run([
        "ffmpeg", "-hide_banner", "-i", str(path),
        "-af", f"silencedetect=noise={threshold_db:g}dB:d={minimum_s:.3f}",
        "-vn", "-f", "null", "-",
    ])
    events = re.finditer(
        r"silence_(start|end):\s*([0-9.]+)"
        r"(?:\s*\|\s*silence_duration:\s*([0-9.]+))?",
        proc.stderr,
    )
    intervals: list[dict[str, float]] = []
    start: float | None = None
    for event in events:
        kind = event.group(1)
        value = float(event.group(2))
        if kind == "start":
            start = value
            continue
        if start is None:
            start = 0.0
        end = min(duration_s, value)
        measured = float(event.group(3)) if event.group(3) else end - start
        intervals.append({
            "start_s": max(0.0, start),
            "end_s": end,
            "duration_s": max(0.0, measured),
        })
        start = None
    if start is not None and start < duration_s:
        intervals.append({
            "start_s": max(0.0, start),
            "end_s": duration_s,
            "duration_s": max(0.0, duration_s - start),
        })
    return intervals


def inspect_voice(
    path: Path,
    timeline_duration_s: float | None = None,
    raw_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise AudioQaError(f"missing or empty narration asset: {path}")
    config = config_with_defaults(raw_config)
    source_duration = media_duration(path)
    intended = (
        source_duration
        if timeline_duration_s is None
        else max(0.0, min(source_duration, float(timeline_duration_s)))
    )
    intervals = silence_intervals(
        path,
        intended,
        config["silence_threshold_db"],
        config["min_detect_s"],
    )
    leading = 0.0
    trailing = max(0.0, (timeline_duration_s or intended) - source_duration)
    internal: list[dict[str, float]] = []
    for interval in intervals:
        if interval["start_s"] <= 0.02:
            leading = max(leading, interval["end_s"])
        elif interval["end_s"] >= intended - 0.02:
            trailing += interval["duration_s"]
        else:
            internal.append(interval)
    timeline_duration = float(timeline_duration_s or source_duration)
    silent_total = min(
        timeline_duration,
        leading + trailing + sum(item["duration_s"] for item in internal),
    )
    return {
        "path": str(path),
        "source_duration_s": source_duration,
        "timeline_duration_s": timeline_duration,
        "leading_s": leading,
        "trailing_s": trailing,
        "internal_silences": internal,
        "prosodic_pauses": [
            item for item in internal
            if item["duration_s"] >= config["min_sentence_pause_s"]
        ],
        "silence_ratio": silent_total / max(1e-6, timeline_duration),
        "audible_start_s": min(timeline_duration, leading),
        "audible_end_s": max(0.0, timeline_duration - trailing),
    }


def sentence_boundary_count(text: str) -> int:
    return len(re.findall(
        r"(?:[。！？!?；;]+|(?<!\d)\.(?!\d))(?:[ \t]*\n+[ \t]*)?|\n+",
        text,
    ))


def merge_intervals(
    intervals: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1] + 1e-6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def inspect_timing_manifest(
    path: Path,
    source_duration_s: float,
) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AudioQaError(f"missing narration timing manifest: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise AudioQaError(f"invalid narration timing manifest {path}: {exc}") from exc
    segments = value.get("segments")
    if value.get("schema_version") != 1 or not isinstance(segments, list) or not segments:
        raise AudioQaError(f"invalid narration timing manifest contract: {path}")
    cursor = 0.0
    for index, segment in enumerate(segments, 1):
        try:
            start = float(segment["start_s"])
            speech_end = float(segment["speech_end_s"])
            pause_start = float(segment["pause_start_s"])
            pause_end = float(segment["pause_end_s"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AudioQaError(
                f"{path}: segment {index} has invalid timing fields"
            ) from exc
        if (
            start < cursor - 0.03
            or speech_end < start
            or pause_start < speech_end - 0.03
            or pause_end < pause_start
            or pause_end > source_duration_s + 0.08
        ):
            raise AudioQaError(f"{path}: segment {index} timing is not monotonic")
        cursor = pause_end
    return value


def audit_timeline(
    entries: list[dict[str, Any]],
    raw_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = config_with_defaults(raw_config)
    analyses: list[dict[str, Any]] = []
    issues: list[str] = []
    for entry in sorted(entries, key=lambda item: float(item["timeline_start_s"])):
        label = str(entry.get("label", Path(entry["path"]).stem))
        analysis = inspect_voice(
            Path(entry["path"]),
            float(entry["timeline_duration_s"]),
            config,
        )
        analysis["label"] = label
        analysis["timeline_start_s"] = float(entry["timeline_start_s"])
        analysis["text"] = str(entry.get("text", ""))
        timing_path = entry.get("timing_path")
        if timing_path:
            timing = inspect_timing_manifest(
                Path(timing_path),
                float(analysis["source_duration_s"]),
            )
            analysis["timing_manifest"] = str(timing_path)
            analysis["timing_segments"] = timing["segments"]
        analyses.append(analysis)
        for silence in analysis["internal_silences"]:
            if silence["duration_s"] > config["max_phrase_gap_s"] + 1e-6:
                issues.append(
                    f"{label}: internal narration gap {silence['duration_s']:.2f}s "
                    f"at {silence['start_s']:.2f}s exceeds "
                    f"{config['max_phrase_gap_s']:.2f}s"
                )
        if analysis["silence_ratio"] > config["max_silence_ratio"] + 1e-6:
            issues.append(
                f"{label}: narration silence ratio {analysis['silence_ratio']:.0%} "
                f"exceeds {config['max_silence_ratio']:.0%}"
            )

    if analyses:
        if analyses[0]["leading_s"] > config["max_leading_s"] + 1e-6:
            issues.append(
                f"{analyses[0]['label']}: leading narration silence "
                f"{analyses[0]['leading_s']:.2f}s exceeds "
                f"{config['max_leading_s']:.2f}s"
            )
        for previous, current in zip(analyses, analyses[1:]):
            previous_end = (
                previous["timeline_start_s"] + previous["audible_end_s"]
            )
            current_start = (
                current["timeline_start_s"] + current["audible_start_s"]
            )
            gap = current_start - previous_end
            if gap > config["max_phrase_gap_s"] + 1e-6:
                issues.append(
                    f"{previous['label']} -> {current['label']}: narration gap "
                    f"{gap:.2f}s exceeds {config['max_phrase_gap_s']:.2f}s"
                )
        if analyses[-1]["trailing_s"] > config["max_trailing_s"] + 1e-6:
            issues.append(
                f"{analyses[-1]['label']}: trailing narration silence "
                f"{analyses[-1]['trailing_s']:.2f}s exceeds "
                f"{config['max_trailing_s']:.2f}s"
            )
        manifests_present = all(item.get("timing_segments") for item in analyses)
        if manifests_present:
            expected_boundaries = sum(
                1
                for item in analyses
                for segment in item["timing_segments"]
                if segment.get("boundary") in {
                    "sentence", "beat", "clause", "safety"
                }
                and float(segment.get("pause_after_s", 0))
                >= config["min_sentence_pause_s"] - 1e-6
            )
        else:
            expected_boundaries = sum(
                max(0, sentence_boundary_count(item["text"]) - 1)
                for item in analyses
            ) + max(0, len(analyses) - 1)
        required_pauses = math.ceil(
            expected_boundaries * config["min_boundary_coverage"]
        )
        pause_intervals: list[tuple[float, float]] = []
        for item in analyses:
            offset = item["timeline_start_s"]
            pause_intervals.extend(
                (
                    offset + float(pause["start_s"]),
                    offset + float(pause["end_s"]),
                )
                for pause in item["prosodic_pauses"]
            )
        for previous, current in zip(analyses, analyses[1:]):
            previous_end = (
                previous["timeline_start_s"] + previous["audible_end_s"]
            )
            current_start = (
                current["timeline_start_s"] + current["audible_start_s"]
            )
            if (
                current_start - previous_end
                >= config["min_sentence_pause_s"] - 1e-6
            ):
                pause_intervals.append((previous_end, current_start))
        pauses = merge_intervals(pause_intervals)
        if manifests_present:
            expected_windows: list[tuple[float, float]] = []
            for item in analyses:
                offset = float(item["timeline_start_s"])
                for segment in item["timing_segments"]:
                    start = offset + float(segment.get("pause_start_s", 0))
                    end = offset + float(segment.get("pause_end_s", start))
                    if end - start >= config["min_sentence_pause_s"] - 1e-6:
                        expected_windows.append((start, end))
            localized = sum(
                any(
                    pause_end >= expected_start - 0.08
                    and pause_start <= expected_end + 0.08
                    for pause_start, pause_end in pauses
                )
                for expected_start, expected_end in expected_windows
            )
            localized_required = math.ceil(
                len(expected_windows) * config["min_boundary_coverage"]
            )
            if localized < localized_required:
                issues.append(
                    f"only {localized}/{len(expected_windows)} planned semantic "
                    "pause(s) were measured at their intended boundaries"
                )
        if len(pauses) < required_pauses:
            issues.append(
                f"narration has {len(pauses)} full breathing pause(s), but "
                f"{required_pauses} are required for {expected_boundaries} "
                "semantic boundary/boundaries"
            )
        audible_start = (
            analyses[0]["timeline_start_s"] + analyses[0]["audible_start_s"]
        )
        audible_end = (
            analyses[-1]["timeline_start_s"] + analyses[-1]["audible_end_s"]
        )
        cursor = audible_start
        unbroken_runs: list[tuple[float, float]] = []
        for pause_start, pause_end in pauses:
            if pause_start > cursor:
                unbroken_runs.append((cursor, pause_start))
            cursor = max(cursor, pause_end)
        if audible_end > cursor:
            unbroken_runs.append((cursor, audible_end))
        longest_run = max(
            (end - start for start, end in unbroken_runs),
            default=0.0,
        )
        if longest_run > config["max_unbroken_s"] + 1e-6:
            issues.append(
                f"longest unbroken narration run {longest_run:.2f}s exceeds "
                f"{config['max_unbroken_s']:.2f}s"
            )
    else:
        expected_boundaries = 0
        required_pauses = 0
        pauses = []
        longest_run = 0.0
    return {
        "issues": issues,
        "config": config,
        "entries": analyses,
        "prosody": {
            "expected_boundaries": expected_boundaries,
            "required_pauses": required_pauses,
            "observed_pauses": len(pauses),
            "timing_manifests": sum(
                bool(item.get("timing_manifest")) for item in analyses
            ),
            "pause_intervals": [
                {"start_s": start, "end_s": end, "duration_s": end - start}
                for start, end in pauses
            ],
            "longest_unbroken_s": longest_run,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--timeline-duration", type=float)
    args = parser.parse_args()
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("ERROR: ffmpeg and ffprobe are required", file=sys.stderr)
        return 2
    try:
        report = audit_timeline([{
            "path": args.audio.resolve(),
            "label": args.audio.stem,
            "timeline_start_s": 0,
            "timeline_duration_s": (
                args.timeline_duration
                if args.timeline_duration is not None
                else media_duration(args.audio.resolve())
            ),
        }])
    except (AudioQaError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
