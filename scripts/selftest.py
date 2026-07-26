#!/usr/bin/env python3
"""Run an offline end-to-end acceptance test without paid media services."""

from __future__ import annotations

import argparse
import ast
import copy
import json
import os
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
        "scripts/layer_compositor.py", "scripts/sprite_sheet.py",
        "scripts/voice_director.py",
        "references/project-schema.md", "references/story-system.md",
        "references/visual-system.md", "references/operations.md",
        "references/acceptance.md", "references/replicate-backend.md",
        "references/layered-motion.md", "references/directed-motion.md",
        "references/motion-audit.md", "references/articulated-rigs.md",
        "references/locomotion.md",
        "references/production-standard.md",
        "references/aspect-direction.md",
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
    for path in SKILL_ROOT.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix.lower() in {".md", ".py", ".yaml", ".json"}:
            path.read_text(encoding="utf-8")
        if path.suffix == ".py":
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    if studio.choose_aspect("auto", "城市空间故事", "topic")[0] != "16:9":
        raise RuntimeError("auto aspect did not select landscape for spatial narrative")
    if studio.choose_aspect("auto", "抖音竖屏口播", "topic")[0] != "9:16":
        raise RuntimeError("auto aspect did not select portrait for mobile intent")
    if studio.choose_aspect("4:5", "anything", "topic")[0] != "4:5":
        raise RuntimeError("explicit aspect was not preserved")


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
        "motion": {
            "pipeline": "generative",
            "min_layers": 4,
            "min_animated_layers": 3,
            "transitions": {
                "enabled": True,
                "duration_s": 0.08,
                "types": ["wipeleft", "dissolve"],
            },
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
    object_alt = Image.new("RGBA", (160, 240), (0, 0, 0, 0))
    ImageDraw.Draw(object_alt).ellipse((52, 82, 108, 168), fill="#164e96")
    object_alt.save(pack / "object-alt.png")
    manifest = {
        "version": 1,
        "canvas": {
            "width": 160,
            "height": 240,
            "fps": 12,
            "duration_s": 0.5,
            "oversample": 2,
            "motion_blur_samples": 2,
            "shutter": 0.5,
        },
        "quality": {"min_layers": 2, "min_animated_layers": 1},
        "layers": [
            {
                "id": "background", "path": "background.png", "z": 0,
                "keyframes": [{"t": 0, "scale": 1}, {"t": 0.5, "scale": 1.02}],
            },
            {
                "id": "object", "path": "object.png", "z": 1,
                "easing": "catmull-rom", "loop": True, "phase_s": 0.07,
                "pivot": [80, 160],
                "sprites": [
                    {"t": 0, "path": "object.png"},
                    {"t": 0.25, "path": "object-alt.png"},
                ],
                "sprite_loop": True,
                "sprite_duration_s": 0.5,
                "sprite_crossfade_s": 0.04,
                "motion_path": {
                    "start_s": 0,
                    "end_s": 0.5,
                    "points": [[-20, 0], [-5, -16], [8, 16], [20, 0]],
                    "orient_to_path": True,
                    "rotation_offset": 0,
                    "easing": "linear",
                },
                "keyframes": [
                    {"t": 0, "x": -20},
                    {"t": 0.25, "x": 20},
                    {"t": 0.5, "x": -20},
                ],
            },
            {
                "id": "follower", "path": "object-alt.png", "z": 2,
                "motion_class": "hinged-part",
                "pivot": [80, 160],
                "follow": {
                    "parent": "object",
                    "lag_s": 0,
                    "inherit": {"x": 1, "y": 1},
                },
                "keyframes": [
                    {"t": 0, "rotation": -4},
                    {"t": 0.25, "rotation": 4},
                    {"t": 0.5, "rotation": -4},
                ],
            },
            {
                "id": "rig-child", "path": "object.png", "z": 3,
                "motion_class": "hinged-part",
                "pivot": [110, 160],
                "follow": {
                    "parent": "follower",
                    "space": "rig",
                    "lag_s": 0,
                    "inherit": {"x": 1, "y": 1, "rotation": 1},
                },
                "keyframes": [
                    {"t": 0, "rotation": -6},
                    {"t": 0.25, "rotation": 6},
                    {"t": 0.5, "rotation": -6},
                ],
            },
        ],
    }
    manifest_path = pack / "layers.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    errors, warnings, stats = layer_compositor.validate_manifest(manifest_path)
    if errors or warnings or stats != {"layers": 4, "animated_layers": 4}:
        raise RuntimeError(
            f"layer validation mismatch: errors={errors} warnings={warnings} stats={stats}"
        )
    directed = copy.deepcopy(manifest)
    directed["quality"]["directed_motion"] = True
    directed["direction"] = {
        "primary_action": "object slides and settles",
        "physical_cause": "a paper tab pushes it",
        "primary_layers": ["object"],
        "motion_density": "high",
        "phases": [
            {"name": "anticipation", "start_s": 0, "end_s": 0.1},
            {"name": "action", "start_s": 0.1, "end_s": 0.4},
            {"name": "settle", "start_s": 0.4, "end_s": 0.5},
        ],
        "designed_holds": [
            {"start_s": 0.45, "end_s": 0.5, "reason": "read the result"}
        ],
        "contacts": [
            {
                "layer": "background",
                "property": "rotation",
                "start_s": 0.1,
                "end_s": 0.5,
                "tolerance": 0,
            }
        ],
    }
    directed["rigs"] = [
        {
            "id": "test-arm-rig",
            "type": "articulated-paper",
            "root": "follower",
            "parts": ["follower", "rig-child"],
        }
    ]
    directed["layers"][1]["keyframes"][1]["ease"] = "back-out"
    directed_path = pack / "directed.json"
    directed_path.write_text(
        json.dumps(directed, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    directed_errors, directed_warnings, _ = layer_compositor.validate_manifest(
        directed_path
    )
    if directed_errors or directed_warnings:
        raise RuntimeError(
            f"directed motion contract failed: "
            f"errors={directed_errors} warnings={directed_warnings}"
        )
    audit = layer_compositor.audit_motion_continuity(directed)
    if (
        audit["issues"]
        or audit["followers"] != 2
        or audit["rig_followers"] != 1
    ):
        raise RuntimeError(f"motion continuity audit failed: {audit}")
    local_follower = layer_compositor.transform_at(directed["layers"][2], 0.2)
    resolved_follower = layer_compositor.resolved_transform_at(
        directed["layers"][2],
        {str(layer["id"]): layer for layer in directed["layers"]},
        0.2,
    )
    if abs(local_follower["x"] - resolved_follower["x"]) < 1:
        raise RuntimeError("follower did not inherit parent translation")
    local_rig_child = layer_compositor.transform_at(directed["layers"][3], 0.2)
    resolved_rig_child = layer_compositor.resolved_transform_at(
        directed["layers"][3],
        {str(layer["id"]): layer for layer in directed["layers"]},
        0.2,
    )
    if (
        abs(local_rig_child["x"] - resolved_rig_child["x"]) < 1
        and abs(local_rig_child["y"] - resolved_rig_child["y"]) < 1
    ):
        raise RuntimeError("rig child did not orbit with the parent pivot")
    walker = {
        "version": 1,
        "canvas": {
            "width": 160,
            "height": 240,
            "fps": 12,
            "duration_s": 0.5,
        },
        "quality": {
            "min_layers": 6,
            "min_animated_layers": 1,
            "directed_motion": True,
            "motion_audit": {"sample_fps": 30},
        },
        "direction": {
            "primary_action": "paper walker crosses with alternating planted feet",
            "physical_cause": "leg joints transfer weight into each planted foot",
            "primary_layers": ["walker-root"],
            "motion_density": "high",
            "phases": [
                {"name": "anticipation", "start_s": 0, "end_s": 0.1},
                {"name": "action", "start_s": 0.1, "end_s": 0.4},
                {"name": "settle", "start_s": 0.4, "end_s": 0.5},
            ],
            "contacts": [
                {
                    "layer": "left-foot", "property": "x",
                    "start_s": 0, "end_s": 0.1, "tolerance": 0,
                },
                {
                    "layer": "left-foot", "property": "y",
                    "start_s": 0, "end_s": 0.1, "tolerance": 0,
                },
                {
                    "layer": "right-foot", "property": "x",
                    "start_s": 0.2, "end_s": 0.3, "tolerance": 0,
                },
                {
                    "layer": "right-foot", "property": "y",
                    "start_s": 0.2, "end_s": 0.3, "tolerance": 0,
                },
                {
                    "layer": "left-foot", "property": "x",
                    "start_s": 0.4, "end_s": 0.5, "tolerance": 0,
                },
                {
                    "layer": "left-foot", "property": "y",
                    "start_s": 0.4, "end_s": 0.5, "tolerance": 0,
                },
            ],
        },
        "layers": [
            {
                "id": "walk-background", "path": "background.png", "z": 0,
                "keyframes": [{"t": 0}, {"t": 0.5}],
            },
            {
                "id": "walker-root", "path": "object.png", "z": 3,
                "pivot": [80, 100], "motion_class": "rigid-body",
                "keyframes": [
                    {"t": 0, "x": 0},
                    {"t": 0.1, "x": 0},
                    {"t": 0.2, "x": 20},
                    {"t": 0.3, "x": 20},
                    {"t": 0.4, "x": 40},
                    {"t": 0.5, "x": 40},
                ],
            },
            {
                "id": "left-leg", "path": "object-alt.png", "z": 4,
                "pivot": [80, 100], "motion_class": "hinged-part",
                "follow": {
                    "parent": "walker-root", "space": "rig", "lag_s": 0,
                    "inherit": {"x": 1, "y": 1, "rotation": 1},
                },
                "keyframes": [{"t": 0}, {"t": 0.5}],
            },
            {
                "id": "left-foot", "path": "object.png", "z": 5,
                "pivot": [80, 140], "motion_class": "hinged-part",
                "follow": {
                    "parent": "left-leg", "space": "rig", "lag_s": 0,
                    "inherit": {"x": 1, "y": 1, "rotation": 1},
                },
                "keyframes": [{"t": 0}, {"t": 0.5}],
            },
            {
                "id": "right-leg", "path": "object-alt.png", "z": 2,
                "pivot": [90, 100], "motion_class": "hinged-part",
                "follow": {
                    "parent": "walker-root", "space": "rig", "lag_s": 0,
                    "inherit": {"x": 1, "y": 1, "rotation": 1},
                },
                "keyframes": [{"t": 0}, {"t": 0.5}],
            },
            {
                "id": "right-foot", "path": "object.png", "z": 2,
                "pivot": [90, 140], "motion_class": "hinged-part",
                "follow": {
                    "parent": "right-leg", "space": "rig", "lag_s": 0,
                    "inherit": {"x": 1, "y": 1, "rotation": 1},
                },
                "keyframes": [{"t": 0}, {"t": 0.5}],
            },
        ],
        "rigs": [
            {
                "id": "test-walk-rig",
                "type": "articulated-paper",
                "root": "walker-root",
                "parts": [
                    "walker-root", "left-leg", "left-foot",
                    "right-leg", "right-foot",
                ],
                "locomotion": {
                    "root_axis": "x",
                    "feet": ["left-foot", "right-foot"],
                    "min_stride_px": 30,
                    "min_contact_s": 0.09,
                    "max_double_support_s": 0.02,
                    "max_plant_drift_px": 1,
                },
            }
        ],
    }
    walker_path = pack / "walker.json"
    walker_path.write_text(
        json.dumps(walker, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    walker_errors, walker_warnings, walker_stats = (
        layer_compositor.validate_manifest(walker_path)
    )
    if (
        walker_errors
        or walker_warnings
        or walker_stats != {"layers": 6, "animated_layers": 1}
    ):
        raise RuntimeError(
            f"locomotion contract failed: errors={walker_errors} "
            f"warnings={walker_warnings} stats={walker_stats}"
        )
    walker_audit = layer_compositor.audit_motion_continuity(walker)
    if (
        walker_audit["issues"]
        or walker_audit["locomotion_rigs"] != 1
        or walker_audit["plant_intervals"] != 3
    ):
        raise RuntimeError(f"locomotion audit failed: {walker_audit}")
    invalid_walk = copy.deepcopy(walker)
    invalid_walk["direction"]["contacts"][4]["layer"] = "right-foot"
    invalid_walk["direction"]["contacts"][5]["layer"] = "right-foot"
    invalid_walk_path = pack / "invalid-walker.json"
    invalid_walk_path.write_text(
        json.dumps(invalid_walk, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    invalid_walk_errors, _, _ = layer_compositor.validate_manifest(
        invalid_walk_path
    )
    if not any("must alternate feet" in item for item in invalid_walk_errors):
        raise RuntimeError("alternating planted-foot guard did not trigger")
    invalid_direction = copy.deepcopy(directed)
    invalid_direction["direction"].pop("physical_cause")
    invalid_direction_path = pack / "invalid-direction.json"
    invalid_direction_path.write_text(
        json.dumps(invalid_direction, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    direction_errors, _, _ = layer_compositor.validate_manifest(
        invalid_direction_path
    )
    if not any("direction.physical_cause is required" in item for item in direction_errors):
        raise RuntimeError("directed motion guard did not trigger")
    invalid_follow = copy.deepcopy(directed)
    invalid_follow["layers"][2]["follow"]["parent"] = "follower"
    invalid_follow_path = pack / "invalid-follow.json"
    invalid_follow_path.write_text(
        json.dumps(invalid_follow, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    follow_errors, _, _ = layer_compositor.validate_manifest(invalid_follow_path)
    if not any("cannot follow itself" in item for item in follow_errors):
        raise RuntimeError("follower cycle guard did not trigger")
    invalid_rig = copy.deepcopy(directed)
    invalid_rig["layers"][3]["follow"]["lag_s"] = 0.1
    invalid_rig_path = pack / "invalid-rig.json"
    invalid_rig_path.write_text(
        json.dumps(invalid_rig, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    rig_errors, _, _ = layer_compositor.validate_manifest(invalid_rig_path)
    if not any("cannot lag" in item for item in rig_errors):
        raise RuntimeError("rig joint separation guard did not trigger")
    disconnected_rig = copy.deepcopy(directed)
    disconnected_rig["rigs"][0]["root"] = "object"
    disconnected_rig_path = pack / "disconnected-rig.json"
    disconnected_rig_path.write_text(
        json.dumps(disconnected_rig, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    disconnected_errors, _, _ = layer_compositor.validate_manifest(
        disconnected_rig_path
    )
    if not any("root must be one of its parts" in item for item in disconnected_errors):
        raise RuntimeError("articulated rig connectivity guard did not trigger")
    drifting_contact = copy.deepcopy(directed)
    drifting_contact["direction"]["contacts"][0]["property"] = "scale"
    drifting_contact["direction"]["contacts"][0]["tolerance"] = 0
    drift_audit = layer_compositor.audit_motion_continuity(drifting_contact)
    if not any("drifts" in item for item in drift_audit["issues"]):
        raise RuntimeError("contact drift audit did not trigger")
    invalid = copy.deepcopy(manifest)
    invalid["layers"][1]["motion_class"] = "major-pose"
    invalid["layers"][1]["sprite_crossfade_s"] = 0.04
    invalid_path = pack / "invalid-major-pose.json"
    invalid_path.write_text(
        json.dumps(invalid, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    invalid_errors, _, _ = layer_compositor.validate_manifest(invalid_path)
    if not any("major-pose sprites cannot crossfade" in item for item in invalid_errors):
        raise RuntimeError("major-pose crossfade guard did not trigger")
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
    if not studio.approval_valid(
        root, studio.load_project(root), studio.load_state(root), "creative-qa"
    ):
        raise RuntimeError("creative QA approval did not survive a portable timestamp change")
    with final.open("ab") as handle:
        handle.write(b"\0")
    if studio.approval_valid(
        root, studio.load_project(root), studio.load_state(root), "creative-qa"
    ):
        raise RuntimeError("creative QA approval ignored changed final content")
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
