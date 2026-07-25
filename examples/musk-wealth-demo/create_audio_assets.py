#!/usr/bin/env python3
"""Create the demo's restrained, original 24-second instrumental bed."""

from __future__ import annotations

import math
import random
import struct
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "source-media" / "audio" / "music-main.wav"
RATE = 48_000
DURATION = 24.0


def envelope(time_s: float, start: float, attack: float, decay: float) -> float:
    local = time_s - start
    if local < 0 or local > attack + decay:
        return 0.0
    if local < attack:
        return local / max(attack, 1e-6)
    return max(0.0, 1.0 - (local - attack) / max(decay, 1e-6))


def main() -> int:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
