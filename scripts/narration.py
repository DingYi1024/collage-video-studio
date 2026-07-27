#!/usr/bin/env python3
"""Provider-neutral narration planning, language defaults, and timing preflight."""

from __future__ import annotations

import math
import re
from typing import Any


class NarrationError(RuntimeError):
    pass


VOICE_DEFAULTS = {
    "zh": "zh-CN-XiaoxiaoNeural",
    "en": "en-US-JennyNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "es": "es-ES-ElviraNeural",
    "pt": "pt-BR-FranciscaNeural",
    "it": "it-IT-ElsaNeural",
}

PACING_PROFILES: dict[str, dict[str, float]] = {
    "energetic": {
        "comma_pause_s": 0.08,
        "clause_pause_s": 0.13,
        "sentence_pause_s": 0.18,
        "beat_pause_s": 0.22,
        "safety_pause_s": 0.16,
    },
    "conversational": {
        "comma_pause_s": 0.10,
        "clause_pause_s": 0.16,
        "sentence_pause_s": 0.22,
        "beat_pause_s": 0.26,
        "safety_pause_s": 0.16,
    },
    "measured": {
        "comma_pause_s": 0.12,
        "clause_pause_s": 0.20,
        "sentence_pause_s": 0.28,
        "beat_pause_s": 0.34,
        "safety_pause_s": 0.18,
    },
    "dramatic": {
        "comma_pause_s": 0.15,
        "clause_pause_s": 0.25,
        "sentence_pause_s": 0.36,
        "beat_pause_s": 0.46,
        "safety_pause_s": 0.20,
    },
}

KNOWN_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "e.g", "i.e", "fig", "no", "inc", "ltd", "co", "corp", "jan", "feb",
    "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
}

_CJK_RANGES = (
    "\u3040-\u30ff"  # Japanese kana
    "\u3400-\u4dbf\u4e00-\u9fff"  # CJK
    "\uac00-\ud7af"  # Korean Hangul
)


def normalize_language(value: str | None) -> str:
    language = str(value or "").strip().replace("_", "-").lower()
    if not language:
        return "zh"
    return language.split("-", 1)[0]


def is_cjk_language(language: str | None) -> bool:
    return normalize_language(language) in {"zh", "ja", "ko"}


def default_voice(language: str | None, configured: str | None = None) -> str:
    value = str(configured or "").strip()
    if value and value.lower() != "auto":
        return value
    base = normalize_language(language)
    if base not in VOICE_DEFAULTS:
        raise NarrationError(
            f"no automatic Edge voice for language {language!r}; "
            "set audio.voice.voice_id explicitly"
        )
    return VOICE_DEFAULTS[base]


def parse_rate_multiplier(rate: str | None) -> float:
    value = str(rate or "+0%").strip()
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)%", value)
    if not match:
        raise NarrationError(
            f"audio.voice.rate must be a signed percentage such as +0% or -2%; got {value!r}"
        )
    multiplier = 1.0 + float(match.group(1)) / 100.0
    if multiplier < 0.75 or multiplier > 1.25:
        raise NarrationError("audio.voice.rate must stay between -25% and +25%")
    return multiplier


def _numeric(
    raw: dict[str, Any],
    key: str,
    default: float,
    maximum: float,
) -> float:
    try:
        value = float(raw.get(key, default))
    except (TypeError, ValueError) as exc:
        raise NarrationError(f"audio.voice.prosody.{key} must be numeric") from exc
    if value < 0 or value > maximum:
        raise NarrationError(
            f"audio.voice.prosody.{key} must be from 0 to {maximum:g}"
        )
    return value


def resolve_prosody_config(
    raw: dict[str, Any] | None = None,
    language: str | None = None,
    profile: str | None = None,
) -> dict[str, float]:
    source = dict(raw or {})
    selected = str(profile or source.get("profile") or "conversational").strip().lower()
    if selected not in PACING_PROFILES:
        raise NarrationError(
            f"audio.voice.profile must be one of {sorted(PACING_PROFILES)}"
        )
    defaults = PACING_PROFILES[selected]
    cjk = is_cjk_language(language)
    config = {
        key: _numeric(source, key, value, 0.8)
        for key, value in defaults.items()
    }
    legacy_min = source.get("min_clause_chars")
    min_default = 8.0 if cjk else 4.0
    config["min_comma_units"] = _numeric(
        source,
        "min_comma_units",
        float(legacy_min) if legacy_min is not None else min_default,
        80.0,
    )
    config["max_phrase_units"] = _numeric(
        source,
        "max_phrase_units",
        20.0 if cjk else 12.0,
        200.0,
    )
    return config


