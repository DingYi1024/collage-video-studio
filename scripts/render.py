#!/usr/bin/env python3
"""Assemble registered motion, voice/source audio, music, captions, and watermark."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import overlays
import studio


CANVAS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "3:4": (1080, 1440),
    "4:3": (1440, 1080),
}
TRANSITIONS = {
    "fade",
    "fadeblack",
    "fadewhite",
    "wipeleft",
    "wiperight",
    "wipeup",
    "wipedown",
    "slideleft",
    "slideright",
    "slideup",
    "slidedown",
    "circleopen",
    "circleclose",
    "dissolve",
    "smoothleft",
    "smoothright",
    "smoothup",
    "smoothdown",
}


class RenderError(RuntimeError):
    pass


def run(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as exc:
        raise RenderError(f"command not found: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise RenderError(f"command failed ({exc.returncode}): {' '.join(command[:8])}") from exc


def ffmpeg(args: list[str]) -> None:
    run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args])


def duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=False,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def state_path(root: Path, record: dict[str, Any]) -> Path:
    return studio.resolve_path(root, record["path"]).resolve()


def concat_escape(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "'\\''")


def build_timeline(project: dict[str, Any], state: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    shots: list[dict[str, Any]] = []
    spans: list[dict[str, Any]] = []
    cursor = 0.0
    artifacts = state["artifacts"]
    for beat in project["beats"]:
        start = cursor
        for shot in beat["shots"]:
            key = studio.artifact_key("motion", beat, shot)
            record = artifacts[key]
            shot_duration = float(shot["duration_s"])
            shots.append({
                "key": key,
                "path": record["path"],
                "duration_s": shot_duration,
                "start_s": cursor,
            })
            cursor += shot_duration
        spans.append({"beat": beat, "start_s": start, "duration_s": cursor - start})
    return shots, spans


def normalize_shots(root: Path, run_dir: Path, shots: list[dict[str, Any]],
                    width: int, height: int, fps: int,
                    transition_duration: float = 0.0) -> list[Path]:
    normalized: list[Path] = []
    for index, shot in enumerate(shots):
        source = studio.resolve_path(root, shot["path"]).resolve()
        if not source.is_file():
            raise RenderError(f"missing motion file: {source}")
        target = run_dir / f"shot-{index:03d}.mp4"
        target_duration = float(shot["duration_s"])
        if transition_duration > 0 and index < len(shots) - 1:
            target_duration += transition_duration
        source_duration = duration(source)
        if source_duration <= 0:
            raise RenderError(f"cannot probe media duration: {source}")
        freeze = max(0.0, target_duration - source_duration)
        filter_graph = (
            f"[0:v]split=2[back][front];"
            f"[back]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},boxblur=24:2,eq=brightness=-0.08[bg];"
            f"[front]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,"
            f"tpad=stop_mode=clone:stop_duration={freeze + 0.25:.3f},fps={fps}[v]"
        )
        ffmpeg([
            "-i", str(source), "-filter_complex", filter_graph, "-map", "[v]", "-an",
            "-t", f"{target_duration:.3f}", "-c:v", "libx264", "-preset", "medium",
            "-crf", "18", "-pix_fmt", "yuv420p", str(target),
        ])
        normalized.append(target)
    return normalized


def transition_settings(project: dict[str, Any]) -> tuple[float, list[str]]:
    settings = project.get("motion", {}).get("transitions", {})
    if not settings or settings.get("enabled", True) is False:
        return 0.0, []
    try:
        duration_s = float(settings.get("duration_s", 0.35))
    except (TypeError, ValueError) as exc:
        raise RenderError("motion.transitions.duration_s must be numeric") from exc
    if duration_s < 0 or duration_s > 1.5:
        raise RenderError("motion.transitions.duration_s must be from 0 to 1.5")
    types = settings.get("types", ["wipeleft"])
    if not isinstance(types, list) or not types:
        raise RenderError("motion.transitions.types must be a non-empty array")
    normalized = [str(name).strip() for name in types]
    invalid = [name for name in normalized if name not in TRANSITIONS]
    if invalid:
        raise RenderError(
            f"unsupported transitions {invalid}; choose from {sorted(TRANSITIONS)}"
        )
    return duration_s, normalized


def concat_video(run_dir: Path, files: list[Path], shots: list[dict[str, Any]],
                 fps: int, transition_duration: float = 0.0,
                 transition_types: list[str] | None = None) -> Path:
    output = run_dir / "body.mp4"
    if transition_duration > 0 and len(files) > 1:
        inputs: list[str] = []
        for path in files:
            inputs.extend(["-i", str(path)])
        filters: list[str] = []
        previous = "[0:v]"
        offset = 0.0
        choices = transition_types or ["wipeleft"]
        for index in range(1, len(files)):
            offset += float(shots[index - 1]["duration_s"])
            output_label = f"[vx{index}]"
            transition = choices[(index - 1) % len(choices)]
            filters.append(
                f"{previous}[{index}:v]xfade=transition={transition}:"
                f"duration={transition_duration:.3f}:offset={offset:.3f}"
                f"{output_label}"
            )
            previous = output_label
        total = sum(float(item["duration_s"]) for item in shots)
        ffmpeg([
            *inputs,
            "-filter_complex", ";".join(filters),
            "-map", previous,
            "-an",
            "-t", f"{total:.3f}",
            "-r", str(fps),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            str(output),
        ])
        return output

    list_file = run_dir / "shots.txt"
    list_file.write_text(
        "".join(f"file '{concat_escape(path)}'\n" for path in files), encoding="utf-8"
    )
    ffmpeg(["-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(output)])
    return output


def beat_audio_inputs(root: Path, project: dict[str, Any], state: dict[str, Any],
                      spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mode = project["project"]["mode"]
    source = project.get("source", {})
    preserve = mode == "footage" and bool(source.get("preserve_original_audio"))
    result: list[dict[str, Any]] = []
    if preserve:
        source_path = studio.resolve_path(root, source["path"]).resolve()
        for span in spans:
            beat = span["beat"]
            result.append({
                "path": source_path,
                "trim_start": float(beat["start_s"]),
                "trim_duration": float(beat["end_s"]) - float(beat["start_s"]),
                "timeline_start": span["start_s"],
                "timeline_duration": span["duration_s"],
            })
    else:
        for span in spans:
            beat = span["beat"]
            record = state["artifacts"][studio.artifact_key("voice", beat)]
            result.append({
                "path": state_path(root, record),
                "trim_start": 0.0,
                "trim_duration": span["duration_s"],
                "timeline_start": span["start_s"],
                "timeline_duration": span["duration_s"],
            })
    return result


def make_overlays(run_dir: Path, project: dict[str, Any], spans: list[dict[str, Any]],
                  width: int, height: int) -> tuple[list[dict[str, Any]], Path | None]:
    audio = project.get("audio", {})
    caption_layers: list[dict[str, Any]] = []
    if audio.get("captions", True):
        for span in spans:
            beat = span["beat"]
            text = (beat.get("narration") or beat.get("transcript") or "").strip()
            if not text:
                continue
            path = run_dir / f"caption-{beat['id']}.png"
            overlays.render_caption(text, path, width, height, audio.get("caption_style", "clean"))
            caption_layers.append({
                "path": path,
                "start_s": span["start_s"] + 0.1,
                "end_s": span["start_s"] + span["duration_s"] - 0.1,
            })
    watermark = audio.get("watermark", "").strip()
    watermark_path = None
    if watermark:
        watermark_path = run_dir / "watermark.png"
        overlays.render_watermark(watermark, watermark_path, width, height)
    return caption_layers, watermark_path


def final_pass(root: Path, body: Path, project: dict[str, Any], state: dict[str, Any],
               spans: list[dict[str, Any]], caption_layers: list[dict[str, Any]],
               watermark: Path | None, total: float, output: Path) -> None:
    inputs = ["-i", str(body)]
    for layer in caption_layers:
        inputs += ["-loop", "1", "-i", str(layer["path"])]
    if watermark:
        inputs += ["-loop", "1", "-i", str(watermark)]

    audio_inputs = beat_audio_inputs(root, project, state, spans)
    first_audio_index = 1 + len(caption_layers) + (1 if watermark else 0)
    for item in audio_inputs:
        inputs += [
            "-ss", f"{item['trim_start']:.3f}",
            "-t", f"{item['trim_duration']:.3f}",
            "-i", str(item["path"]),
        ]

    music_record = state["artifacts"].get("music:main")
    music_index = None
    if music_record:
        music_index = first_audio_index + len(audio_inputs)
        inputs += ["-stream_loop", "-1", "-i", str(state_path(root, music_record))]

    filters: list[str] = []
    video_prev = "[0:v]"
    for index, layer in enumerate(caption_layers, 1):
        label = f"[vc{index}]"
        filters.append(
            f"{video_prev}[{index}:v]overlay=0:0:"
            f"enable='between(t,{layer['start_s']:.3f},{layer['end_s']:.3f})'{label}"
        )
        video_prev = label
    if watermark:
        watermark_index = 1 + len(caption_layers)
        filters.append(f"{video_prev}[{watermark_index}:v]overlay=0:0[vout]")
    else:
        filters.append(f"{video_prev}null[vout]")

    mix = project.get("audio", {}).get("mix", {})
    voice_volume = float(mix.get("voice", 1.0))
    music_volume = float(mix.get("music", 0.35))
    voice_labels: list[str] = []
    for offset, item in enumerate(audio_inputs):
        input_index = first_audio_index + offset
        delay_ms = max(0, round(float(item["timeline_start"]) * 1000))
        label = f"[voice{offset}]"
        filters.append(
            f"[{input_index}:a]atrim=0:{item['timeline_duration']:.3f},"
            f"asetpts=PTS-STARTPTS,volume={voice_volume:.3f},"
            f"adelay={delay_ms}:all=1{label}"
        )
        voice_labels.append(label)
    if voice_labels:
        filters.append(
            f"{''.join(voice_labels)}amix=inputs={len(voice_labels)}:"
            f"duration=longest:normalize=0,apad,atrim=0:{total:.3f}[voice_mix]"
        )
    else:
        filters.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{total:.3f}[voice_mix]")

    if music_index is not None:
        filters.extend([
            "[voice_mix]asplit=2[voice_final][voice_side]",
            f"[{music_index}:a]atrim=0:{total:.3f},volume={music_volume:.3f},"
            f"afade=t=out:st={max(0.0, total - 1.5):.3f}:d=1.5[music]",
            "[music][voice_side]sidechaincompress=threshold=0.025:ratio=10:"
            "attack=8:release=320[ducked]",
            f"[voice_final][ducked]amix=inputs=2:duration=longest:normalize=0,"
            f"atrim=0:{total:.3f}[aout]",
        ])
    else:
        filters.append("[voice_mix]anull[aout]")

    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg([
        *inputs, "-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]",
        "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(output),
    ])


def render(root: Path, output: Path) -> Path:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RenderError("ffmpeg and ffprobe are required")
    project = studio.load_project(root)
    state = studio.load_state(root)
    errors, warnings = studio.validate_project(root, project, "assemble")
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        raise RenderError("project is not render-ready:\n- " + "\n- ".join(errors))

    aspect = project["project"]["aspect"]
    width, height = CANVAS[aspect]
    fps = int(project["project"].get("fps", 24))
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = root / "render" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    shots, spans = build_timeline(project, state)
    total = sum(item["duration_s"] for item in shots)
    transition_duration, transition_types = transition_settings(project)
    if len(shots) < 2:
        transition_duration = 0.0
    normalized = normalize_shots(
        root, run_dir, shots, width, height, fps, transition_duration
    )
    body = concat_video(
        run_dir, normalized, shots, fps, transition_duration, transition_types
    )
    captions, watermark = make_overlays(run_dir, project, spans, width, height)
    final_pass(root, body, project, state, spans, captions, watermark, total, output)
    if not output.is_file() or output.stat().st_size <= 0:
        raise RenderError("ffmpeg completed without a non-empty output")
    print(f"rendered {output} ({total:.2f}s, {len(shots)} shots)")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("--output", default="final.mp4")
    args = parser.parse_args()
    root = Path(args.project_dir).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    try:
        render(root, output.resolve())
        return 0
    except (RenderError, studio.StudioError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
