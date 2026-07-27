#!/usr/bin/env python3
"""Resume, checkpoint, restore, report, and package collage-video projects."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

import studio
import production_contract


class OpsError(RuntimeError):
    pass


def history_root(root: Path) -> Path:
    return root / ".studio" / "history"


def checkpoint(root: Path, note: str = "", kind: str = "manual") -> Path:
    project = studio.load_project(root)
    state = studio.load_state(root)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = history_root(root) / stamp
    target = base
    suffix = 1
    while target.exists():
        target = Path(f"{base}-{suffix:02d}")
        suffix += 1
    target.mkdir(parents=True)
    shutil.copy2(studio.project_file(root), target / "project.json")
    studio.atomic_json(target / "state.json", state)
    studio.atomic_json(target / "checkpoint.json", {
        "id": target.name,
        "created_at": studio.now_iso(),
        "project_id": project["project"]["id"],
        "kind": kind,
        "note": note,
    })
    return target


def list_checkpoints(root: Path) -> list[dict[str, Any]]:
    hroot = history_root(root)
    if not hroot.exists():
        return []
    result = []
    for folder in sorted((p for p in hroot.iterdir() if p.is_dir()), reverse=True):
        meta_path = folder / "checkpoint.json"
        try:
            meta = studio.load_json(meta_path)
        except studio.StudioError:
            meta = {"id": folder.name, "created_at": "", "kind": "unknown", "note": ""}
        meta["path"] = str(folder)
        result.append(meta)
    return result


def resolve_checkpoint(root: Path, value: str) -> Path:
    checkpoints = list_checkpoints(root)
    if value.isdigit():
        index = int(value)
        if index < 1 or index > len(checkpoints):
            raise OpsError(f"checkpoint index out of range: {value}")
        return Path(checkpoints[index - 1]["path"])
    target = history_root(root) / value
    if not target.is_dir():
        raise OpsError(f"checkpoint does not exist: {value}")
    return target


def restore(root: Path, value: str, confirmed: bool) -> Path:
    if not confirmed:
        raise OpsError("restore replaces project.json and state.json; rerun with --yes")
    target = resolve_checkpoint(root, value)
    for name in ("project.json", "state.json"):
        if not (target / name).is_file():
            raise OpsError(f"checkpoint is incomplete: missing {name}")
    safety = checkpoint(root, note=f"automatic safety copy before restoring {target.name}",
                        kind="pre-restore")
    shutil.copy2(target / "project.json", studio.project_file(root))
    shutil.copy2(target / "state.json", studio.state_file(root))
    return safety


def stage_expected(root: Path, project: dict[str, Any], stage: str) -> set[str]:
    try:
        return {job["id"] for job in studio.build_jobs(root, project, stage)}
    except (KeyError, TypeError):
        return set()


def stage_missing(
    root: Path,
    project: dict[str, Any],
    state: dict[str, Any],
    stage: str,
) -> set[str]:
    try:
        jobs = studio.build_jobs(root, project, stage)
    except (KeyError, TypeError):
        return set()
    try:
        production = production_contract.profile_config(project)
    except production_contract.ProductionError:
        production = None
    strict = bool(production and production["strict_evidence"])
    return {
        job["id"] for job in jobs
        if not studio.artifact_current(state, job, strict=strict)
    }


def next_action(root: Path) -> dict[str, str]:
    project = studio.load_project(root)
    state = studio.load_state(root)
    creative = project.get("creative", {})
    script = "python scripts/studio.py"

    if not project.get("beats"):
        return {"stage": "story", "reason": "beat map is empty",
                "command": f"{script} validate \"{root}\" --stage story"}
    errors, _ = studio.validate_project(root, project, "story")
    if errors:
        return {"stage": "story", "reason": f"story validation has {len(errors)} error(s)",
                "command": f"{script} validate \"{root}\" --stage story"}
    if not studio.approval_valid(root, project, state, "story"):
        return {"stage": "story", "reason": "story approval is missing or stale",
                "command": f"{script} approve \"{root}\" --gate story --note \"user approved\""}
    if len(creative.get("candidate_themes", [])) != 3:
        return {"stage": "styles", "reason": "three comparable theme candidates are required",
                "command": "edit creative.candidate_themes in project.json"}
    styles = stage_missing(root, project, state, "styles")
    if styles:
        return {"stage": "styles", "reason": f"{len(styles)} style preview(s) missing/stale",
                "command": f"{script} jobs \"{root}\" --stage styles"}
    if not isinstance(creative.get("theme"), dict):
        return {"stage": "styles", "reason": "the user has not selected a theme",
                "command": f"{script} choose-theme \"{root}\" <theme-id>"}
    if not studio.approval_valid(root, project, state, "style"):
        return {"stage": "styles", "reason": "visual-direction approval is missing or stale",
                "command": f"{script} approve \"{root}\" --gate style --note \"user approved\""}

    mode = project["project"]["mode"]
    if mode != "footage":
        images = stage_missing(root, project, state, "images")
        if images:
            return {"stage": "images", "reason": f"{len(images)} keyframe(s) missing/stale",
                    "command": f"{script} jobs \"{root}\" --stage images"}
        layers = stage_missing(root, project, state, "layers")
        if layers:
            return {"stage": "layers",
                    "reason": f"{len(layers)} layer package(s) missing/stale",
                    "command": f"{script} jobs \"{root}\" --stage layers"}
    motion = stage_missing(root, project, state, "motion")
    if motion:
        return {"stage": "motion", "reason": f"{len(motion)} motion clip(s) missing/stale",
                "command": f"{script} jobs \"{root}\" --stage motion"}
    voice = stage_missing(root, project, state, "voice")
    if voice:
        return {"stage": "voice", "reason": f"{len(voice)} narration file(s) missing/stale",
                "command": f"{script} jobs \"{root}\" --stage voice"}
    music = stage_missing(root, project, state, "music")
    if music:
        return {"stage": "music", "reason": "music is configured but missing",
                "command": f"{script} jobs \"{root}\" --stage music"}
    final = root / "final.mp4"
    if not final.is_file():
        return {"stage": "render", "reason": "all registered assets are ready",
                "command": f"python scripts/render.py \"{root}\""}
    qa = root / "qa" / "report.json"
    if not qa.is_file() or qa.stat().st_mtime < final.stat().st_mtime:
        return {"stage": "qa", "reason": "final.mp4 has no current QA report",
                "command": f"python scripts/qa.py \"{root}\""}
    try:
        report = studio.load_json(qa)
    except studio.StudioError:
        report = {}
    if report.get("details", {}).get("qa_input_fingerprint") != studio.qa_input_fingerprint(
        root, project, state
    ):
        return {"stage": "qa", "reason": "QA evidence is stale for current inputs",
                "command": f"python scripts/qa.py \"{root}\""}
    if report.get("summary", {}).get("errors", 1):
        return {"stage": "qa", "reason": "the current QA report contains blocking errors",
                "command": f"python scripts/qa.py \"{root}\""}
    if not studio.approval_valid(root, project, state, "creative-qa"):
        return {"stage": "human-review",
                "reason": "technical QA passed; human visual/audio approval is missing or stale",
                "command": f"{script} approve \"{root}\" --gate creative-qa "
                           f"--note \"human review completed\""}
    return {"stage": "complete", "reason": "production, technical QA, and human approval gates are complete",
            "command": f"python scripts/project_ops.py report \"{root}\""}


def artifact_summary(root: Path, project: dict[str, Any],
                     state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for stage in ("styles", "images", "layers", "motion", "voice", "music"):
        expected = stage_expected(root, project, stage)
        missing = stage_missing(root, project, state, stage)
        rows.append({
            "stage": stage, "complete": len(expected) - len(missing),
            "expected": len(expected),
            "missing": sorted(missing),
        })
    return rows


def write_report(root: Path, output: Path | None = None) -> Path:
    project = studio.load_project(root)
    state = studio.load_state(root)
    action = next_action(root)
    rows = artifact_summary(root, project, state)
    checkpoints = list_checkpoints(root)
    qa_path = root / "qa" / "report.json"
    qa = studio.load_json(qa_path) if qa_path.is_file() else None
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    if output is None:
        output = root / "reports" / f"{stamp}-{project['project']['id']}.md"
    if output.exists():
        raise OpsError(f"report already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    theme = project.get("creative", {}).get("theme") or {}
    lines = [
        f"# {project['project']['title']} — Production Report",
        "",
        f"- Generated: {studio.now_iso()}",
        f"- Project: `{project['project']['id']}`",
        f"- Mode: `{project['project']['mode']}`",
        f"- Target: {project['project']['duration_s']}s · {project['project']['aspect']} · "
        f"{project['project'].get('fps', 30)} fps",
        f"- Story arc: `{project.get('creative', {}).get('arc') or 'unset'}`",
        f"- Selected theme: `{theme.get('id', 'unset')}`",
        "",
        "## Production status",
        "",
        "| Stage | Complete | Expected |",
        "|---|---:|---:|",
    ]
    lines.extend(f"| {row['stage']} | {row['complete']} | {row['expected']} |" for row in rows)
    lines.extend([
        "",
        "## Approval gates",
        "",
        "| Gate | Status |",
        "|---|---|",
    ])
    for gate in ("story", "style", "creative-qa"):
        status = "valid" if studio.approval_valid(root, project, state, gate) else "missing/stale"
        lines.append(f"| {gate} | {status} |")
    lines.extend([
        "",
        "## Current next action",
        "",
        f"- Stage: `{action['stage']}`",
        f"- Reason: {action['reason']}",
        f"- Command: `{action['command']}`",
        "",
        "## Checkpoints",
        "",
        f"{len(checkpoints)} checkpoint(s).",
    ])
    for item in checkpoints[:10]:
        lines.append(f"- `{item['id']}` · {item.get('kind', '')} · {item.get('note', '')}")
    lines.extend(["", "## Technical QA", ""])
    if qa:
        summary = qa.get("summary", {})
        lines.append(
            f"Errors: {summary.get('errors', 0)} · Warnings: {summary.get('warnings', 0)} · "
            f"Checks: {summary.get('checks', 0)}"
        )
        for check in qa.get("checks", []):
            lines.append(f"- [{check['level'].upper()}] {check['name']}: {check['message']}")
    else:
        lines.append("No QA report yet.")
    lines.extend([
        "",
        "## Creative review still requiring a human",
        "",
        "- Does the opening work without audio?",
        "- Do style, faces, products, labels, and display text remain stable?",
        "- Are captions readable without covering the focal subject?",
        "- Is narration intelligible and music appropriately ducked?",
        "- Does the final beat resolve the opening promise?",
        "",
    ])
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def package_project(root: Path, output: Path | None = None, include_media: bool = True) -> Path:
    project = studio.load_project(root)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    if output is None:
        output = root / "exports" / f"{project['project']['id']}-{stamp}.zip"
    if output.exists():
        raise OpsError(f"package already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    excluded_roots = {"render", ".studio", "exports"}
    if not include_media:
        excluded_roots.add("media")
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            rel = path.relative_to(root)
            if rel.parts and rel.parts[0] in excluded_roots:
                continue
            if path.resolve() == output.resolve():
                continue
            archive.write(path, rel.as_posix())
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    next_cmd = sub.add_parser("next", help="show the next unblocked production action")
    next_cmd.add_argument("project_dir")

    cp = sub.add_parser("checkpoint", help="save project and state without overwriting history")
    cp.add_argument("project_dir")
    cp.add_argument("--note", default="")

    history = sub.add_parser("history", help="list checkpoints newest first")
    history.add_argument("project_dir")

    restore_cmd = sub.add_parser("restore", help="restore a checkpoint after a safety copy")
    restore_cmd.add_argument("project_dir")
    restore_cmd.add_argument("checkpoint")
    restore_cmd.add_argument("--yes", action="store_true")

    report = sub.add_parser("report", help="write a project-grounded markdown report")
    report.add_argument("project_dir")
    report.add_argument("--output")

    package = sub.add_parser("package", help="create a portable project zip")
    package.add_argument("project_dir")
    package.add_argument("--output")
    package.add_argument("--without-media", action="store_true")

    args = parser.parse_args()
    root = Path(args.project_dir).resolve()
    try:
        if args.command == "next":
            action = next_action(root)
            print(json.dumps(action, ensure_ascii=False, indent=2))
        elif args.command == "checkpoint":
            path = checkpoint(root, args.note)
            print(f"checkpoint: {path.name}")
        elif args.command == "history":
            items = list_checkpoints(root)
            if not items:
                print("no checkpoints")
            for index, item in enumerate(items, 1):
                print(f"{index}. {item['id']} · {item.get('kind', '')} · {item.get('note', '')}")
        elif args.command == "restore":
            safety = restore(root, args.checkpoint, args.yes)
            print(f"restored {args.checkpoint}; safety checkpoint: {safety.name}")
        elif args.command == "report":
            output = Path(args.output) if args.output else None
            if output is not None and not output.is_absolute():
                output = root / output
            output = output.resolve() if output is not None else None
            print(f"report: {write_report(root, output)}")
        elif args.command == "package":
            output = Path(args.output) if args.output else None
            if output is not None and not output.is_absolute():
                output = root / output
            output = output.resolve() if output is not None else None
            print(f"package: {package_project(root, output, not args.without_media)}")
        return 0
    except (OpsError, studio.StudioError, OSError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
