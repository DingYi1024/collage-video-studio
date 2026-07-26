#!/usr/bin/env python3
"""Inspect narration assets for long internal, leading, trailing, or cross-clip silence."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULTS = {
    "silence_threshold_db": -42.0,
    "min_detect_s": 0.12,
    "max_phrase_gap_s": 0.35,
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
        elif key == "max_silence_ratio":
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
        "silence_ratio": silent_total / max(1e-6, timeline_duration),
        "audible_start_s": min(timeline_duration, leading),
        "audible_end_s": max(0.0, timeline_duration - trailing),
    }


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
    return {"issues": issues, "config": config, "entries": analyses}


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
