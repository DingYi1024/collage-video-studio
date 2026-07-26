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
        text = " ".join(
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


async def synthesize(
    items: list[dict[str, Any]],
    output_dir: Path,
    voice: str,
    rate: str,
    volume: str,
    pitch: str,
    overwrite: bool,
    qa_config: dict[str, Any],
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
            raw = temp_dir / f"{item['id']}.mp3"
            communicate = edge_tts.Communicate(
                item["text"],
                voice=voice,
                rate=rate,
                volume=volume,
                pitch=pitch,
            )
            await communicate.save(str(raw))
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
                f"(speech {spoken_s:.2f}s, scene {item['duration_s']:.2f}s)"
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
    ))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VoiceError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
