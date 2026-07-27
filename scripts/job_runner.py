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


METADATA_KEYS = {
    "timing_path",
    "timing_status",
    "provider",
    "model",
    "duration_s",
    "content_sha256",
}


def load_adapter(path: Path) -> ModuleType:
    if not path.is_file():
        raise RunnerError(f"adapter does not exist: {path}")
    spec = importlib.util.spec_from_file_location("collage_video_backend", path)
    if spec is None or spec.loader is None:
        raise RunnerError(f"cannot load adapter: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "execute", None)):
        raise RunnerError(
            "adapter must define execute(job, project_dir) -> path or result object"
        )
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


def normalize_result(
    root: Path,
    job: dict[str, Any],
    raw: Any,
) -> tuple[Path, str | None, dict[str, Any]]:
    if isinstance(raw, dict):
        if "path" not in raw:
            raise RunnerError(f"{job['id']}: adapter result object is missing path")
        path_value = raw["path"]
        url = str(raw["url"]) if raw.get("url") else None
        metadata_raw = raw.get("metadata", {})
        if not isinstance(metadata_raw, dict):
            raise RunnerError(f"{job['id']}: adapter metadata must be an object")
        unknown = sorted(set(metadata_raw) - METADATA_KEYS)
        if unknown:
            raise RunnerError(
                f"{job['id']}: unsupported adapter metadata keys: {unknown}"
            )
        metadata = dict(metadata_raw)
    else:
        path_value = raw
        url = None
        metadata = {}
    try:
        output = Path(path_value)
    except (TypeError, ValueError) as exc:
        raise RunnerError(
            f"{job['id']}: adapter result path must be a filesystem path"
        ) from exc
    if not output.is_absolute():
        output = root / output
    output = output.resolve()
    try:
        output.relative_to(root.resolve())
    except ValueError as exc:
        raise RunnerError(
            f"{job['id']}: adapter output must stay inside the project directory"
        ) from exc
    timing_value = metadata.get("timing_path")
    if timing_value:
        timing = Path(str(timing_value))
        if not timing.is_absolute():
            timing = root / timing
        timing = timing.resolve()
        try:
            timing.relative_to(root.resolve())
        except ValueError as exc:
            raise RunnerError(
                f"{job['id']}: timing_path must stay inside the project directory"
            ) from exc
        if not timing.is_file() or timing.stat().st_size <= 0:
            raise RunnerError(
                f"{job['id']}: timing_path is missing or empty: {timing}"
            )
        metadata["timing_path"] = studio.portable_path(root, timing)
        metadata["timing_status"] = "provided"
    elif job.get("kind") == "speech":
        metadata["timing_status"] = "missing"
    return output, url, metadata


def register_result(
    root: Path,
    state: dict[str, Any],
    job: dict[str, Any],
    output: Path,
    url: str | None,
    metadata: dict[str, Any],
) -> None:
    if not output.is_file() or output.stat().st_size <= 0:
        raise RunnerError(f"{job['id']}: adapter returned a missing or empty file: {output}")
    record = studio.register_artifact(
        root,
        job["id"],
        output,
        url=url,
        metadata=metadata or None,
    )
    state["artifacts"][job["id"]] = record
    state["updated_at"] = record["updated_at"]


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
                output, url, metadata = normalize_result(root, job, raw)
                register_result(root, state, job, output, url, metadata)
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
