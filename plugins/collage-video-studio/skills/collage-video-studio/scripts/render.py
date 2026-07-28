#!/usr/bin/env python3
"""Assemble registered motion, voice/source audio, music, captions, and watermark."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import overlays
import production_contract
import production_remotion
import readiness_seal
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
SEMANTIC_TRANSITIONS = {
    "paper-wipe": "wipeleft",
    "matched-cut": "dissolve",
    "camera-travel": "smoothleft",
    "layer-build": "circleopen",
    "punch-in": "zoomin",
    "timeline-slide": "wipeup",
    "map-travel": "slideleft",
}
TRANSITIONS.add("zoomin")


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


def video_fps(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=avg_frame_rate",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=False,
    )
    value = proc.stdout.strip()
    try:
        numerator, denominator = value.split("/", 1)
        return float(numerator) / max(1e-9, float(denominator))
    except (ValueError, ZeroDivisionError):
        try:
            return float(value)
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
    for beat_index, beat in enumerate(project["beats"]):
        start = cursor
        for shot_index, shot in enumerate(beat["shots"]):
            key = studio.artifact_key("motion", beat, shot)
            record = artifacts[key]
            fps = int(project.get("project", {}).get("fps", 30))
            shot_duration = (
                int(shot["duration_frames"]) / fps
                if shot.get("duration_frames") is not None
                else float(shot["duration_s"])
            )
            shots.append({
                "key": key,
                "path": record["path"],
                "duration_s": shot_duration,
                "start_s": cursor,
                "beat_id": str(beat.get("id", f"beat-{beat_index + 1:02d}")),
                "shot_id": str(shot.get("id", f"shot-{shot_index + 1:02d}")),
                "enter_transition": (
                    beat.get("transition", {}).get("mechanism")
                    or beat.get("transition_mechanism")
                    if shot_index == 0 and beat_index > 0
                    else None
                ),
                "enter_transition_duration_s": (
                    beat.get("transition", {}).get("duration_s")
                    or beat.get("transition_duration_s")
                    if shot_index == 0 and beat_index > 0
                    else None
                ),
                "out_transition": shot.get("transition_mechanism"),
            })
            cursor += shot_duration
        spans.append({"beat": beat, "start_s": start, "duration_s": cursor - start})
    return shots, spans


def normalize_shots(root: Path, run_dir: Path, shots: list[dict[str, Any]],
                    width: int, height: int, fps: int,
                    transition_duration: float = 0.0,
                    frame_conversion: str = "auto") -> list[Path]:
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
        source_rate = video_fps(source)
        use_interpolation = (
            frame_conversion == "interpolate"
            or (frame_conversion == "auto" and source_rate > 0 and source_rate < fps - 0.1)
        )
        cadence_filter = (
            f"minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:"
            "me_mode=bidir:vsbmc=1"
            if use_interpolation
            else f"fps={fps}"
        )
        freeze = max(0.0, target_duration - source_duration)
        filter_graph = (
            f"[0:v]split=2[back][front];"
            f"[back]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},boxblur=24:2,eq=brightness=-0.08[bg];"
            f"[front]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,"
            f"tpad=stop_mode=clone:stop_duration={freeze + 0.25:.3f},"
            f"{cadence_filter}[v]"
        )
        ffmpeg([
            "-i", str(source), "-filter_complex", filter_graph, "-map", "[v]", "-an",
            "-t", f"{target_duration:.3f}", "-c:v", "libx264", "-preset", "medium",
            "-crf", "18", "-pix_fmt", "yuv420p", str(target),
        ])
        normalized.append(target)
    return normalized


def semantic_transition_settings(
    shots: list[dict[str, Any]],
) -> tuple[float, list[str]]:
    if len(shots) < 2:
        return 0.0, []
    mechanisms: list[str] = []
    durations: list[float] = []
    declared = False
    for index in range(len(shots) - 1):
        current = shots[index]
        following = shots[index + 1]
        mechanism = following.get("enter_transition") or current.get("out_transition")
        if mechanism:
            declared = True
        mechanism = str(mechanism or "matched-cut")
        transition = SEMANTIC_TRANSITIONS.get(mechanism)
        if transition is None:
            raise RenderError(
                f"unsupported semantic transition mechanism {mechanism!r}; "
                f"choose from {sorted(SEMANTIC_TRANSITIONS)}"
            )
        mechanisms.append(transition)
        raw_duration = following.get("enter_transition_duration_s")
        durations.append(float(raw_duration if raw_duration is not None else 0.35))
    if not declared:
        return 0.0, []
    duration = max(durations)
    if duration <= 0 or duration > 1.5:
        raise RenderError("semantic transition duration must be from 0 to 1.5")
    return duration, mechanisms


def transition_settings(
    project: dict[str, Any],
    shots: list[dict[str, Any]] | None = None,
) -> tuple[float, list[str]]:
    if shots:
        semantic_duration, semantic_types = semantic_transition_settings(shots)
        if semantic_types:
            return semantic_duration, semantic_types
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
        voice_mode = str(
            project.get("audio", {}).get("voice", {}).get(
                "continuity_mode", "segmented"
            )
        )
        if voice_mode == "continuous":
            total = sum(float(span["duration_s"]) for span in spans)
            record = state["artifacts"]["voice:main"]
            return [{
                "path": state_path(root, record),
                "trim_start": 0.0,
                "trim_duration": total,
                "timeline_start": 0.0,
                "timeline_duration": total,
            }]
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


def timing_caption_cues(
    root: Path,
    project: dict[str, Any],
    state: dict[str, Any],
    spans: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    voice = project.get("audio", {}).get("voice", {})
    continuous = str(voice.get("continuity_mode", "segmented")) == "continuous"
    records: list[tuple[dict[str, Any], float]] = []
    if continuous:
        record = state.get("artifacts", {}).get("voice:main")
        if record:
            records.append((record, 0.0))
    else:
        for span in spans:
            beat = span["beat"]
            record = state.get("artifacts", {}).get(
                studio.artifact_key("voice", beat)
            )
            if record:
                records.append((record, float(span["start_s"])))
    cues: list[dict[str, Any]] = []
    for record, offset in records:
        timing_path = record.get("metadata", {}).get("timing_path")
        if not timing_path:
            continue
        try:
            timing = studio.load_json(studio.resolve_path(root, timing_path))
        except studio.StudioError:
            continue
        for segment in timing.get("segments", []):
            text = str(segment.get("text", "")).strip()
            try:
                start = offset + float(segment["start_s"])
                end = offset + float(segment["pause_end_s"])
            except (KeyError, TypeError, ValueError):
                continue
            if text and end > start:
                cues.append({
                    "text": text,
                    "start_s": max(0.0, start - 0.04),
                    "end_s": end + 0.04,
                })
    return sorted(cues, key=lambda item: float(item["start_s"]))


def make_overlays(
    root: Path,
    run_dir: Path,
    project: dict[str, Any],
    state: dict[str, Any],
    spans: list[dict[str, Any]],
    width: int,
    height: int,
) -> tuple[list[dict[str, Any]], Path | None]:
    audio = project.get("audio", {})
    caption_layers: list[dict[str, Any]] = []
    if audio.get("captions", True):
        cues = timing_caption_cues(root, project, state, spans)
        if not cues:
            cues = [
                {
                    "text": (
                        span["beat"].get("narration")
                        or span["beat"].get("transcript")
                        or ""
                    ).strip(),
                    "start_s": span["start_s"] + 0.1,
                    "end_s": span["start_s"] + span["duration_s"] - 0.1,
                }
                for span in spans
            ]
        for index, cue in enumerate(cues, 1):
            if not cue["text"] or cue["end_s"] <= cue["start_s"]:
                continue
            path = run_dir / f"caption-{index:03d}.png"
            overlays.render_caption(
                cue["text"],
                path,
                width,
                height,
                audio.get("caption_style", "clean"),
            )
            caption_layers.append({
                "path": path,
                "start_s": cue["start_s"],
                "end_s": cue["end_s"],
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
    gain_db = float(project.get("audio", {}).get("narration_gain_db", 0.0))
    voice_volume = float(mix.get("voice", 1.0)) * math.pow(10, gain_db / 20)
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


def visual_cache_fingerprint(
    project: dict[str, Any],
    state: dict[str, Any],
    shots: list[dict[str, Any]],
    caption_layers: list[dict[str, Any]],
    watermark: Path | None,
) -> str:
    visual_artifacts = {
        key: {
            "content_sha256": value.get("content_sha256"),
            "job_fingerprint": value.get("job_fingerprint")
            or value.get("metadata", {}).get("job_fingerprint"),
        }
        for key, value in state.get("artifacts", {}).items()
        if not key.startswith(("voice:", "music:"))
    }
    captions = [
        {
            "start_s": item["start_s"],
            "end_s": item["end_s"],
            "content_sha256": production_contract.file_digest(item["path"]),
        }
        for item in caption_layers
    ]
    return production_contract.canonical_digest({
        "project": {
            "aspect": project.get("project", {}).get("aspect"),
            "fps": project.get("project", {}).get("fps"),
            "beats": project.get("beats"),
            "motion": project.get("motion"),
            "captions": project.get("audio", {}).get("captions"),
            "caption_style": project.get("audio", {}).get("caption_style"),
            "watermark": project.get("audio", {}).get("watermark"),
        },
        "shots": shots,
        "artifacts": visual_artifacts,
        "captions": captions,
        "watermark_sha256": (
            production_contract.file_digest(watermark) if watermark else None
        ),
    })


def remux_audio(
    root: Path,
    visual_master: Path,
    project: dict[str, Any],
    state: dict[str, Any],
    spans: list[dict[str, Any]],
    total: float,
    output: Path,
) -> None:
    inputs = ["-i", str(visual_master)]
    audio_inputs = beat_audio_inputs(root, project, state, spans)
    for item in audio_inputs:
        inputs += [
            "-ss", f"{item['trim_start']:.3f}",
            "-t", f"{item['trim_duration']:.3f}",
            "-i", str(item["path"]),
        ]
    music_record = state["artifacts"].get("music:main")
    music_index = None
    if music_record:
        music_index = 1 + len(audio_inputs)
        inputs += ["-stream_loop", "-1", "-i", str(state_path(root, music_record))]
    filters: list[str] = []
    mix = project.get("audio", {}).get("mix", {})
    gain_db = float(project.get("audio", {}).get("narration_gain_db", 0.0))
    voice_volume = float(mix.get("voice", 1.0)) * math.pow(10, gain_db / 20)
    music_volume = float(mix.get("music", 0.35))
    labels: list[str] = []
    for offset, item in enumerate(audio_inputs, 1):
        delay_ms = max(0, round(float(item["timeline_start"]) * 1000))
        label = f"[voice{offset}]"
        filters.append(
            f"[{offset}:a]atrim=0:{item['timeline_duration']:.3f},"
            f"asetpts=PTS-STARTPTS,volume={voice_volume:.5f},"
            f"adelay={delay_ms}:all=1{label}"
        )
        labels.append(label)
    if labels:
        filters.append(
            f"{''.join(labels)}amix=inputs={len(labels)}:"
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
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "0:v:0", "-map", "[aout]",
        "-t", f"{total:.3f}", "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(output),
    ])


def render(root: Path, output: Path) -> Path:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RenderError("ffmpeg and ffprobe are required")
    project = studio.load_project(root)
    state = studio.load_state(root)
    if bool(project.get("production", {}).get("require_readiness_seal", False)):
        readiness = readiness_seal.verify(root)
        if not readiness["passed"]:
            raise RenderError("registered readiness seal is stale")
    errors, warnings = studio.validate_project(root, project, "assemble")
    for warning in warnings:
        print(f"WARNING: {warning}")
    if errors:
        raise RenderError("project is not render-ready:\n- " + "\n- ".join(errors))
    production = production_contract.profile_config(project)
    if production and production.get("render_engine") == "remotion":
        try:
            return production_remotion.render(root, output)
        except production_remotion.ProductionRemotionError as exc:
            raise RenderError(str(exc)) from exc

    aspect = project["project"]["aspect"]
    width, height = CANVAS[aspect]
    fps = int(project["project"].get("fps", 30))
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = root / "render" / stamp
    run_dir.mkdir(parents=True, exist_ok=False)
    shots, spans = build_timeline(project, state)
    total = sum(item["duration_s"] for item in shots)
    transition_duration, transition_types = transition_settings(project, shots)
    if len(shots) < 2:
        transition_duration = 0.0
    captions, watermark = make_overlays(
        root, run_dir, project, state, spans, width, height
    )
    cache_root = root / "render-cache"
    cache_master = cache_root / "visual-master.mp4"
    subtitle_free_master = cache_root / "subtitle-free-master.mp4"
    cache_manifest = cache_root / "visual-master.json"
    visual_fingerprint = visual_cache_fingerprint(
        project, state, shots, captions, watermark
    )
    cached = {}
    if cache_manifest.is_file():
        try:
            cached = json.loads(cache_manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            cached = {}
    if (
        cache_master.is_file()
        and (not captions or subtitle_free_master.is_file())
        and cached.get("visual_fingerprint") == visual_fingerprint
        and cached.get("content_sha256")
        == production_contract.file_digest(cache_master)
    ):
        remux_audio(root, cache_master, project, state, spans, total, output)
        print(f"reused visual master for audio remux: {cache_master}")
        if not output.is_file() or output.stat().st_size <= 0:
            raise RenderError("audio remux completed without a non-empty output")
        print(f"rendered {output} ({total:.2f}s, {len(shots)} shots)")
        return output
    normalized = normalize_shots(
        root,
        run_dir,
        shots,
        width,
        height,
        fps,
        transition_duration,
        str(project.get("motion", {}).get("frame_conversion", "auto")),
    )
    body = concat_video(
        run_dir, normalized, shots, fps, transition_duration, transition_types
    )
    cache_root.mkdir(parents=True, exist_ok=True)
    ffmpeg([
        "-i", str(body), "-map", "0:v:0", "-an", "-c:v", "copy",
        str(subtitle_free_master),
    ])
    final_pass(root, body, project, state, spans, captions, watermark, total, output)
    ffmpeg([
        "-i", str(output), "-map", "0:v:0", "-an", "-c:v", "copy",
        str(cache_master),
    ])
    studio.atomic_json(cache_manifest, {
        "visual_fingerprint": visual_fingerprint,
        "content_sha256": production_contract.file_digest(cache_master),
        "subtitle_free_master": str(subtitle_free_master),
        "subtitle_free_sha256": production_contract.file_digest(
            subtitle_free_master
        ),
    })
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
    except (
        RenderError,
        studio.StudioError,
        readiness_seal.ReadinessSealError,
        KeyError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
