#!/usr/bin/env python3
"""Execute a JSONL media manifest through a pluggable Python adapter."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import studio


class RunnerError(RuntimeError):
    pass


def load_adapter(path: Path) -> ModuleType:
    if not path.is_file():
        raise RunnerError(f"adapter does not exist: {path}")
    spec = importlib.util.spec_from_file_location("collage_video_backend", path)
    if spec is None or spec.loader is None:
        raise RunnerError(f"cannot load adapter: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "execute", None)):
        raise RunnerError("adapter must define execute(job, project_dir) -> path")
    return module


def load_manifest(path: Path) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                job = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RunnerError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            for key in ("id", "kind", "prompt", "inputs", "params", "output"):
                if key not in job:
                    raise RunnerError(f"{path}:{line_number}: missing field {key!r}")
            jobs.append(job)
    return jobs


def register_result(root: Path, state: dict[str, Any], job: dict[str, Any],
                    output: Path) -> None:
    if not output.is_file() or output.stat().st_size <= 0:
        raise RunnerError(f"{job['id']}: adapter returned a missing or empty file: {output}")
    state["artifacts"][job["id"]] = {
        "path": studio.portable_path(root, output),
        "url": None,
        "job_id": job["id"],
        "updated_at": studio.now_iso(),
    }
    state["updated_at"] = studio.now_iso()
    studio.atomic_json(studio.state_file(root), state)


def execute_manifest(root: Path, manifest: Path, adapter_path: Path, *,
                     only: set[str] | None = None, limit: int | None = None,
                     retries: int = 1, dry_run: bool = False,
                     continue_on_error: bool = False) -> tuple[int, int, int]:
    jobs = load_manifest(manifest)
    state = studio.load_state(root)
    module = load_adapter(adapter_path) if not dry_run else None
    selected: list[dict[str, Any]] = []
    for job in jobs:
        if only and job["id"] not in only:
            continue
        if job["id"] in state["artifacts"]:
            continue
        selected.append(job)
    if limit is not None:
        selected = selected[:limit]

    completed = skipped = failed = 0
    skipped = len(jobs) - len(selected)
    for position, job in enumerate(selected, 1):
        print(f"[{position}/{len(selected)}] {job['id']} ({job['kind']})")
        if dry_run:
            print(f"  -> {job['output']['path']}")
            continue
        error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                assert module is not None
                raw = module.execute(job, root)
                output = Path(raw)
                if not output.is_absolute():
                    output = root / output
                register_result(root, state, job, output.resolve())
                print(f"  registered {studio.portable_path(root, output)}")
                completed += 1
                error = None
                break
            except Exception as exc:  # adapter exceptions must be surfaced with job context
                error = exc
                if attempt < retries:
                    delay = min(2 ** attempt, 8)
                    print(f"  attempt {attempt + 1} failed: {exc}; retrying in {delay}s")
                    time.sleep(delay)
        if error is not None:
            failed += 1
            print(f"  FAILED: {error}", file=sys.stderr)
            if not continue_on_error:
                break
    return completed, skipped, failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--stage", choices=sorted(studio.JOB_STAGES))
    source.add_argument("--manifest")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--only", help="comma-separated job ids")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()

    root = Path(args.project_dir).resolve()
    manifest = root / "jobs" / f"{args.stage}.jsonl" if args.stage else Path(args.manifest)
    if not manifest.is_absolute():
        manifest = root / manifest
    adapter = Path(args.adapter)
    if not adapter.is_absolute():
        adapter = Path.cwd() / adapter
    only = set(filter(None, args.only.split(","))) if args.only else None
    try:
        completed, skipped, failed = execute_manifest(
            root, manifest.resolve(), adapter.resolve(), only=only, limit=args.limit,
            retries=max(0, args.retries), dry_run=args.dry_run,
            continue_on_error=args.continue_on_error,
        )
    except (RunnerError, studio.StudioError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(f"summary: completed={completed}, skipped={skipped}, failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
