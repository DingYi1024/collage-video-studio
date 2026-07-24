#!/usr/bin/env python3
"""Run an offline end-to-end acceptance test without paid media services."""

from __future__ import annotations

import argparse
import ast
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import job_runner
import layer_compositor
import project_ops
import qa
import replicate_contract_test
import render
import studio


SCRIPT_DIR = Path(__file__).resolve().parent
MOCK_ADAPTER = SCRIPT_DIR / "mock_backend.py"
SKILL_ROOT = SCRIPT_DIR.parent


def static_contract() -> None:
    required = [
        "SKILL.md", "LICENSE", "requirements.txt", "agents/openai.yaml",
        "scripts/studio.py", "scripts/job_runner.py",
        "scripts/render.py", "scripts/qa.py", "scripts/project_ops.py",
        "scripts/package_skill.py", "scripts/replicate_backend.py",
        "scripts/replicate_contract_test.py",
        "scripts/layer_compositor.py",
        "references/project-schema.md", "references/story-system.md",
        "references/visual-system.md", "references/operations.md",
        "references/acceptance.md", "references/replicate-backend.md",
        "references/layered-motion.md",
        "assets/backend_adapter.py",
        "assets/replicate-backend.example.json",
    ]
    missing = [name for name in required if not (SKILL_ROOT / name).is_file()]
    if missing:
        raise RuntimeError(f"skill package is incomplete: {missing}")
    skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    if not skill_text.startswith("---\n") or "\nname: collage-video-studio\n" not in skill_text:
        raise RuntimeError("SKILL.md frontmatter/name contract failed")
    interface = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    if "$collage-video-studio" not in interface:
        raise RuntimeError("agents/openai.yaml default prompt does not invoke the skill")
    banned_terms = [
        "vox" + "-director", "alisa" + "0808", "atlas" + "cloud",
        "atlas" + " cloud", "stav " + "zilber", "rom" + "1trs", "higgs" + "field",
    ]
    banned = re.compile("|".join(re.escape(item) for item in banned_terms), re.IGNORECASE)
    for path in SKILL_ROOT.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix.lower() in {".md", ".py", ".yaml", ".json"}:
            text = path.read_text(encoding="utf-8")
            match = banned.search(text)
            if match:
                raise RuntimeError(f"upstream identity leaked into {path}: {match.group(0)}")
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def sample_project(root: Path) -> dict:
    themes = [
        {
            "id": "map-print", "medium": "screen-printed maps and paper buildings",
            "palette": "charcoal, coral, cream", "typography": "condensed civic signage",
            "texture": "coarse print on recycled stock",
            "composition": "map-first diagrams with one large focal block",
            "motion": "measured map reveals and stamped labels",
        },
        {
            "id": "street-copy", "medium": "photocopied street scenes and torn flyers",
            "palette": "black, white, acid orange", "typography": "hand-cut protest lettering",
            "texture": "copy grain and rough ripped edges",
            "composition": "dense diagonal street-level layers",
            "motion": "urgent tears, slides, and snap stamps",
        },
        {
            "id": "paper-lab", "medium": "clean paper models and diagram cutouts",
            "palette": "off-white, cobalt, temperature red",
            "typography": "precise geometric labels",
            "texture": "clean cardstock with subtle fibers",
            "composition": "large negative space and controlled comparisons",
            "motion": "calm unfolds, overlays, and parallax",
        },
    ]
    beats = [
        {
            "id": "b01", "purpose": "pose a visual puzzle",
            "narration": "The same city can contain two completely different temperatures.",
            "display_text": "ONE CITY. TWO CLIMATES.", "feel": "surprising",
            "shots": [
                {
                    "id": "s01", "duration_s": 0.5, "framing": "wide", "camera": "push",
                    "scene": "two neighboring streets split between shade and dark pavement",
                    "element_motion": "temperature labels stamp in; heat strips rise",
                    "show_display_text": True,
                },
                {
                    "id": "s02", "duration_s": 0.5, "framing": "detail", "camera": "pan",
                    "scene": "tree canopy beside black asphalt",
                    "element_motion": "leaf shadows unfold; a thermometer strip climbs",
                    "show_display_text": False,
                },
            ],
        },
        {
            "id": "b02", "purpose": "explain the mechanism",
            "narration": "Dark surfaces store sunlight while trees release shade and water.",
            "display_text": "SURFACES STORE HEAT", "feel": "clear",
            "shots": [
                {
                    "id": "s01", "duration_s": 0.5, "framing": "close", "camera": "tilt",
                    "scene": "a paper cross-section of road, soil, and tree roots",
                    "element_motion": "sun arrows fold down; heat blocks stack in the road",
                    "show_display_text": True,
                },
                {
                    "id": "s02", "duration_s": 0.5, "framing": "wide", "camera": "pull",
                    "scene": "a cool street expands into a neighborhood plan",
                    "element_motion": "tree crowns pop open; blue cooling zones spread",
                    "show_display_text": False,
                },
            ],
        },
    ]
    return {
        "schema_version": 1,
        "project": {
            "id": "offline-acceptance", "title": "Offline Acceptance",
            "mode": "topic", "topic": "Why cities feel hotter", "language": "en",
            "duration_s": 2.0, "aspect": "9:16", "fps": 24, "test_mode": True,
        },
        "source": {},
        "creative": {"arc": "question-answer", "theme": themes[0],
                     "candidate_themes": themes},
        "audio": {
            "voice": {"description": "neutral documentary narrator", "speed": 1.0},
            "music_prompt": "minimal instrumental pulse, no vocals",
            "captions": True, "caption_style": "clean", "watermark": "",
            "mix": {"voice": 1.0, "music": 0.25},
        },
        "beats": beats,
    }


