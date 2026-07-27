#!/usr/bin/env python3
"""Run technical acceptance checks and extract visual-review frames."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import studio
import layer_compositor
import audio_qa
import production_contract


CANVAS = {
    "16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080),
    "4:5": (1080, 1350), "3:4": (1080, 1440), "4:3": (1440, 1080),
}


class QaError(RuntimeError):
    pass


def probe(path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode:
        raise QaError(proc.stderr.strip() or f"ffprobe failed for {path}")
    return json.loads(proc.stdout)


def add(checks: list[dict[str, str]], level: str, name: str, message: str) -> None:
    checks.append({"level": level, "name": name, "message": message})


def frame_rate(value: Any) -> float:
    text = str(value or "0").strip()
    try:
        if "/" in text:
            numerator, denominator = text.split("/", 1)
            return float(numerator) / max(1e-9, float(denominator))
        return float(text)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def delivery_level_config(raw: dict[str, Any] | None) -> dict[str, float]:
    defaults = {
        "min_lufs": -22.0,
        "max_lufs": -11.0,
        "max_true_peak_db": -0.5,
    }
    source = raw or {}
    config: dict[str, float] = {}
    for key, default in defaults.items():
        try:
            value = float(source.get(key, default))
        except (TypeError, ValueError) as exc:
            raise QaError(f"audio.delivery_qa.{key} must be numeric") from exc
        if value >= 0:
            raise QaError(f"audio.delivery_qa.{key} must be negative")
        config[key] = value
    if config["min_lufs"] >= config["max_lufs"]:
        raise QaError("audio.delivery_qa.min_lufs must be lower than max_lufs")
    return config


def extract_frames(final: Path, target: Path, duration: float, count: int) -> list[str]:
    if count <= 0 or duration <= 0:
        return []
    target.mkdir(parents=True, exist_ok=True)
    fractions = [0.05 + (0.90 * i / max(1, count - 1)) for i in range(count)]
    paths = []
    for index, fraction in enumerate(fractions, 1):
        timestamp = min(max(0.0, duration * fraction), max(0.0, duration - 0.05))
        output = target / f"frame-{index:02d}-{timestamp:.2f}s.jpg"
        proc = subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{timestamp:.3f}",
             "-i", str(final), "-frames:v", "1", "-vf", "scale=720:-2", str(output)],
            capture_output=True, text=True, check=False,
        )
        if proc.returncode:
            raise QaError(proc.stderr.strip() or f"failed to extract frame at {timestamp:.2f}s")
        paths.append(output.name)
    return paths


def detect_freezes(final: Path, minimum_s: float = 0.12) -> list[tuple[float, float]]:
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-i", str(final),
            # Directed shots may animate one small paper object while most of the frame
            # remains stable. A very low tolerance catches exact/near-exact frame repeats
            # without classifying selective motion as a whole-frame freeze.
            "-vf", f"freezedetect=n=0.00001:d={minimum_s:.3f}",
            "-an", "-f", "null", "-",
        ],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode:
        raise QaError(proc.stderr.strip() or "freeze detection failed")
    starts = [
        float(value)
        for value in re.findall(r"freeze_start:\s*([0-9.]+)", proc.stderr)
    ]
    durations = [
        float(value)
        for value in re.findall(r"freeze_duration:\s*([0-9.]+)", proc.stderr)
    ]
    freezes = list(zip(starts, durations))
    if len(starts) > len(durations):
        try:
            total = float(probe(final).get("format", {}).get("duration", 0))
        except (TypeError, ValueError):
            total = 0.0
        freezes.extend(
            (start, max(0.0, total - start))
            for start in starts[len(durations):]
            if total - start >= minimum_s - 1e-6
        )
    return freezes


def audit_motion_activity(
    final: Path,
    profile: str,
    *,
    sample_fps: int = 10,
    width: int = 160,
    height: int = 90,
) -> dict[str, Any]:
    """Measure low-motion cadence independently of exact-frame freeze checks."""
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(final),
            "-an", "-vf", f"fps={sample_fps},scale={width}:{height},format=gray",
            "-f", "rawvideo", "-pix_fmt", "gray", "-",
        ],
        capture_output=True,
        check=False,
    )
    if proc.returncode:
        raise QaError(proc.stderr.decode("utf-8", "replace").strip()
                      or "motion activity sampling failed")
    frame_size = width * height
    frames = [
        proc.stdout[offset:offset + frame_size]
        for offset in range(0, len(proc.stdout) - frame_size + 1, frame_size)
    ]
    if len(frames) < 2:
        return {
            "profile": profile,
            "sample_fps": sample_fps,
            "mean_activity": 0.0,
            "low_motion_ratio": 1.0,
            "low_motion_ranges": [],
            "longest_low_motion_s": 0.0,
        }
    activity = [
        sum(abs(left - right) for left, right in zip(previous, current))
        / (frame_size * 255.0)
        for previous, current in zip(frames, frames[1:])
    ]
    # At this scale, 0.0012 distinguishes a living paper frame from tiny
    # compression shimmer while preserving the separate exact-freeze detector.
    threshold = 0.0012
    low = [value < threshold for value in activity]
    ranges: list[tuple[float, float]] = []
    start: int | None = None
    for index, is_low in enumerate(low + [False]):
        if is_low and start is None:
            start = index
        elif not is_low and start is not None:
            duration = (index - start) / sample_fps
            if duration >= 0.30:
                ranges.append((start / sample_fps, duration))
            start = None
    return {
        "profile": profile,
        "sample_fps": sample_fps,
        "threshold": threshold,
        "mean_activity": sum(activity) / len(activity),
        "low_motion_ratio": sum(low) / len(low),
        "low_motion_ranges": [
            {"start_s": start_s, "duration_s": duration_s}
            for start_s, duration_s in ranges
        ],
        "longest_low_motion_s": max(
            (duration for _, duration in ranges),
            default=0.0,
        ),
    }


def designed_hold_ranges(
    root: Path,
    project: dict[str, Any],
    artifacts: dict[str, Any],
) -> list[tuple[float, float, str]]:
    ranges: list[tuple[float, float, str]] = []
    offset = 0.0
    for beat, shot in studio.iter_shots(project):
        for hold in shot.get("designed_holds", []):
            try:
                ranges.append((
                    offset + float(hold["start_s"]),
                    offset + float(hold["end_s"]),
                    str(hold.get("reason", "designed hold")),
                ))
            except (KeyError, TypeError, ValueError):
                continue
        key = studio.artifact_key("layers", beat, shot)
        record = artifacts.get(key, {})
        manifest_path = studio.resolve_path(root, record.get("path", ""))
        try:
            manifest = layer_compositor.load_manifest(manifest_path)
        except layer_compositor.LayerError:
            offset += float(shot.get("duration_s", 0.0))
            continue
        direction = manifest.get("direction", {})
        for hold in direction.get("designed_holds", []):
            try:
                ranges.append((
                    offset + float(hold["start_s"]),
                    offset + float(hold["end_s"]),
                    str(hold.get("reason", "designed hold")),
                ))
            except (KeyError, TypeError, ValueError):
                continue
        offset += float(shot.get("duration_s", 0.0))
    return ranges


def freeze_is_designed(
    freeze: tuple[float, float],
    holds: list[tuple[float, float, str]],
    tolerance_s: float = 0.08,
) -> bool:
    start, duration = freeze
    end = start + duration
    return any(
        start >= hold_start - tolerance_s and end <= hold_end + tolerance_s
        for hold_start, hold_end, _ in holds
    )


def declares_tail_hold(
    shot: dict[str, Any],
    source_duration: float,
    shot_duration: float,
) -> bool:
    """Return whether a validated shot declares the otherwise frozen tail."""
    for hold in shot.get("designed_holds", []):
        if not isinstance(hold, dict):
            continue
        try:
            start = float(hold.get("start_s"))
            end = float(hold.get("end_s"))
        except (TypeError, ValueError):
            continue
        if (
            abs(end - shot_duration) <= 0.08
            and start <= source_duration + 0.08
        ):
            return True
    return False


def voice_timeline_entries(
    root: Path,
    project: dict[str, Any],
    artifacts: dict[str, Any],
) -> list[dict[str, Any]]:
    voice = project.get("audio", {}).get("voice", {})
    if str(voice.get("continuity_mode", "segmented")) == "continuous":
        record = artifacts.get("voice:main")
        if not record:
            return []
        duration = sum(
            float(shot.get("duration_s", 0))
            for _, shot in studio.iter_shots(project)
        )
        entry = {
            "path": studio.resolve_path(root, record.get("path", "")),
            "label": "voice:main",
            "timeline_start_s": 0.0,
            "timeline_duration_s": duration,
            "text": "\n".join(
                str(beat.get("narration", "")).strip()
                for beat in project.get("beats", [])
                if str(beat.get("narration", "")).strip()
            ),
        }
        timing_path = record.get("metadata", {}).get("timing_path")
        if timing_path:
            entry["timing_path"] = studio.resolve_path(root, timing_path)
        return [entry]
    entries: list[dict[str, Any]] = []
    offset = 0.0
    for beat in project.get("beats", []):
        duration = sum(
            float(shot.get("duration_s", 0))
            for shot in beat.get("shots", [])
        )
        key = studio.artifact_key("voice", beat)
        record = artifacts.get(key)
        if record:
            entry = {
                "path": studio.resolve_path(root, record.get("path", "")),
                "label": key,
                "timeline_start_s": offset,
                "timeline_duration_s": duration,
                "text": str(beat.get("narration", "")).strip(),
            }
            timing_path = record.get("metadata", {}).get("timing_path")
            if timing_path:
                entry["timing_path"] = studio.resolve_path(root, timing_path)
            entries.append(entry)
        offset += duration
    return entries


def run_qa(root: Path, final: Path, frame_count: int = 6) -> dict[str, Any]:
    if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
        raise QaError("ffmpeg and ffprobe are required")
    project = studio.load_project(root)
    state = studio.load_state(root)
    checks: list[dict[str, str]] = []
    motion_audits: list[dict[str, Any]] = []

    errors, warnings = studio.validate_project(root, project, "assemble")
    for message in errors:
        add(checks, "error", "project-readiness", message)
    for message in warnings:
        add(checks, "warning", "project-readiness", message)

    if not final.is_file() or final.stat().st_size <= 0:
        add(checks, "error", "final-file", f"missing or empty: {final}")
        return finish_report(root, project, checks, [], {})
    add(checks, "info", "final-file", f"{final.stat().st_size} bytes")

    media = probe(final)
    fmt = media.get("format", {})
    streams = media.get("streams", [])
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    try:
        actual_duration = float(fmt.get("duration", 0))
    except (TypeError, ValueError):
        actual_duration = 0.0
    expected_duration = sum(
        float(shot.get("duration_s", 0)) for _, shot in studio.iter_shots(project)
    )
    tolerance = max(0.25, expected_duration * 0.02)
    if abs(actual_duration - expected_duration) <= tolerance:
        add(checks, "info", "duration",
            f"{actual_duration:.3f}s; target timeline {expected_duration:.3f}s")
    else:
        add(checks, "error", "duration",
            f"{actual_duration:.3f}s; target timeline {expected_duration:.3f}s")

    if video:
        actual_canvas = (int(video.get("width", 0)), int(video.get("height", 0)))
        expected_canvas = CANVAS[project["project"]["aspect"]]
        level = "info" if actual_canvas == expected_canvas else "error"
        add(checks, level, "canvas", f"{actual_canvas[0]}x{actual_canvas[1]}; expected "
            f"{expected_canvas[0]}x{expected_canvas[1]}")
        pixel_format = video.get("pix_fmt", "")
        add(checks, "info" if pixel_format == "yuv420p" else "warning",
            "pixel-format", pixel_format or "unknown")
        expected_fps = float(project["project"].get("fps", 30))
        average_fps = frame_rate(video.get("avg_frame_rate"))
        nominal_fps = frame_rate(video.get("r_frame_rate"))
        fps_level = (
            "info"
            if abs(average_fps - expected_fps) <= 0.15
            else "error"
        )
        add(
            checks,
            fps_level,
            "delivery-fps",
            f"average {average_fps:.3f} fps; target {expected_fps:.3f} fps",
        )
        cadence_level = (
            "info"
            if abs(average_fps - nominal_fps) <= 0.15
            else "error"
        )
        add(
            checks,
            cadence_level,
            "constant-frame-rate",
            f"average {average_fps:.3f}; nominal {nominal_fps:.3f}",
        )
    else:
        add(checks, "error", "video-stream", "no video stream")
    add(checks, "info" if audio else "error", "audio-stream",
        "present" if audio else "missing")
    final_levels: dict[str, Any] = {}
    if audio:
        level_config = delivery_level_config(
            project.get("audio", {}).get("delivery_qa", {})
        )
        try:
            final_levels = audio_qa.measure_levels(final)
        except audio_qa.AudioQaError as exc:
            final_levels = {"error": str(exc)}
            add(
                checks,
                "error",
                "delivery-audio-levels",
                f"could not measure final audio: {exc}",
            )
        else:
            integrated = final_levels["integrated_lufs"]
            peak = final_levels["true_peak_db"]
            loudness_level = (
                "error"
                if (
                    integrated < level_config["min_lufs"] - 1e-6
                    or integrated > level_config["max_lufs"] + 1e-6
                )
                else "info"
            )
            add(
                checks,
                loudness_level,
                "delivery-loudness",
                f"{integrated:.1f} LUFS; allowed "
                f"{level_config['min_lufs']:.1f} to "
                f"{level_config['max_lufs']:.1f} LUFS",
            )
            add(
                checks,
                (
                    "error"
                    if peak > level_config["max_true_peak_db"] + 1e-6
                    else "info"
                ),
                "delivery-true-peak",
                f"{peak:.1f} dBTP; maximum "
                f"{level_config['max_true_peak_db']:.1f} dBTP",
            )

    artifacts = state.get("artifacts", {})
    empty = []
    for key, record in artifacts.items():
        path = studio.resolve_path(root, record.get("path", ""))
        if not path.is_file() or path.stat().st_size <= 0:
            empty.append(key)
    if empty:
        add(checks, "error", "artifact-files", f"missing/empty: {', '.join(empty)}")
    else:
        add(checks, "info", "artifact-files", f"{len(artifacts)} registered file(s) verified")

    target_fps = float(project.get("project", {}).get("fps", 30))
    conversion = str(project.get("motion", {}).get("frame_conversion", "auto"))
    source_rates: list[float] = []
    short_sources: list[str] = []
    source_fps_errors: list[str] = []
    source_fps_warnings: list[str] = []
    for beat, shot in studio.iter_shots(project):
        key = studio.artifact_key("motion", beat, shot)
        record = artifacts.get(key)
        if not record:
            continue
        path = studio.resolve_path(root, record.get("path", ""))
        if not path.is_file():
            continue
        motion_media = probe(path)
        motion_video = next(
            (
                item
                for item in motion_media.get("streams", [])
                if item.get("codec_type") == "video"
            ),
            None,
        )
        rate = frame_rate((motion_video or {}).get("avg_frame_rate"))
        source_rates.append(rate)
        if rate <= 0:
            source_fps_errors.append(f"{key}=unknown frame rate")
        elif rate < 11.85:
            source_fps_errors.append(
                f"{key}={rate:.2f}fps is below the 12fps source floor"
            )
        elif rate < target_fps - 0.15 and conversion == "duplicate":
            source_fps_errors.append(
                f"{key}={rate:.2f}fps duplicated to {target_fps:.0f}fps"
            )
        elif rate < 23.85 and conversion in {"auto", "interpolate"}:
            source_fps_warnings.append(
                f"{key}={rate:.2f}fps will be motion-interpolated to "
                f"{target_fps:.0f}fps; review artifacts"
            )
        try:
            source_duration = float(
                motion_media.get("format", {}).get("duration", 0)
            )
        except (TypeError, ValueError):
            source_duration = 0.0
        shot_duration = float(shot.get("duration_s", 0))
        if source_duration < shot_duration - 0.12:
            if not declares_tail_hold(shot, source_duration, shot_duration):
                short_sources.append(
                    f"{key}={source_duration:.2f}s for {shot_duration:.2f}s shot"
                )
    if source_fps_errors:
        add(
            checks,
            "error",
            "motion-source-fps",
            "; ".join(source_fps_errors),
        )
    elif source_rates:
        add(
            checks,
            "info",
            "motion-source-fps",
            f"{len(source_rates)} clip(s); minimum {min(source_rates):.2f} fps; "
            f"conversion policy {conversion}",
        )
    if source_fps_warnings:
        add(
            checks,
            "warning",
            "motion-source-interpolation",
            "; ".join(source_fps_warnings),
        )
    if short_sources:
        add(
            checks,
            "error",
            "motion-source-duration",
            "undeclared tail freeze risk: " + "; ".join(short_sources),
        )
    elif source_rates:
        add(
            checks,
            "info",
            "motion-source-duration",
            "all motion clips cover their shot or declare a tail hold",
        )

    source = project.get("source", {})
    preserve_audio = (
        project.get("project", {}).get("mode") == "footage"
        and bool(source.get("preserve_original_audio"))
    )
    voice_audit: dict[str, Any] = {"issues": [], "entries": []}
    if preserve_audio:
        add(
            checks,
            "info",
            "narration-continuity",
            "source audio preserved; inspect speech pauses during human review",
        )
    else:
        voice_entries = voice_timeline_entries(root, project, artifacts)
        if not voice_entries:
            add(
                checks,
                "error",
                "narration-continuity",
                "no registered pure-voice artifact available for silence audit",
            )
        else:
            try:
                missing_timing = [
                    str(entry["label"])
                    for entry in voice_entries
                    if not entry.get("timing_path")
                ]
                if missing_timing:
                    add(
                        checks,
                        "warning",
                        "narration-timing",
                        "phrase timing unavailable; beat-caption fallback for "
                        + ", ".join(missing_timing),
                    )
                voice_audit = audio_qa.audit_timeline(
                    voice_entries,
                    project.get("audio", {}).get("voice", {}).get("qa", {}),
                )
                if voice_audit["issues"]:
                    add(
                        checks,
                        "error",
                        "narration-continuity",
                        "; ".join(voice_audit["issues"]),
                    )
                else:
                    largest_gap = max(
                        (
                            float(silence["duration_s"])
                            for entry in voice_audit["entries"]
                            for silence in entry["internal_silences"]
                        ),
                        default=0.0,
                    )
                    add(
                        checks,
                        "info",
                        "narration-continuity",
                        f"{len(voice_audit['entries'])} pure-voice asset(s); "
                        f"largest internal gap {largest_gap:.2f}s; "
                        f"{voice_audit['prosody']['observed_pauses']}/"
                        f"{voice_audit['prosody']['required_pauses']} full "
                        "breathing pauses; "
                        f"longest unbroken run "
                        f"{voice_audit['prosody']['longest_unbroken_s']:.2f}s; "
                        f"{voice_audit['prosody']['timing_manifests']} timing "
                        "manifest(s); "
                        "pause minimums and maximums pass",
                    )
            except audio_qa.AudioQaError as exc:
                add(checks, "error", "narration-continuity", str(exc))

    if project.get("motion", {}).get("pipeline") == "layered":
        total_layers = 0
        total_animated = 0
        packs = 0
        layer_errors: list[str] = []
        continuity_issues: list[str] = []
        for beat, shot in studio.iter_shots(project):
            key = studio.artifact_key("layers", beat, shot)
            record = artifacts.get(key, {})
            manifest_path = studio.resolve_path(root, record.get("path", ""))
            errors, layer_warnings, stats = layer_compositor.validate_manifest(manifest_path)
            layer_errors.extend(f"{key}: {item}" for item in errors)
            for message in layer_warnings:
                add(checks, "warning", "layered-motion", f"{key}: {message}")
            if not errors:
                manifest = layer_compositor.load_manifest(manifest_path)
                audit = layer_compositor.audit_motion_continuity(manifest)
                audit["package"] = key
                motion_audits.append(audit)
                continuity_issues.extend(
                    f"{key}: {message}" for message in audit["issues"]
                )
            packs += 1
            total_layers += stats["layers"]
            total_animated += stats["animated_layers"]
        if layer_errors:
            add(checks, "error", "layered-motion", "; ".join(layer_errors))
        else:
            add(
                checks, "info", "layered-motion",
                f"{packs} package(s), {total_layers} layers, "
                f"{total_animated} independently animated layers",
            )
        if continuity_issues:
            add(
                checks,
                "error",
                "motion-continuity",
                "; ".join(continuity_issues),
            )
        else:
            followers = sum(int(item.get("followers", 0)) for item in motion_audits)
            rig_followers = sum(
                int(item.get("rig_followers", 0)) for item in motion_audits
            )
            locomotion_rigs = sum(
                int(item.get("locomotion_rigs", 0)) for item in motion_audits
            )
            plant_intervals = sum(
                int(item.get("plant_intervals", 0)) for item in motion_audits
            )
            interior_stalls = sum(
                len(item.get("interior_stalls", [])) for item in motion_audits
            )
            fastest = max(
                (
                    float(item.get("maxima", {}).get("speed_px_s", {}).get("value", 0))
                    for item in motion_audits
                ),
                default=0.0,
            )
            add(
                checks,
                "info",
                "motion-continuity",
                f"{len(motion_audits)} package(s) sampled; "
                f"{followers} follower layer(s), {rig_followers} rig joint(s); "
                f"{locomotion_rigs} walk rig(s), {plant_intervals} plant interval(s); "
                f"{interior_stalls} continuous-keyframe stall(s); "
                f"peak speed {fastest:.1f}px/s; "
                "no transform jump, unintended keyframe stop, or contact drift",
            )
    try:
        production = production_contract.profile_config(project)
    except production_contract.ProductionError as exc:
        raise QaError(str(exc)) from exc
    activity_profile = (
        str(production["activity_profile"]) if production else "editorial"
    )
    motion_activity = audit_motion_activity(final, activity_profile)
    activity_limits = {
        "calm": {"warn_run": 3.0, "warn_ratio": 0.75, "error_run": 5.0, "error_ratio": 0.90},
        "editorial": {"warn_run": 1.5, "warn_ratio": 0.55, "error_run": 3.0, "error_ratio": 0.75},
        "kinetic": {"warn_run": 0.9, "warn_ratio": 0.35, "error_run": 2.0, "error_ratio": 0.55},
    }[activity_profile]
    longest_low = float(motion_activity["longest_low_motion_s"])
    low_ratio = float(motion_activity["low_motion_ratio"])
    if (
        longest_low >= activity_limits["error_run"]
        or low_ratio >= activity_limits["error_ratio"]
    ):
        level = "error"
    elif (
        longest_low >= activity_limits["warn_run"]
        or low_ratio >= activity_limits["warn_ratio"]
    ):
        level = "warning"
    else:
        level = "info"
    add(
        checks,
        level,
        "motion-activity",
        f"{activity_profile} profile; mean activity "
        f"{float(motion_activity['mean_activity']):.4f}; "
        f"low-motion ratio {low_ratio:.1%}; "
        f"longest low-motion range {longest_low:.2f}s",
    )

    freezes = detect_freezes(final)
    holds = designed_hold_ranges(root, project, artifacts)
    unexpected = [item for item in freezes if not freeze_is_designed(item, holds)]
    designed = [item for item in freezes if freeze_is_designed(item, holds)]
    if unexpected:
        summary = ", ".join(
            f"{start:.2f}s/{duration:.2f}s" for start, duration in unexpected
        )
        add(checks, "error", "motion-freeze", summary)
    else:
        add(checks, "info", "motion-freeze", "no unintended freeze >= 0.12s")
    if designed:
        summary = ", ".join(
            f"{start:.2f}s/{duration:.2f}s" for start, duration in designed
        )
        add(checks, "info", "designed-hold", summary)

    if project.get("audio", {}).get("watermark", ""):
        add(checks, "info", "watermark", "explicit watermark configured")
    else:
        add(checks, "info", "watermark", "none")

    frame_dir = root / "qa" / "frames"
    frames = extract_frames(final, frame_dir, actual_duration, frame_count)
    details = {
        "final": studio.portable_path(root, final),
        "duration_s": actual_duration,
        "expected_duration_s": expected_duration,
        "frame_dir": studio.portable_path(root, frame_dir),
        "motion_audits": motion_audits,
        "voice_audit": voice_audit,
        "final_audio_levels": final_levels,
        "motion_activity": motion_activity,
        "qa_input_fingerprint": studio.qa_input_fingerprint(
            root, project, studio.load_state(root)
        ),
    }
    return finish_report(root, project, checks, frames, details)


def finish_report(root: Path, project: dict[str, Any], checks: list[dict[str, str]],
                  frames: list[str], details: dict[str, Any]) -> dict[str, Any]:
    errors = sum(item["level"] == "error" for item in checks)
    warnings = sum(item["level"] == "warning" for item in checks)
    report = {
        "generated_at": studio.now_iso(),
        "project_id": project.get("project", {}).get("id"),
        "summary": {"errors": errors, "warnings": warnings, "checks": len(checks)},
        "details": details,
        "checks": checks,
        "frames": frames,
        "human_review": [
            "Opening communicates a hook within three seconds, including without audio.",
            "Approved theme remains consistent across shots.",
            "Faces, product geometry, labels, logos, and display text do not drift.",
            "Motion has one clear camera action and no unintended pause, jump, reverse, melt, or morph.",
            "Captions remain readable and do not cover the focal subject or safe area.",
            "Narration has clear semantic phrasing and breathing pauses without long blanks; music ducks correctly and no syllables are clipped.",
            "Final beat resolves the opening promise and the ending is not abrupt.",
        ],
    }
    qa_dir = root / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    studio.atomic_json(qa_dir / "report.json", report)
    lines = [
        f"# QA — {project.get('project', {}).get('title', 'Project')}",
        "",
        f"Errors: {errors} · Warnings: {warnings} · Checks: {len(checks)}",
        "",
        "## Technical checks",
        "",
    ]
    lines.extend(f"- **{item['level'].upper()} · {item['name']}** — {item['message']}"
                 for item in checks)
    lines.extend(["", "## Extracted frames", ""])
    lines.extend(f"- `frames/{name}`" for name in frames)
    lines.extend(["", "## Human review", ""])
    lines.extend(f"- [ ] {item}" for item in report["human_review"])
    (qa_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("--final", default="final.mp4")
    parser.add_argument("--frames", type=int, default=6)
    args = parser.parse_args()
    root = Path(args.project_dir).resolve()
    final = Path(args.final)
    if not final.is_absolute():
        final = root / final
    try:
        report = run_qa(root, final.resolve(), max(0, args.frames))
    except (QaError, studio.StudioError, OSError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    summary = report["summary"]
    print(f"qa: errors={summary['errors']} warnings={summary['warnings']} "
          f"checks={summary['checks']}")
    print(f"report: {root / 'qa' / 'report.md'}")
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
