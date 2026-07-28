#!/usr/bin/env python3
"""Reserve and register media created by a host-side provider tool."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

import production_contract
import provider_lifecycle
import studio


class ExternalMediaError(RuntimeError):
    pass


def _find_attempt_record(
    state: dict[str, Any],
    attempt: dict[str, Any],
) -> dict[str, Any]:
    matches = [
        item
        for item in state.get("attempts", [])
        if isinstance(item, dict)
        and item.get("job_id") == attempt.get("job_id")
        and item.get("job_fingerprint") == attempt.get("job_fingerprint")
        and item.get("status") == "running"
    ]
    if not matches:
        raise ExternalMediaError("matching running attempt ledger record is missing")
    return matches[-1]


def reserve(
    root: Path,
    *,
    artifact_id: str,
    provider: str,
    model: str,
    prompt: str,
) -> dict[str, Any]:
    root = root.resolve()
    if not artifact_id.startswith(("image:", "style:")):
        raise ExternalMediaError(
            "external visual artifacts must use image:* or style:* ids"
        )
    if not provider.strip() or not model.strip() or not prompt.strip():
        raise ExternalMediaError("provider, model, and prompt are required")
    project = studio.load_project(root)
    state = studio.load_state(root)
    job = {
        "id": artifact_id,
        "kind": "image_generation",
        "prompt": prompt.strip(),
        "provider": provider.strip(),
        "model": model.strip(),
    }
    fingerprint = production_contract.canonical_digest(job)
    group, _, used = production_contract.check_attempt_available(
        project, state, "image_generation", artifact_id
    )
    if group is None:
        raise ExternalMediaError("image generation has no production attempt group")
    started = studio.now_iso()
    ledger = production_contract.append_attempt(
        state,
        group=group,
        job_id=artifact_id,
        fingerprint=fingerprint,
        attempt_number=used + 1,
        started_at=started,
    )
    lifecycle = provider_lifecycle.reserve_with_budget(
        state,
        project,
        job_id=artifact_id,
        fingerprint=fingerprint,
        group=group,
        at=started,
    )
    state.setdefault("external_media", {})[str(lifecycle["attempt_id"])] = {
        "artifact_id": artifact_id,
        "provider": provider.strip(),
        "model": model.strip(),
        "prompt": prompt.strip(),
        "job_fingerprint": fingerprint,
    }
    state["updated_at"] = started
    studio.atomic_json(studio.state_file(root), state)
    return {
        "status": "reserved",
        "attempt_id": lifecycle["attempt_id"],
        "attempt_number": ledger["attempt_number"],
        "artifact_id": artifact_id,
        "job_fingerprint": fingerprint,
    }


def complete(
    root: Path,
    *,
    attempt_id: str,
    source: Path,
) -> dict[str, Any]:
    root = root.resolve()
    source = source.resolve()
    if not source.is_file() or source.stat().st_size <= 0:
        raise ExternalMediaError(f"completed provider output is missing: {source}")
    state = studio.load_state(root)
    attempts = provider_lifecycle.materialize(state)
    attempt = attempts.get(attempt_id)
    if not isinstance(attempt, dict) or attempt.get("status") != "running":
        raise ExternalMediaError("attempt is missing or no longer running")
    reservation = state.get("external_media", {}).get(attempt_id)
    if not isinstance(reservation, dict):
        raise ExternalMediaError("external media reservation metadata is missing")
    suffix = source.suffix.lower() or ".png"
    safe_id = str(reservation["artifact_id"]).replace(":", "-")
    destination = root / "media" / "sources" / f"{safe_id}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    metadata = {
        "provider": reservation["provider"],
        "model": reservation["model"],
        "provenance_class": "provider-generated",
        "source_artifact_ids": [],
        "production_ready": True,
        "placeholder": False,
        "job_fingerprint": reservation["job_fingerprint"],
    }
    record = studio.register_artifact(
        root,
        str(reservation["artifact_id"]),
        destination,
        metadata=metadata,
    )
    state = studio.load_state(root)
    attempt = provider_lifecycle.materialize(state).get(attempt_id)
    if not isinstance(attempt, dict):
        raise ExternalMediaError("attempt disappeared after artifact registration")
    ledger = _find_attempt_record(state, attempt)
    finished = studio.now_iso()
    ledger["status"] = "completed"
    ledger["finished_at"] = finished
    provider_lifecycle.transition(
        state,
        attempt_id=attempt_id,
        event="completed",
        at=finished,
        artifact={
            "path": record["path"],
            "content_sha256": record["content_sha256"],
            "provenance_class": "provider-generated",
        },
    )
    state["updated_at"] = finished
    studio.atomic_json(studio.state_file(root), state)
    return {
        "status": "completed",
        "attempt_id": attempt_id,
        "artifact_id": reservation["artifact_id"],
        "path": record["path"],
        "content_sha256": record["content_sha256"],
    }


def reject(
    root: Path,
    *,
    attempt_id: str,
    reason: str,
) -> dict[str, Any]:
    if not reason.strip():
        raise ExternalMediaError("rejection reason is required")
    root = root.resolve()
    state = studio.load_state(root)
    attempt = provider_lifecycle.materialize(state).get(attempt_id)
    if not isinstance(attempt, dict) or attempt.get("status") != "running":
        raise ExternalMediaError("attempt is missing or no longer running")
    ledger = _find_attempt_record(state, attempt)
    finished = studio.now_iso()
    ledger["status"] = "rejected"
    ledger["finished_at"] = finished
    ledger["error"] = reason.strip()
    provider_lifecycle.transition(
        state,
        attempt_id=attempt_id,
        event="rejected",
        at=finished,
        reason=reason.strip(),
    )
    state["updated_at"] = finished
    studio.atomic_json(studio.state_file(root), state)
    return {
        "status": "rejected",
        "attempt_id": attempt_id,
        "reason": reason.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    reserve_parser = sub.add_parser("reserve")
    reserve_parser.add_argument("project_dir", type=Path)
    reserve_parser.add_argument("artifact_id")
    reserve_parser.add_argument("--provider", required=True)
    reserve_parser.add_argument("--model", required=True)
    reserve_parser.add_argument("--prompt", required=True)
    complete_parser = sub.add_parser("complete")
    complete_parser.add_argument("project_dir", type=Path)
    complete_parser.add_argument("attempt_id")
    complete_parser.add_argument("source", type=Path)
    reject_parser = sub.add_parser("reject")
    reject_parser.add_argument("project_dir", type=Path)
    reject_parser.add_argument("attempt_id")
    reject_parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    try:
        if args.command == "reserve":
            result = reserve(
                args.project_dir,
                artifact_id=args.artifact_id,
                provider=args.provider,
                model=args.model,
                prompt=args.prompt,
            )
        elif args.command == "complete":
            result = complete(
                args.project_dir,
                attempt_id=args.attempt_id,
                source=args.source,
            )
        else:
            result = reject(
                args.project_dir,
                attempt_id=args.attempt_id,
                reason=args.reason,
            )
        print(result)
        return 0
    except (
        ExternalMediaError,
        studio.StudioError,
        production_contract.ProductionError,
        provider_lifecycle.LifecycleError,
        OSError,
        ValueError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