def text_units(text: str, language: str | None = None) -> int:
    if is_cjk_language(language):
        return len(re.findall(fr"[A-Za-z0-9{_CJK_RANGES}]", text))
    return len(re.findall(r"\b[\w]+(?:['’][\w]+)?\b", text, flags=re.UNICODE))


def _period_is_boundary(text: str, position: int) -> bool:
    previous = text[position - 1] if position > 0 else ""
    following = text[position + 1] if position + 1 < len(text) else ""
    if previous.isdigit() and following.isdigit():
        return False
    if following == ".":
        return False
    if previous == ".":
        return not following or following.isspace()
    if previous.isalnum() and following.isalnum():
        return False
    token_start = max(
        text.rfind(" ", 0, position),
        text.rfind("\n", 0, position),
        text.rfind("\t", 0, position),
    ) + 1
    current_token = text[token_start:position + 1].lower()
    if (
        ("://" in current_token or "@" in current_token or current_token.startswith("www."))
        and following
        and not following.isspace()
    ):
        return False
    prefix = text[: position + 1]
    token_match = re.search(r"([A-Za-z](?:[A-Za-z.]*)?)\.$", prefix)
    token = token_match.group(1).lower() if token_match else ""
    if token in KNOWN_ABBREVIATIONS:
        return False
    if re.fullmatch(r"(?:[a-z]\.){2,}", f"{token}.", flags=re.IGNORECASE):
        return False
    return True


def _colon_is_boundary(text: str, position: int) -> bool:
    previous = text[position - 1] if position > 0 else ""
    following = text[position + 1] if position + 1 < len(text) else ""
    if previous.isdigit() and following.isdigit():
        return False
    if text[position + 1: position + 3] == "//":
        return False
    return True


def _split_overlong(
    text: str,
    maximum_units: int,
    language: str | None,
) -> list[str]:
    if maximum_units <= 0 or text_units(text, language) <= maximum_units:
        return [text.strip()]
    chunks: list[str] = []
    remaining = text.strip()
    cjk = is_cjk_language(language)
    total_units = text_units(remaining, language)
    chunk_count = math.ceil(total_units / maximum_units)
    target_units = math.ceil(total_units / chunk_count)
    while text_units(remaining, language) > target_units:
        if cjk:
            units = list(re.finditer(fr"[A-Za-z0-9{_CJK_RANGES}]", remaining))
            hard_end = units[target_units - 1].end()
            soft_start = units[max(1, math.floor(target_units * 0.6)) - 1].end()
            candidates = [
                index + 1
                for index, character in enumerate(remaining[soft_start:hard_end], soft_start)
                if character in "，、,；;：:"
            ]
            cut = candidates[-1] if candidates else hard_end
        else:
            words = list(re.finditer(r"\S+", remaining))
            cut = words[target_units - 1].end()
        chunk = remaining[:cut].strip()
        if not chunk:
            break
        chunks.append(chunk)
        remaining = remaining[cut:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks or [text.strip()]


def build_prosody_plan(
    text: str,
    raw_config: dict[str, Any] | None = None,
    language: str | None = None,
    profile: str | None = None,
) -> list[dict[str, Any]]:
    config = resolve_prosody_config(raw_config, language, profile)
    raw_plan: list[dict[str, Any]] = []
    buffer: list[str] = []

    def flush(kind: str, pause_s: float) -> None:
        segment = "".join(buffer).strip()
        buffer.clear()
        if segment:
            raw_plan.append({
                "text": segment,
                "boundary": kind,
                "pause_after_s": pause_s,
            })
        elif raw_plan:
            raw_plan[-1]["pause_after_s"] = max(
                float(raw_plan[-1]["pause_after_s"]), pause_s
            )
            raw_plan[-1]["boundary"] = kind

    for position, character in enumerate(text):
        if character in "\r\n":
            flush("beat", config["beat_pause_s"])
            continue
        buffer.append(character)
        if character in "。！？!?":
            flush("sentence", config["sentence_pause_s"])
        elif character == "." and _period_is_boundary(text, position):
            flush("sentence", config["sentence_pause_s"])
        elif character in "；;：" or (
            character == ":" and _colon_is_boundary(text, position)
        ):
            flush("clause", config["clause_pause_s"])
        elif character == "…":
            flush("clause", config["clause_pause_s"])
        elif character in "，,、":
            visible = text_units("".join(buffer), language)
            if visible >= config["min_comma_units"]:
                flush("comma", config["comma_pause_s"])
    flush("end", 0.0)

    plan: list[dict[str, Any]] = []
    maximum_units = max(1, round(config["max_phrase_units"]))
    for segment in raw_plan:
        chunks = _split_overlong(segment["text"], maximum_units, language)
        for index, chunk in enumerate(chunks):
            final_chunk = index == len(chunks) - 1
            plan.append({
                "text": chunk,
                "boundary": segment["boundary"] if final_chunk else "safety",
                "pause_after_s": (
                    float(segment["pause_after_s"])
                    if final_chunk
                    else config["safety_pause_s"]
                ),
                "units": text_units(chunk, language),
                "safety_split": not final_chunk,
            })
    if plan:
        plan[-1]["pause_after_s"] = 0.0
        plan[-1]["boundary"] = "end"
    return plan


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
            raise NarrationError(
                f"{beat_id}: beat or shot duration_s must be a positive number"
            ) from exc
        if duration <= 0:
            raise NarrationError(f"{beat_id}: duration_s must be positive")
        items.append({"id": beat_id, "text": text, "duration_s": duration})
    if not items:
        raise NarrationError("project has no narrated beats")
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
            "beat_map": [
                {
                    "id": item["id"],
                    "text": item["text"],
                    "units": text_units(item["text"], project.get("project", {}).get("language")),
                }
                for item in items
            ],
        }]
    return items


