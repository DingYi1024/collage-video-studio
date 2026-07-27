#!/usr/bin/env python3
"""Generate natural, language-aware narration with Edge neural TTS."""

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
import narration
import studio


class VoiceError(RuntimeError):
    pass


build_prosody_plan = narration.build_prosody_plan
resolve_prosody_config = narration.resolve_prosody_config


def load_project(project_dir: Path) -> dict[str, Any]:
    path = project_dir / "project.json"
    try:
        project = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VoiceError(f"cannot read {path}: {exc}") from exc
    if not isinstance(project, dict):
        raise VoiceError("project.json must contain a JSON object")
    return project


narration_items = narration.narration_items


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
    language: str = "zh",
    profile: str = "conversational",
) -> list[dict[str, Any]]:
    plan = build_prosody_plan(text, prosody_config, language, profile)
    if not plan:
        raise VoiceError("narration has no speakable text")
    concat_paths: list[Path] = []
    silence_paths: dict[float, Path] = {}
    cursor_s = 0.0
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
        speech_s = media_duration(trimmed)
        segment["start_s"] = cursor_s
        segment["speech_end_s"] = cursor_s + speech_s
        segment["speech_duration_s"] = speech_s
        cursor_s += speech_s
        pause_s = round(float(segment["pause_after_s"]), 3)
        segment["pause_start_s"] = cursor_s
        segment["pause_end_s"] = cursor_s + pause_s
        cursor_s += pause_s
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
    language: str,
    profile: str,
) -> list[dict[str, Any]]:
    try:
        import edge_tts
    except ImportError as exc:
        raise VoiceError(
            "edge-tts is not installed; run `python -m pip install -r requirements.txt`"
        ) from exc

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="collage-voice-") as temp_name:
        temp_dir = Path(temp_name)
        for item in items:
            output = output_dir / f"{item['id']}.wav"
            if output.exists() and not overwrite:
                print(f"skip {output} (use --overwrite to replace it)")
                results.append({
                    "id": item["id"],
                    "output": output,
                    "timing": output.with_suffix(".timing.json"),
                    "skipped": True,
                })
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
                language=language,
                profile=profile,
            )
            spoken_s = media_duration(raw)
            available_s = item["duration_s"] - 0.08
            if spoken_s > available_s:
                raise VoiceError(
                    f"{item['id']}: speech is {spoken_s:.2f}s but the scene allows "
                    f"{available_s:.2f}s; shorten the copy or increase --rate"
                )
            raw_timing = item_temp / f"{item['id']}.timing.json"
            studio.atomic_json(raw_timing, {
                "schema_version": 1,
                "artifact_id": f"voice:{item['id']}",
                "language": language,
                "text": item["text"],
                "segments": plan,
            })
            raw_audit = audio_qa.audit_timeline([{
                "path": raw,
                "label": item["id"],
                "timeline_start_s": 0,
                "timeline_duration_s": item["duration_s"],
                "text": item["text"],
                "timing_path": raw_timing,
            }], qa_config, check_levels=False)
            if raw_audit["issues"]:
                raise VoiceError(
                    f"{item['id']}: narration continuity failed: "
                    + "; ".join(raw_audit["issues"])
                    + "; edit the copy or adjust a near-normal speaking rate"
                )
            master_voice(raw, output, item["duration_s"])
            timing_path = output.with_suffix(".timing.json")
            studio.atomic_json(timing_path, {
                "schema_version": 1,
                "artifact_id": f"voice:{item['id']}",
                "language": language,
                "voice_id": voice,
                "rate": rate,
                "profile": profile,
                "text": item["text"],
                "speech_duration_s": spoken_s,
                "timeline_duration_s": float(item["duration_s"]),
                "segments": plan,
            })
            results.append({
                "id": item["id"],
                "output": output,
                "timing": timing_path,
                "skipped": False,
            })
            print(
                f"wrote {output} "
                f"(speech {spoken_s:.2f}s, scene {item['duration_s']:.2f}s, "
                f"{len(plan)} prosody phrase(s))"
            )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan and generate natural multilingual narration per story beat."
    )
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--voice")
    parser.add_argument("--rate")
    parser.add_argument("--volume")
    parser.add_argument("--pitch")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true", help="emit machine-readable preflight")
    parser.add_argument(
        "--no-register",
        action="store_true",
        help="do not register generated audio in project state",
    )
    args = parser.parse_args()

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise VoiceError("ffmpeg and ffprobe are required")
    project_dir = args.project_dir.resolve()
    project = load_project(project_dir)
    items = narration_items(project)
    language = str(project.get("project", {}).get("language", "zh"))
    voice_config = project.get("audio", {}).get("voice", {})
    profile = str(voice_config.get("profile", "conversational"))
    voice = narration.default_voice(
        language,
        args.voice or voice_config.get("voice_id"),
    )
    rate = args.rate or str(voice_config.get("rate", "+0%"))
    narration.parse_rate_multiplier(rate)
    volume = args.volume or str(voice_config.get("volume", "+0%"))
    pitch = args.pitch or str(voice_config.get("pitch", "-2Hz"))
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else project_dir / "media" / "audio"
    )
    if args.dry_run:
        report = narration.preflight_project(project)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        print(
            f"language={report['language']} voice={report['voice_id']} "
            f"profile={report['profile']} rate={report['rate']}"
        )
        for warning in report["warnings"]:
            print(f"WARNING: {warning}")
        for item in items:
            print(
                f"{item['id']}: {item['duration_s']:.2f}s | {item['text']} | "
                f"{voice} {rate} {pitch}"
            )
            for segment in build_prosody_plan(
                item["text"],
                voice_config.get("prosody", {}),
                language,
                profile,
            ):
                print(
                    f"  {segment['boundary']}: "
                    f"{segment['pause_after_s']:.2f}s | {segment['text']}"
                )
        return 0
    results = asyncio.run(synthesize(
        items=items,
        output_dir=output_dir,
        voice=voice,
        rate=rate,
        volume=volume,
        pitch=pitch,
        overwrite=args.overwrite,
        qa_config=voice_config.get("qa", {}),
        prosody_config=voice_config.get("prosody", {}),
        language=language,
        profile=profile,
    ))
    if not args.no_register:
        for result in results:
            output = Path(result["output"])
            timing = Path(result["timing"])
            if not output.is_file():
                continue
            metadata: dict[str, Any] = {}
            if timing.is_file():
                metadata["timing_path"] = studio.portable_path(project_dir, timing)
                metadata["timing_status"] = "provided"
            studio.register_artifact(
                project_dir,
                f"voice:{result['id']}",
                output,
                metadata=metadata,
            )
            print(f"registered voice:{result['id']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (VoiceError, narration.NarrationError, studio.StudioError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
