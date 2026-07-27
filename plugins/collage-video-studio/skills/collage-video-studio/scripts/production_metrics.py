#!/usr/bin/env python3
"""Append auditable production events and summarize provider, local, avoided, and elapsed work."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import production_contract
import studio


CATEGORIES = {
    "authoring",
    "provider",
    "local-derivative",
    "deterministic-check",
    "evidence-render",
    "video-render",
    "human-review",
}


class MetricsError(RuntimeError):
    pass


def record(
    root: Path,
    *,
    category: str,
    operation: str,
    duration_s: float,
    provider_calls: int = 0,
    local_derivatives: int = 0,
    avoided_calls: int = 0,
    status: str = "completed",
    artifact: Path | None = None,
) -> dict[str, Any]:
    if category not in CATEGORIES:
        raise MetricsError(f"unsupported category: {category}")
    if not operation.strip() or duration_s < 0:
        raise MetricsError("operation and non-negative duration_s are required")
    counts = (provider_calls, local_derivatives, avoided_calls)
    if any(value < 0 for value in counts):
        raise MetricsError("production counts cannot be negative")
    event = {
        "at": studio.now_iso(),
        "category": category,
        "operation": operation.strip(),
        "duration_s": round(float(duration_s), 6),
        "provider_calls": int(provider_calls),
        "local_derivatives": int(local_derivatives),
        "avoided_calls": int(avoided_calls),
        "status": status,
        "artifact": (
            {
                "path": studio.portable_path(root, artifact),
                "content_sha256": production_contract.file_digest(artifact),
            }
            if artifact is not None and artifact.is_file()
            else None
        ),
    }
    event["fingerprint"] = production_contract.canonical_digest(event)
    path = root / "reports" / "production-metrics.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return event


def summarize(root: Path) -> dict[str, Any]:
    path = root / "reports" / "production-metrics.jsonl"
    events: list[dict[str, Any]] = []
    if path.is_file():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise MetricsError(f"invalid metrics line {line_number}") from exc
            expected = production_contract.canonical_digest({
                key: value for key, value in event.items() if key != "fingerprint"
            })
            if expected != event.get("fingerprint"):
                raise MetricsError(f"metrics line {line_number} failed integrity")
            events.append(event)
    by_category: dict[str, dict[str, float | int]] = {}
    for event in events:
        bucket = by_category.setdefault(
            event["category"],
            {
                "events": 0,
                "duration_s": 0.0,
                "provider_calls": 0,
                "local_derivatives": 0,
                "avoided_calls": 0,
            },
        )
        bucket["events"] = int(bucket["events"]) + 1
        bucket["duration_s"] = round(
            float(bucket["duration_s"]) + float(event["duration_s"]), 6
        )
        for key in ("provider_calls", "local_derivatives", "avoided_calls"):
            bucket[key] = int(bucket[key]) + int(event[key])
    report = {
        "events": len(events),
        "by_category": by_category,
        "totals": {
            "duration_s": round(sum(float(item["duration_s"]) for item in events), 6),
            "provider_calls": sum(int(item["provider_calls"]) for item in events),
            "local_derivatives": sum(
                int(item["local_derivatives"]) for item in events
            ),
            "avoided_calls": sum(int(item["avoided_calls"]) for item in events),
        },
    }
    report["fingerprint"] = production_contract.canonical_digest(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("record")
    add.add_argument("project_dir", type=Path)
    add.add_argument("--category", choices=sorted(CATEGORIES), required=True)
    add.add_argument("--operation", required=True)
    add.add_argument("--duration-s", type=float, required=True)
    add.add_argument("--provider-calls", type=int, default=0)
    add.add_argument("--local-derivatives", type=int, default=0)
    add.add_argument("--avoided-calls", type=int, default=0)
    add.add_argument("--status", default="completed")
    add.add_argument("--artifact", type=Path)
    summary = sub.add_parser("summary")
    summary.add_argument("project_dir", type=Path)
    args = parser.parse_args()
    try:
        root = args.project_dir.resolve()
        if args.command == "record":
            event = record(
                root,
                category=args.category,
                operation=args.operation,
                duration_s=args.duration_s,
                provider_calls=args.provider_calls,
                local_derivatives=args.local_derivatives,
                avoided_calls=args.avoided_calls,
                status=args.status,
                artifact=args.artifact.resolve() if args.artifact else None,
            )
            print(event["fingerprint"])
        else:
            print(json.dumps(summarize(root), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, MetricsError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