def preflight_project(project: dict[str, Any]) -> dict[str, Any]:
    pmeta = project.get("project", {})
    language = str(pmeta.get("language", "zh"))
    voice = project.get("audio", {}).get("voice", {})
    profile = str(voice.get("profile", "conversational"))
    rate = str(voice.get("rate", "+0%"))
    multiplier = parse_rate_multiplier(rate)
    voice_id = default_voice(language, voice.get("voice_id"))
    units_per_second = {
        "zh": 4.2,
        "ja": 5.0,
        "ko": 4.0,
        "en": 2.7,
        "fr": 2.6,
        "de": 2.4,
        "es": 2.8,
        "pt": 2.8,
        "it": 2.8,
    }.get(normalize_language(language), 2.6)
    reports: list[dict[str, Any]] = []
    warnings: list[str] = []
    for item in narration_items(project):
        plan = build_prosody_plan(
            item["text"], voice.get("prosody", {}), language, profile
        )
        units = sum(int(segment["units"]) for segment in plan)
        pause_s = sum(float(segment["pause_after_s"]) for segment in plan)
        estimated_s = units / max(0.1, units_per_second * multiplier) + pause_s
        utilization = estimated_s / max(0.1, float(item["duration_s"]))
        if utilization > 1.02:
            warnings.append(
                f"{item['id']}: estimated narration {estimated_s:.1f}s exceeds "
                f"the {item['duration_s']:.1f}s timeline; shorten copy or retime visuals"
            )
        elif utilization < 0.55:
            warnings.append(
                f"{item['id']}: narration fills only about {utilization:.0%} of the "
                "timeline; add copy or declare designed intro/outro holds"
            )
        reports.append({
            "id": item["id"],
            "timeline_duration_s": float(item["duration_s"]),
            "estimated_duration_s": estimated_s,
            "estimated_utilization": utilization,
            "units": units,
            "phrases": len(plan),
            "safety_splits": sum(bool(part["safety_split"]) for part in plan),
            "plan": plan,
        })
    return {
        "language": language,
        "voice_id": voice_id,
        "profile": profile,
        "rate": rate,
        "items": reports,
        "warnings": warnings,
    }