def prepare_root(root: Path) -> None:
    for folder in ("jobs", "media/images", "media/motion", "media/audio", "render"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    studio.atomic_json(studio.project_file(root), sample_project(root))
    studio.atomic_json(studio.state_file(root),
                       {"version": 1, "artifacts": {}, "approvals": {},
                       "updated_at": studio.now_iso()})


def layered_compositor_contract(root: Path) -> None:
    pack = root / "layer-contract"
    pack.mkdir(parents=True, exist_ok=True)
    from PIL import Image, ImageDraw
    background = Image.new("RGBA", (160, 240), "#f2ead8")
    background.save(pack / "background.png")
    object_layer = Image.new("RGBA", (160, 240), (0, 0, 0, 0))
    ImageDraw.Draw(object_layer).rectangle((45, 90, 115, 160), fill="#e64b2e")
    object_layer.save(pack / "object.png")
    manifest = {
        "version": 1,
        "canvas": {"width": 160, "height": 240, "fps": 12, "duration_s": 0.5},
        "quality": {"min_layers": 2, "min_animated_layers": 1},
        "layers": [
            {
                "id": "background", "path": "background.png", "z": 0,
                "keyframes": [{"t": 0, "scale": 1}, {"t": 0.5, "scale": 1.02}],
            },
            {
                "id": "object", "path": "object.png", "z": 1,
                "keyframes": [{"t": 0, "x": -20}, {"t": 0.5, "x": 20}],
            },
        ],
    }
    manifest_path = pack / "layers.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    errors, warnings, stats = layer_compositor.validate_manifest(manifest_path)
    if errors or warnings or stats != {"layers": 2, "animated_layers": 2}:
        raise RuntimeError(
            f"layer validation mismatch: errors={errors} warnings={warnings} stats={stats}"
        )
    output = pack / "motion.mp4"
    layer_compositor.render_manifest(manifest_path, output)
    if not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError("layer compositor did not render motion")
    shutil.rmtree(pack)


def write_and_run_stage(root: Path, stage: str) -> None:
    project = studio.load_project(root)
    jobs = studio.build_jobs(root, project, stage)
    manifest = root / "jobs" / f"{stage}.jsonl"
    with manifest.open("w", encoding="utf-8", newline="\n") as handle:
        for job in jobs:
            handle.write(json.dumps(job, ensure_ascii=False, sort_keys=True) + "\n")
    completed, _, failed = job_runner.execute_manifest(
        root, manifest, MOCK_ADAPTER, retries=0
    )
    if failed or completed != len(jobs):
        raise RuntimeError(f"{stage}: completed={completed} expected={len(jobs)} failed={failed}")


def mode_contracts(root: Path) -> None:
    base = studio.load_project(root)
    state = studio.load_state(root)
    first_image = Path(next(
        record["path"] for key, record in state["artifacts"].items() if key.startswith("image:")
    ))
    photo = copy.deepcopy(base)
    photo["project"]["mode"] = "photo"
    photo["source"] = {
        "path": first_image.as_posix(), "subject": "product",
        "anchor_policy": "preserve silhouette, label spelling, and proportions",
    }
    photo_kinds = [studio.build_jobs(root, photo, stage)[0]["kind"]
                   for stage in ("styles", "images", "motion")]
    if photo_kinds != ["image_edit", "image_edit", "image_to_video"]:
        raise RuntimeError(f"photo routing mismatch: {photo_kinds}")

    footage = copy.deepcopy(base)
    footage["project"]["mode"] = "footage"
    footage["source"] = {"path": "final.mp4", "preserve_original_audio": True}
    cursor = 0.0
    for beat in footage["beats"]:
        span = sum(float(shot["duration_s"]) for shot in beat["shots"])
        beat["start_s"], beat["end_s"] = cursor, cursor + span
        cursor += span
    footage_kinds = [
        (studio.build_jobs(root, footage, stage)[0]["kind"]
         if studio.build_jobs(root, footage, stage) else "none")
        for stage in ("styles", "motion", "voice")
    ]
    if footage_kinds != ["video_edit", "video_edit", "none"]:
        raise RuntimeError(f"footage routing mismatch: {footage_kinds}")


def run_test(root: Path) -> None:
    static_contract()
    layered_compositor_contract(root)
    adapter_contract = root / "adapter-contract"
    replicate_contract_test.run_test(adapter_contract)
    shutil.rmtree(adapter_contract)
    prepare_root(root)
    errors, warnings = studio.validate_project(root, studio.load_project(root), "images")
    if errors or warnings:
        raise RuntimeError(f"unexpected validation result: errors={errors}, warnings={warnings}")
    studio.record_approval(root, "story", "offline acceptance")
    initial = project_ops.checkpoint(root, "initial approved project", "test")
    changed = studio.load_project(root)
    changed["beats"][0]["narration"] = "Temporary change for stale-approval test."
    studio.atomic_json(studio.project_file(root), changed)
    if studio.approval_valid(root, changed, studio.load_state(root), "story"):
        raise RuntimeError("story approval did not become stale after a story change")
    project_ops.restore(root, initial.name, confirmed=True)
    restored_project = studio.load_project(root)
    if restored_project["beats"][0]["narration"].startswith("Temporary"):
        raise RuntimeError("checkpoint restore did not recover project.json")
    if not studio.approval_valid(root, restored_project, studio.load_state(root), "story"):
        raise RuntimeError("checkpoint restore did not recover the valid story approval")
    write_and_run_stage(root, "styles")
    studio.record_approval(root, "style", "offline acceptance")
    for stage in ("images", "motion", "voice", "music"):
        write_and_run_stage(root, stage)
    render.render(root, root / "final.mp4")
    report = qa.run_qa(root, root / "final.mp4", 3)
    if report["summary"]["errors"]:
        raise RuntimeError(f"QA failed: {report['checks']}")
    studio.record_approval(root, "creative-qa", "offline acceptance")
    final = root / "final.mp4"
    stat = final.stat()
    os.utime(final, (stat.st_atime, max(0, stat.st_mtime - 2)))
    if studio.approval_valid(root, studio.load_project(root), studio.load_state(root),
                             "creative-qa"):
        raise RuntimeError("creative QA approval did not become stale after final changed")
    report = qa.run_qa(root, final, 3)
    if report["summary"]["errors"]:
        raise RuntimeError(f"QA rerun failed: {report['checks']}")
    studio.record_approval(root, "creative-qa", "offline acceptance rerun")
    mode_contracts(root)
    action = project_ops.next_action(root)
    if action["stage"] != "complete":
        raise RuntimeError(f"next-action routing mismatch: {action}")
    report_path = project_ops.write_report(root)
    package_path = project_ops.package_project(root)
    if not report_path.is_file() or not package_path.is_file():
        raise RuntimeError("report or package was not created")
    checkpoints = project_ops.list_checkpoints(root)
    if not checkpoints:
        raise RuntimeError("checkpoint was not created")
    print("PASS: production-adapter contract, topic pipeline, photo/footage routing, "
          "render, QA, checkpoint/restore, report, package")
    print(f"final: {root / 'final.mp4'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true", help="retain the temporary project")
    args = parser.parse_args()
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("ERROR: ffmpeg and ffprobe are required", file=sys.stderr)
        return 2
    temp = Path(tempfile.mkdtemp(prefix="collage-video-studio-selftest-"))
    try:
        run_test(temp)
        if args.keep:
            print(f"kept: {temp}")
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        print(f"artifacts retained for diagnosis: {temp}", file=sys.stderr)
        return 1
    finally:
        if not args.keep and (temp / "final.mp4").is_file():
            shutil.rmtree(temp)


if __name__ == "__main__":
    raise SystemExit(main())
