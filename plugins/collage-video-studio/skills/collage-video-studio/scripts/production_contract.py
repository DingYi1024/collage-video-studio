#!/usr/bin/env python3
"""Stable production profiles, generation ledgers, and content fingerprints."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


PROFILES: dict[str, dict[str, Any]] = {
    "draft": {
        "min_layers": 4,
        "min_animated_layers": 2,
        "activity_profile": "editorial",
        "attempt_limits": {
            "visual_source": 8,
            "generative_motion": 3,
            "voice": 4,
            "music": 2,
        },
    },
    "balanced": {
        "min_layers": 6,
        "min_animated_layers": 3,
        "activity_profile": "kinetic",
        "attempt_limits": {
            "visual_source": 18,
            "generative_motion": 6,
            "voice": 8,
            "music": 3,
        },
    },
    "full-depth": {
        "min_layers": 8,
        "min_animated_layers": 4,
        "activity_profile": "kinetic",
        "attempt_limits": {
            "visual_source": 32,
            "generative_motion": 10,
            "voice": 12,
            "music": 5,
        },
    },
}

KIND_GROUPS = {
    "image_generation": "visual_source",
    "image_edit": "visual_source",
    "layer_package": "visual_source",
    "image_to_video": "generative_motion",
    "video_edit": "generative_motion",
    "speech": "voice",
    "music": "music",
}


class ProductionError(RuntimeError):
    pass


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def profile_config(project: dict[str, Any]) -> dict[str, Any] | None:
    """Return merged production settings, or None for legacy projects."""
    raw = project.get("production")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ProductionError("production must be an object")
    name = str(raw.get("profile", "balanced"))
    if name not in PROFILES:
        raise ProductionError(
            "production.profile must be draft, balanced, or full-depth"
        )
    base = PROFILES[name]
    limits = dict(base["attempt_limits"])
    override = raw.get("attempt_limits", {})
    if not isinstance(override, dict):
        raise ProductionError("production.attempt_limits must be an object")
    for group, value in override.items():
        if group not in limits:
            raise ProductionError(
                f"unsupported production attempt group: {group}"
            )
        try:
            parsed = int(value)
            if parsed < 0 or float(value) != parsed:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ProductionError(
                f"production.attempt_limits.{group} must be a non-negative integer"
            ) from exc
        limits[group] = parsed
    activity = str(raw.get("activity_profile", base["activity_profile"]))
    if activity not in {"calm", "editorial", "kinetic"}:
        raise ProductionError(
            "production.activity_profile must be calm, editorial, or kinetic"
        )
    return {
        "profile": name,
        "min_layers": int(base["min_layers"]),
        "min_animated_layers": int(base["min_animated_layers"]),
        "activity_profile": activity,
        "attempt_limits": limits,
        "strict_evidence": bool(raw.get("strict_evidence", True)),
    }


def job_fingerprint(job: dict[str, Any]) -> str:
    return canonical_digest(job)


def attempt_group(kind: str) -> str | None:
    return KIND_GROUPS.get(kind)


def attempt_count(state: dict[str, Any], group: str) -> int:
    return sum(
        1
        for item in state.get("attempts", [])
        if isinstance(item, dict) and item.get("group") == group
    )


def check_attempt_available(
    project: dict[str, Any],
    state: dict[str, Any],
    kind: str,
) -> tuple[str | None, int | None, int]:
    config = profile_config(project)
    group = attempt_group(kind)
    if config is None or group is None:
        return group, None, 0 if group is None else attempt_count(state, group)
    limit = int(config["attempt_limits"][group])
    used = attempt_count(state, group)
    if used >= limit:
        raise ProductionError(
            f"{group} attempt budget exhausted ({used}/{limit}); "
            "raise the explicit production.attempt_limits value only after review"
        )
    return group, limit, used


def append_attempt(
    state: dict[str, Any],
    *,
    group: str,
    job_id: str,
    fingerprint: str,
    attempt_number: int,
    started_at: str,
) -> dict[str, Any]:
    record = {
        "group": group,
        "job_id": job_id,
        "job_fingerprint": fingerprint,
        "attempt_number": attempt_number,
        "started_at": started_at,
        "status": "running",
    }
    state.setdefault("attempts", []).append(record)
    return record

