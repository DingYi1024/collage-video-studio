#!/usr/bin/env python3
"""Generate scene-length, directed Mandarin narration with Edge neural TTS."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import audio_qa


class VoiceError(RuntimeError):
    pass


PROSODY_DEFAULTS = {
    "comma_pause_s": 0.10,
    "clause_pause_s": 0.16,
    "sentence_pause_s": 0.22,
    "beat_pause_s": 0.26,
    "min_clause_chars": 8,
}


def resolve_prosody_config(raw: dict[str, Any] | None = None) -> dict[str, float]:
    config = {key: float(value) for key, value in PROSODY_DEFAULTS.items()}
    if not raw:
        return config
    for key in PROSODY_DEFAULTS:
        if key not in raw:
            continue
        try:
            value = float(raw[key])
        except (TypeError, ValueError) as exc:
            raise VoiceError(f"audio.voice.prosody.{key} must be numeric") from exc
        maximum = 80.0 if key == "min_clause_chars" else 0.8
        if value < 0 or value > maximum:
            raise VoiceError(
                f"audio.voice.prosody.{key} must be from 0 to {maximum:g}"
            )
        config[key] = value
    return config


def build_prosody_plan(
    text: str,
    raw_config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    config = resolve_prosody_config(raw_config)
    plan: list[dict[str, Any]] = []
    buffer: list[str] = []

    def flush(kind: str, pause_s: float) -> None:
        segment = "".join(buffer).strip()
        buffer.clear()
        if segment:
            plan.append({
                "text": segment,
                "boundary": kind,
                "pause_after_s": pause_s,
            })
        elif plan:
            plan[-1]["pause_after_s"] = max(
                float(plan[-1]["pause_after_s"]), pause_s
            )
            plan[-1]["boundary"] = kind

    for position, character in enumerate(text):
        if character in "\r\n":
            flush("beat", config["beat_pause_s"])
            continue
        buffer.append(character)
        decimal_point = (
            character == "."
            and position > 0
            and position + 1 < len(text)
            and text[position - 1].isdigit()
            and text[position + 1].isdigit()
        )
        if character in "。！？.!?" and not decimal_point:
            flush("sentence", config["sentence_pause_s"])
        elif character in "；;：:…":
            flush("clause", config["clause_pause_s"])
        elif character in "，,":
            visible = len("".join(buffer).replace(" ", ""))
            if visible >= config["min_clause_chars"]:
                flush("comma", config["comma_pause_s"])
    flush("end", 0.0)
    if plan:
        plan[-1]["pause_after_s"] = 0.0
        plan[-1]["boundary"] = "end"
    return plan


def load_project(project_dir: Path) -> dict[str, Any]:
    path = project_dir / "project.json"
    try:
        project = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VoiceError(f"cannot read {path}: {exc}") from exc
    if not isinstance(project, dict):
        raise VoiceError("project.json must contain a JSON object")
    return project


def narration_items(project: dict[str, Any]) -> list[dict[str, Any]]:
    continuity_mode = str(
        project.get("audio", {}).get("voice", {}).get(
            "continuity_mode", "segmented"
        )
    )
    items: list[dict[str, Any]] = []
    for index, beat in enumerate(project.get("beats", []), start=1):
        text = str(beat.get("narration", "")).strip()
        if not text:
            continue
        beat_id = str(beat.get("id") or f"beat-{index:02d}")
        try:
            duration = float(
                beat.get("duration_s")
                or sum(float(shot.get("duration_s", 0)) for shot in beat.get("shots", []))
            )
        except (TypeError, ValueError) as exc:
            raise VoiceError(
                f"{beat_id}: beat or shot duration_s must be a positive number"
            ) from exc
        if duration <= 0:
            raise VoiceError(f"{beat_id}: duration_s must be positive")
        items.append({"id": beat_id, "text": text, "duration_s": duration})
    if not items:
        raise VoiceError("project has no narrated beats")
    if continuity_mode == "continuous":
        text = "\n".join(
            item["text"].rstrip()
            + ("" if item["text"].rstrip().endswith(tuple("。！？.!?")) else "。")
            for item in items
        )
        return [{
            "id": "main",
            "text": text,
            "duration_s": sum(float(item["duration_s"]) for item in items),
        }]
    return items


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(command, text=True, capture_output=True, check=False)
    if proc.returncode:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise VoiceError(detail or f"command failed: {' '.join(command)}")
    return proc


def media_duration(path: Path) -> float:
    proc = run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    try:
        return float(proc.stdout.strip())
    except ValueError as exc:
        raise VoiceError(f"ffprobe returned an invalid duration for {path}") from exc


def master_voice(source: Path, output: Path, duration_s: float) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(source),
        "-af", (
            "highpass=f=70,"
            "loudnorm=I=-18:TP=-2:LRA=7,"
            f"apad=pad_dur={duration_s:.3f}"
        ),
        "-t", f"{duration_s:.3f}",
        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(output),
    ])


def trim_clause(source: Path, output: Path) -> None:
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(source),
        "-af", (
            "silenceremove=start_periods=1:start_duration=0.01:"
            "start_threshold=-42dB:start_silence=0.01,"
            "areverse,"
            "silenceremove=start_periods=1:start_duration=0.01:"
            "start_threshold=-42dB:start_silence=0.01,"
            "areverse"
        ),
        "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(output),
    ])


def make_silence(output: Path, duration_s: float) -> None:
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
        "-t", f"{duration_s:.3f}",
        "-c:a", "pcm_s16le", str(output),
    ])


def concat_escape(path: Path) -> str:
    return path.resolve().as_posix().replace("'", "'\\''")


async def synthesize_with_prosody(
    edge_tts: Any,
    text: str,
    output: Path,
    temp_dir: Path,
    voice: str,
    rate: str,
    volume: str,
    pitch: str,
    prosody_config: dict[str, Any],
) -> list[dict[str, Any]]:
    plan = build_prosody_plan(text, prosody_config)
    if not plan:
        raise VoiceError("narration has no speakable text")
    concat_paths: list[Path] = []
    silence_paths: dict[float, Path] = {}
    for index, segment in enumerate(plan):
        encoded = temp_dir / f"clause-{index:03d}.mp3"
        trimmed = temp_dir / f"clause-{index:03d}.wav"
        communicate = edge_tts.Communicate(
            segment["text"],
            voice=voice,
            rate=rate,
            volume=volume,
            pitch=pitch,
        )
        await communicate.save(str(encoded))
        trim_clause(encoded, trimmed)
        concat_paths.append(trimmed)
        pause_s = round(float(segment["pause_after_s"]), 3)
        if pause_s <= 0:
            continue
        silence = silence_paths.get(pause_s)
        if silence is None:
            silence = temp_dir / f"silence-{pause_s:.3f}.wav"
            make_silence(silence, pause_s)
            silence_paths[pause_s] = silence
        concat_paths.append(silence)
    list_path = temp_dir / "prosody-concat.txt"
    list_path.write_text(
        "".join(
            f"file '{concat_escape(path)}'\n"
            for path in concat_paths
        ),
        encoding="utf-8",
    )
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(list_path),
        "-c:a", "pcm_s16le", str(output),
    ])
    return plan


async def synthesize(
    items: list[dict[str, Any]],
    output_dir: Path,
    voice: str,
    rate: str,
    volume: str,
    pitch: str,
    overwrite: bool,
    qa_config: dict[str, Any],
    prosody_config: dict[str, Any],
) -> None:
    try:
        import edge_tts
    except ImportError as exc:
        raise VoiceError(
            "edge-tts is not installed; run `python -m pip install -r requirements.txt`"
        ) from exc

    with tempfile.TemporaryDirectory(prefix="collage-voice-") as temp_name:
        temp_dir = Path(temp_name)
        for item in items:
            output = output_dir / f"{item['id']}.wav"
            if output.exists() and not overwrite:
                print(f"skip {output} (use --overwrite to replace it)")
                continue
            item_temp = temp_dir / item["id"]
            item_temp.mkdir(parents=True, exist_ok=True)
            raw = item_temp / f"{item['id']}.wav"
            plan = await synthesize_with_prosody(
                edge_tts=edge_tts,
                text=item["text"],
                output=raw,
                temp_dir=item_temp,
                voice=voice,
                rate=rate,
                volume=volume,
                pitch=pitch,
                prosody_config=prosody_config,
            )
            spoken_s = media_duration(raw)
            available_s = item["duration_s"] - 0.08
            if spoken_s > available_s:
                raise VoiceError(
                    f"{item['id']}: speech is {spoken_s:.2f}s but the scene allows "
                    f"{available_s:.2f}s; shorten the copy or increase --rate"
                )
            raw_audit = audio_qa.audit_timeline([{
                "path": raw,
                "label": item["id"],
                "timeline_start_s": 0,
                "timeline_duration_s": item["duration_s"],
                "text": item["text"],
            }], qa_config)
            if raw_audit["issues"]:
                raise VoiceError(
                    f"{item['id']}: narration continuity failed: "
                    + "; ".join(raw_audit["issues"])
                    + "; edit the copy or adjust a near-normal speaking rate"
                )
            master_voice(raw, output, item["duration_s"])
            print(
                f"wrote {output} "
                f"(speech {spoken_s:.2f}s, scene {item['duration_s']:.2f}s, "
                f"{len(plan)} prosody phrase(s))"
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Direct and generate natural Mandarin narration per story beat."
    )
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--voice")
    parser.add_argument("--rate")
    parser.add_argument("--volume")
    parser.add_argument("--pitch")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise VoiceError("ffmpeg and ffprobe are required")
    project_dir = args.project_dir.resolve()
    project = load_project(project_dir)
    items = narration_items(project)
    voice_config = project.get("audio", {}).get("voice", {})
    voice = args.voice or str(voice_config.get("voice_id", "zh-CN-XiaoxiaoNeural"))
    rate = args.rate or str(voice_config.get("rate", "-2%"))
    volume = args.volume or str(voice_config.get("volume", "+0%"))
    pitch = args.pitch or str(voice_config.get("pitch", "-2Hz"))
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else project_dir / "source-media" / "audio"
    )
    if args.dry_run:
        for item in items:
            print(
                f"{item['id']}: {item['duration_s']:.2f}s | {item['text']} | "
                f"{voice} {rate} {pitch}"
            )
            for segment in build_prosody_plan(
                item["text"], voice_config.get("prosody", {})
            ):
                print(
                    f"  {segment['boundary']}: "
                    f"{segment['pause_after_s']:.2f}s | {segment['text']}"
                )
        return 0
    asyncio.run(synthesize(
        items=items,
        output_dir=output_dir,
        voice=voice,
        rate=rate,
        volume=volume,
        pitch=pitch,
        overwrite=args.overwrite,
        qa_config=voice_config.get("qa", {}),
        prosody_config=voice_config.get("prosody", {}),
    ))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VoiceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
