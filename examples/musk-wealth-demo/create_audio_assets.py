#!/usr/bin/env python3
"""Create the demo's continuous narration evidence and original instrumental bed."""

from __future__ import annotations

import math
import random
import json
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "source-media" / "audio" / "music-main.wav"
VOICE_OUTPUT = ROOT / "source-media" / "audio" / "main.wav"
TIMING_OUTPUT = ROOT / "source-media" / "audio" / "main.timing.json"
RATE = 48_000
DURATION = 24.0


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(proc.stdout.strip())


def create_continuous_voice() -> None:
    project = json.loads((ROOT / "project.seed.json").read_text(encoding="utf-8"))
    texts = [str(beat["narration"]) for beat in project["beats"]]
    pauses = [0.18, 0.20, 0.22, 0.18, 0.24, 0.26]
    with tempfile.TemporaryDirectory(prefix="musk-voice-") as temp_value:
        temp = Path(temp_value)
        concat: list[Path] = []
        segments: list[dict[str, object]] = []
        cursor = 0.0
        for index, (text, pause_s) in enumerate(zip(texts, pauses), 1):
            source = ROOT / "source-media" / "audio" / f"b{index:02d}.wav"
            speech = temp / f"speech-{index:02d}.wav"
            run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(source),
                "-af",
                (
                    "silenceremove=start_periods=1:start_duration=0.01:"
                    "start_threshold=-42dB:start_silence=0.01,"
                    "areverse,"
                    "silenceremove=start_periods=1:start_duration=0.01:"
                    "start_threshold=-42dB:start_silence=0.01,"
                    "areverse,"
                    "silenceremove=stop_periods=-1:stop_duration=0.25:"
                    "stop_threshold=-42dB:stop_silence=0.20,"
                    "atempo=0.73"
                ),
                "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", str(speech),
            ])
            speech_s = duration(speech)
            concat.append(speech)
            segment = {
                "text": text,
                "boundary": "beat",
                "pause_after_s": pause_s,
                "start_s": cursor,
                "speech_end_s": cursor + speech_s,
                "speech_duration_s": speech_s,
                "pause_start_s": cursor + speech_s,
                "pause_end_s": cursor + speech_s + pause_s,
            }
            cursor += speech_s + pause_s
            segments.append(segment)
            silence = temp / f"pause-{index:02d}.wav"
            run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                "-t", f"{pause_s:.3f}", "-c:a", "pcm_s16le", str(silence),
            ])
            concat.append(silence)
        concat_file = temp / "concat.txt"
        concat_file.write_text(
            "".join(f"file '{path.as_posix()}'\n" for path in concat),
            encoding="utf-8",
        )
        raw = temp / "continuous-raw.wav"
        run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-c:a", "pcm_s16le", str(raw),
        ])
        run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(raw),
            "-af", "highpass=f=70,loudnorm=I=-18:TP=-2:LRA=7",
            "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le",
            str(VOICE_OUTPUT),
        ])
    TIMING_OUTPUT.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "continuous",
                "segments": segments,
                "duration_s": duration(VOICE_OUTPUT),
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def envelope(time_s: float, start: float, attack: float, decay: float) -> float:
    local = time_s - start
    if local < 0 or local > attack + decay:
        return 0.0
    if local < attack:
        return local / max(attack, 1e-6)
    return max(0.0, 1.0 - (local - attack) / max(decay, 1e-6))


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    create_continuous_voice()
    random.seed(2021)
    pulses = [beat * 0.75 for beat in range(32)]
    paper_hits = [0.55, 4.55, 8.55, 12.55, 16.55, 20.55, 23.18]
    chord = (55.0, 82.41, 110.0, 164.81)
    with wave.open(str(OUTPUT), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(RATE)
        for sample_index in range(round(DURATION * RATE)):
            time_s = sample_index / RATE
            progress = time_s / DURATION
            low = 0.0
            for pulse in pulses:
                strength = envelope(time_s, pulse, 0.018, 0.30)
                low += math.sin(2 * math.pi * 55.0 * (time_s - pulse)) * strength
            pad = sum(
                math.sin(2 * math.pi * frequency * time_s + index * 0.7)
                for index, frequency in enumerate(chord)
            ) / len(chord)
            pad *= 0.34 + 0.40 * progress
            tick = 0.0
            for hit in paper_hits:
                strength = envelope(time_s, hit, 0.004, 0.13)
                if strength:
                    noise = random.uniform(-1.0, 1.0)
                    tick += noise * strength
            rise = math.sin(2 * math.pi * (220 + 80 * progress) * time_s)
            rise *= envelope(time_s, 20.5, 0.45, 2.4) * 0.18
            sample = max(-1.0, min(1.0, low * 0.13 + pad * 0.10 + tick * 0.10 + rise))
            left = int(sample * 32767)
            right = int(sample * (0.96 + 0.03 * math.sin(time_s * 0.7)) * 32767)
            stream.writeframesraw(struct.pack("<hh", left, right))
    print(f"wrote {OUTPUT}")
    print(f"wrote {VOICE_OUTPUT} and {TIMING_OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
