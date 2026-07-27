#!/usr/bin/env python3
"""Append-only provider-attempt lifecycle and recovery ledger."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import uuid
from pathlib import Path
from typing import Any, Callable


class LifecycleError(RuntimeError):
    pass


EVENTS = {
    "reserved", "completed", "failed", "rejected",
    "recovery-requested", "recovery-source", "superseded", "reused",
}
TERMINAL = {"completed", "failed", "rejected", "superseded", "reused"}
SIDE_EVENTS = {"recovery-requested", "recovery-source"}


def append_event(
    state: dict[str, Any],
    *,
    event: str,
    job_id: str,
    at: str,
    attempt_id: str | None = None,
    fingerprint: str | None = None,
    group: str | None = None,
    parent_attempt_id: str | None = None,
    reason: str | None = None,
    artifact: dict[str, Any] | None = None,
    quota_consumed: bool | None = None,
) -> dict[str, Any]:
    if event not in EVENTS:
        raise LifecycleError(f"unsupported lifecycle event {event!r}")
    if not str(job_id).strip() or not str(at).strip():
        raise LifecycleError("job_id and at are required")
    if event == "reserved" and not fingerprint:
        raise LifecycleError("reserved events require fingerprint")
    identifier = attempt_id or f"attempt-{uuid.uuid4().hex[:16]}"
    record: dict[str, Any] = {
        "sequence": len(state.setdefault("provider_events", [])) + 1,
        "event": event,
        "attempt_id": identifier,
        "job_id": job_id,
        "at": at,
    }
    for key, value in (
        ("job_fingerprint", fingerprint),
        ("group", group),
        ("parent_attempt_id", parent_attempt_id),
        ("reason", reason),
        ("artifact", copy.deepcopy(artifact) if artifact else None),
        ("quota_consumed", quota_consumed),
    ):
        if value is not None:
            record[key] = value
    state["provider_events"].append(record)
    return record


def reserve(
    state: dict[str, Any],
    *,
    job_id: str,
    fingerprint: str,
    group: str,
    at: str,
    parent_attempt_id: str | None = None,
    quota_consumed: bool = True,
) -> dict[str, Any]:
    return append_event(
        state,
        event="reserved",
        job_id=job_id,
        fingerprint=fingerprint,
        group=group,
        at=at,
        parent_attempt_id=parent_attempt_id,
        quota_consumed=quota_consumed,
    )


def transition(
    state: dict[str, Any],
    *,
    attempt_id: str,
    event: str,
    at: str,
    reason: str | None = None,
    artifact: dict[str, Any] | None = None,
    quota_consumed: bool | None = None,
) -> dict[str, Any]:
    if event == "reserved":
        raise LifecycleError("use reserve() for reserved events")
    current = materialize(state).get(attempt_id)
    if current is None:
        raise LifecycleError(f"unknown attempt_id {attempt_id}")
    if current["status"] in TERMINAL and event not in {
        *SIDE_EVENTS, "superseded", "reused",
    }:
        raise LifecycleError(
            f"{attempt_id} is already terminal ({current['status']})"
        )
    return append_event(
        state,
        event=event,
        attempt_id=attempt_id,
        job_id=current["job_id"],
        fingerprint=current.get("job_fingerprint"),
        group=current.get("group"),
        at=at,
        reason=reason,
        artifact=artifact,
        quota_consumed=quota_consumed,
    )


def materialize(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    attempts: dict[str, dict[str, Any]] = {}
    last_sequence = 0
    for event in state.get("provider_events", []):
        if not isinstance(event, dict):
            raise LifecycleError("provider_events must contain objects")
        sequence = int(event.get("sequence", 0))
        if sequence != last_sequence + 1:
            raise LifecycleError("provider event sequences must be contiguous")
        last_sequence = sequence
        attempt_id = str(event.get("attempt_id", ""))
        kind = str(event.get("event", ""))
        if kind not in EVENTS or not attempt_id:
            raise LifecycleError("invalid provider event")
        if kind == "reserved":
            if attempt_id in attempts:
                raise LifecycleError(f"attempt {attempt_id} reserved twice")
            attempts[attempt_id] = {
                "attempt_id": attempt_id,
                "job_id": event.get("job_id"),
                "job_fingerprint": event.get("job_fingerprint"),
                "group": event.get("group"),
                "status": "running",
                "reserved_at": event.get("at"),
                "history": [event],
            }
            continue
        if attempt_id not in attempts:
            raise LifecycleError(f"event references unreserved attempt {attempt_id}")
        attempt = attempts[attempt_id]
        if kind in SIDE_EVENTS:
            attempt.setdefault("side_events", []).append(event)
            attempt["history"].append(event)
            continue
        attempt["status"] = kind
        attempt["updated_at"] = event.get("at")
        if event.get("reason"):
            attempt["reason"] = event["reason"]
        if event.get("artifact"):
            attempt["artifact"] = event["artifact"]
        attempt["history"].append(event)
    return attempts


def audit(state: dict[str, Any]) -> dict[str, Any]:
    attempts = materialize(state)
    counts: dict[str, int] = {}
    for attempt in attempts.values():
        status = str(attempt["status"])
        counts[status] = counts.get(status, 0) + 1
    running = sorted(
        item["attempt_id"]
        for item in attempts.values()
        if item["status"] == "running"
    )
    quota_consumed = sum(
        bool(attempt.get("history", [{}])[0].get("quota_consumed", True))
        for attempt in attempts.values()
    )
    recoveries = sum(
        len(attempt.get("side_events", [])) for attempt in attempts.values()
    )
    return {
        "events": len(state.get("provider_events", [])),
        "attempts": len(attempts),
        "status_counts": counts,
        "open_attempts": running,
        "quota_consumed_attempts": quota_consumed,
        "recovery_events": recoveries,
        "passed": not running,
    }


def reserve_with_budget(
    state: dict[str, Any],
    project: dict[str, Any],
    *,
    job_id: str,
    fingerprint: str,
    group: str,
    at: str,
    parent_attempt_id: str | None = None,
    quota_consumed: bool = True,
) -> dict[str, Any]:
    """Reserve against the narrower human-approved cap; failures still count."""
    production = __import__("production_contract")
    config = production.profile_config(project)
    attempts = materialize(state)
    used = sum(
        item.get("group") == group
        and bool(item.get("history", [{}])[0].get("quota_consumed", True))
        for item in attempts.values()
    )
    if config is not None:
        limit = int(config["attempt_limits"].get(group, 0))
        if group == "visual_source":
            approved = config.get("approved_visual_attempt_cap")
            if approved is None:
                raise LifecycleError(
                    "visual reservation requires approved_visual_attempt_cap"
                )
            limit = int(approved)
        if quota_consumed and used >= limit:
            raise LifecycleError(
                f"{group} approved attempt cap exhausted ({used}/{limit})"
            )
    return reserve(
        state,
        job_id=job_id,
        fingerprint=fingerprint,
        group=group,
        at=at,
        parent_attempt_id=parent_attempt_id,
        quota_consumed=quota_consumed,
    )


def register_recovery_source(
    state: dict[str, Any],
    *,
    attempt_id: str,
    at: str,
    artifact: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    attempt = materialize(state).get(attempt_id)
    if attempt is None or attempt.get("status") != "rejected":
        raise LifecycleError("recovery source must refer to a rejected attempt")
    if not artifact.get("path") or not artifact.get("content_sha256"):
        raise LifecycleError("recovery source requires path and content_sha256")
    return transition(
        state,
        attempt_id=attempt_id,
        event="recovery-source",
        at=at,
        reason=reason,
        artifact={**copy.deepcopy(artifact), "lifecycle": "recovery-source"},
        quota_consumed=False,
    )


def update_file(
    path: Path,
    operation: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LifecycleError(f"cannot read state {path}: {exc}") from exc
    if not isinstance(state, dict):
        raise LifecycleError("state must be an object")
    record = operation(state)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    audit_command = sub.add_parser("audit")
    audit_command.add_argument("state")
    reserve_command = sub.add_parser("reserve")
    reserve_command.add_argument("state")
    reserve_command.add_argument("--job-id", required=True)
    reserve_command.add_argument("--fingerprint", required=True)
    reserve_command.add_argument("--group", required=True)
    event_command = sub.add_parser("event")
    event_command.add_argument("state")
    event_command.add_argument("--attempt-id", required=True)
    event_command.add_argument(
        "--event",
        required=True,
        choices=sorted(EVENTS - {"reserved"}),
    )
    event_command.add_argument("--reason")
    args = parser.parse_args()
    path = Path(args.state).resolve()
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        if args.command == "reserve":
            report = update_file(
                path,
                lambda state: reserve(
                    state,
                    job_id=args.job_id,
                    fingerprint=args.fingerprint,
                    group=args.group,
                    at=now,
                ),
            )
        elif args.command == "event":
            report = update_file(
                path,
                lambda state: transition(
                    state,
                    attempt_id=args.attempt_id,
                    event=args.event,
                    at=now,
                    reason=args.reason,
                ),
            )
        else:
            state = json.loads(path.read_text(encoding="utf-8"))
            report = audit(state)
    except (OSError, json.JSONDecodeError, LifecycleError) as exc:
        print(f"ERROR: {exc}")
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if args.command != "audit" or report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
