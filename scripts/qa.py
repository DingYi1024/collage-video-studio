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
    return list(zip(starts, durations))


def designed_hold_ranges(
    root: Path,
    project: dict[str, Any],
    artifacts: dict[str, Any],
) -> list[tuple[float, float, str]]:
    ranges: list[tuple[float, float, str]] = []
    offset = 0.0
    for beat, shot in studio.iter_shots(project):
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


def run_qa(root: Path, final: Path, frame_count: int = 6) -> dict[str, Any]:
    if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
        raise QaError("ffmpeg and ffprobe are required")
    project = studio.load_project(root)
    state = studio.load_state(root)
    checks: list[dict[str, str]] = []

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
    else:
        add(checks, "error", "video-stream", "no video stream")
    add(checks, "info" if audio else "error", "audio-stream",
        "present" if audio else "missing")

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

    if project.get("motion", {}).get("pipeline") == "layered":
        total_layers = 0
        total_animated = 0
        packs = 0
        layer_errors: list[str] = []
        for beat, shot in studio.iter_shots(project):
            key = studio.artifact_key("layers", beat, shot)
            record = artifacts.get(key, {})
            manifest_path = studio.resolve_path(root, record.get("path", ""))
            errors, layer_warnings, stats = layer_compositor.validate_manifest(manifest_path)
            layer_errors.extend(f"{key}: {item}" for item in errors)
            for message in layer_warnings:
                add(checks, "warning", "layered-motion", f"{key}: {message}")
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
            "Narration is intelligible; music ducks correctly; no syllables are clipped.",
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
