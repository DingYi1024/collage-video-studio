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
import audio_qa
import asset_quality
import editorial_contract
import editorial_runtime
import narration
import project_ops
import production_contract
import provider_lifecycle
import proof_review
import qa
import registered_sources
import replicate_contract_test
import render
import studio
import voice_director


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
        "scripts/production_contract.py", "scripts/registered_sources.py",
        "scripts/editorial_runtime.py", "scripts/editorial_contract.py",
        "scripts/provider_lifecycle.py", "scripts/asset_quality.py",
        "scripts/proof_review.py",
        "scripts/voice_director.py", "scripts/audio_qa.py", "scripts/narration.py",
        "references/project-schema.md", "references/story-system.md",
        "references/visual-system.md", "references/operations.md",
        "references/acceptance.md", "references/replicate-backend.md",
        "references/production-profiles.md",
        "references/advanced-layer-primitives.md",
        "references/editorial-composition.md",
        "references/semantic-contracts.md",
        "references/provider-lifecycle.md",
        "references/quality-gates.md",
        "references/responsive-direction.md",
        "references/layered-motion.md", "references/directed-motion.md",
        "references/motion-audit.md", "references/articulated-rigs.md",
        "references/locomotion.md", "references/smooth-keyframes.md",
        "references/voice-continuity.md",
        "references/delivery-qa.md",
        "references/production-standard.md",
        "references/aspect-direction.md",
        "assets/backend_adapter.py",
        "assets/editorial-project-template.json",
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
    init_args = studio.parser().parse_args(["init", "unused-project"])
    if init_args.fps != 30:
        raise RuntimeError("new projects must default to 30 fps")


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
            "voice": {
                "description": "neutral documentary narrator",
                "speed": 1.0,
                "continuity_mode": "continuous",
                "qa": {
                    "min_sentence_pause_s": 0.16,
                    "max_phrase_gap_s": 0.50,
                    "max_unbroken_s": 5.50,
                    "min_boundary_coverage": 0.75,
                    "max_leading_s": 0.25,
                    "max_trailing_s": 0.60,
                    "max_silence_ratio": 0.25,
                    "min_lufs": -23.0,
                    "max_lufs": -13.0,
                    "max_true_peak_db": -0.5,
                },
            },
            "music_prompt": "minimal instrumental pulse, no vocals",
            "captions": True, "caption_style": "clean", "watermark": "",
            "mix": {"voice": 1.0, "music": 0.25},
            "delivery_qa": {
                "min_lufs": -22.0,
                "max_lufs": -11.0,
                "max_true_peak_db": -0.5,
            },
        },
        "motion": {
            "pipeline": "generative",
            "frame_conversion": "auto",
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
    stop_start = copy.deepcopy(directed)
    stop_start["quality"]["motion_audit"] = {
        "sample_fps": 30,
        "enforce_smooth_keyframes": True,
        "max_interior_stalls": 0,
    }
    stop_start["layers"][1]["loop"] = False
    stop_start["layers"][1].pop("motion_path", None)
    stop_start["layers"][1]["motion_intent"] = "continuous"
    stop_start["layers"][1]["easing"] = "smootherstep"
    stop_start["layers"][1]["keyframes"] = [
        {"t": 0, "x": -30},
        {"t": 0.25, "x": 0},
        {"t": 0.5, "x": 30},
    ]
    stop_start_audit = layer_compositor.audit_motion_continuity(stop_start)
    if (
        len(stop_start_audit["interior_stalls"]) != 1
        or not any("continuous translation stops" in item
                   for item in stop_start_audit["issues"])
    ):
        raise RuntimeError(
            f"smooth-keyframe guard did not catch stop-start easing: "
            f"{stop_start_audit}"
        )
    stop_start["layers"][1]["easing"] = "catmull-rom"
    smooth_audit = layer_compositor.audit_motion_continuity(stop_start)
    if smooth_audit["interior_stalls"] or smooth_audit["issues"]:
        raise RuntimeError(
            f"smooth-keyframe guard rejected continuous curve: {smooth_audit}"
        )
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
    footage["project"]["language"] = "unsupported-test-language"
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
    footage_errors, _ = studio.validate_project(root, footage, "story")
    if any("automatic Edge voice" in item for item in footage_errors):
        raise RuntimeError(
            f"preserved-source footage was blocked by unused TTS: {footage_errors}"
        )


def voice_continuity_contract(root: Path) -> None:
    import asyncio
    import math
    import struct
    import wave

    sample_rate = 48000
    english = narration.build_prosody_plan(
        "Dr. Smith used version 2.5 in the U.S. market. It worked.",
        language="en",
    )
    if len(english) != 2 or not english[0]["text"].endswith("market."):
        raise RuntimeError(f"abbreviation-aware narration split failed: {english}")
    url_plan = narration.build_prosody_plan(
        "Read https://example.com/path before continuing. Then decide.",
        language="en",
    )
    if len(url_plan) != 2 or "example.com/path" not in url_plan[0]["text"]:
        raise RuntimeError(f"URL-safe narration split failed: {url_plan}")
    unpunctuated = narration.build_prosody_plan(
        "这是一个没有任何标点但仍然必须自动加入安全呼吸点的很长中文句子用于验证通用分句能力",
        language="zh",
    )
    if len(unpunctuated) < 2 or not any(
        item["boundary"] == "safety" for item in unpunctuated
    ):
        raise RuntimeError(f"long-phrase safety split failed: {unpunctuated}")
    energetic = narration.build_prosody_plan(
        "This deliberately unpunctuated sentence contains enough words to require "
        "more than one safe phrase without producing a breathless run",
        language="en",
        profile="energetic",
    )
    if any(
        item["boundary"] == "safety" and item["pause_after_s"] < 0.16
        for item in energetic
    ):
        raise RuntimeError(f"energetic safety pause is below QA minimum: {energetic}")
    if narration.default_voice("en-US", "auto") != "en-US-JennyNeural":
        raise RuntimeError("language-aware voice selection failed")
    try:
        narration.default_voice("xx", "auto")
    except narration.NarrationError:
        pass
    else:
        raise RuntimeError("unknown language should require an explicit voice")

    plan = voice_director.build_prosody_plan(
        "第一句需要解释。\n第二句，继续推进。",
        {
            "comma_pause_s": 0.14,
            "sentence_pause_s": 0.28,
            "beat_pause_s": 0.32,
        },
    )
    if (
        len(plan) != 2
        or plan[0]["boundary"] != "beat"
        or abs(float(plan[0]["pause_after_s"]) - 0.32) > 1e-6
        or plan[-1]["pause_after_s"] != 0
    ):
        raise RuntimeError(f"prosody plan mismatch: {plan}")

    class FakeCommunicate:
        def __init__(self, text: str, **_: object) -> None:
            self.text = text

        async def save(self, path: str) -> None:
            duration = max(0.50, min(0.90, len(self.text) * 0.06))
            subprocess.run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i",
                f"sine=frequency=330:duration={duration:.3f}:sample_rate=48000",
                "-c:a", "libmp3lame", path,
            ], check=True)

    class FakeEdgeTts:
        Communicate = FakeCommunicate

    assembled_voice = root / "voice-prosody-assembly.wav"
    assembly_dir = root / "voice-prosody-parts"
    assembly_dir.mkdir(parents=True, exist_ok=True)
    assembly_plan = asyncio.run(voice_director.synthesize_with_prosody(
        edge_tts=FakeEdgeTts,
        text="第一句需要解释。\n第二句继续推进。",
        output=assembled_voice,
        temp_dir=assembly_dir,
        voice="test",
        rate="+0%",
        volume="+0%",
        pitch="+0Hz",
        prosody_config={"sentence_pause_s": 0.28, "beat_pause_s": 0.32},
    ))
    assembly_timing = assembled_voice.with_suffix(".timing.json")
    studio.atomic_json(assembly_timing, {
        "schema_version": 1,
        "artifact_id": "voice:main",
        "language": "zh",
        "text": "第一句需要解释。\n第二句继续推进。",
        "segments": assembly_plan,
    })
    assembly_report = audio_qa.audit_timeline([{
        "path": assembled_voice,
        "label": "voice:test-prosody-assembly",
        "timeline_start_s": 0,
        "timeline_duration_s": audio_qa.media_duration(assembled_voice),
        "text": "第一句需要解释。\n第二句继续推进。",
        "timing_path": assembly_timing,
    }], check_levels=False)
    if len(assembly_plan) != 2 or assembly_report["issues"]:
        raise RuntimeError(
            f"prosody assembly contract failed: "
            f"plan={assembly_plan} report={assembly_report}"
        )
    level_report = audio_qa.audit_timeline([{
        "path": assembled_voice,
        "label": "voice:test-low-level",
        "timeline_start_s": 0,
        "timeline_duration_s": audio_qa.media_duration(assembled_voice),
    }])
    if not any("voice loudness" in item for item in level_report["issues"]):
        raise RuntimeError(f"quiet voice level guard did not trigger: {level_report}")
    if not all(
        "start_s" in segment and "pause_end_s" in segment
        for segment in assembly_plan
    ):
        raise RuntimeError("synthesized prosody plan lacks timing metadata")
    caption_project = {
        "audio": {
            "captions": True,
            "voice": {"continuity_mode": "continuous"},
        }
    }
    caption_state = {
        "artifacts": {
            "voice:main": {
                "path": studio.portable_path(root, assembled_voice),
                "metadata": {
                    "timing_path": studio.portable_path(root, assembly_timing)
                },
            }
        }
    }
    cues = render.timing_caption_cues(root, caption_project, caption_state, [])
    if len(cues) != len(assembly_plan) or any(
        cue["end_s"] <= cue["start_s"] for cue in cues
    ):
        raise RuntimeError(f"timing-driven caption cues failed: {cues}")
    bad_voice = root / "voice-gap-contract.wav"
    segments = [
        ("tone", 0.35),
        ("silence", 0.80),
        ("tone", 0.35),
    ]
    with wave.open(str(bad_voice), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        frame_index = 0
        for kind, duration_s in segments:
            for _ in range(round(duration_s * sample_rate)):
                value = (
                    0
                    if kind == "silence"
                    else round(9000 * math.sin(2 * math.pi * 330 * frame_index / sample_rate))
                )
                handle.writeframesraw(struct.pack("<h", value))
                frame_index += 1
    report = audio_qa.audit_timeline([{
        "path": bad_voice,
        "label": "voice:test-gap",
        "timeline_start_s": 0,
        "timeline_duration_s": 1.5,
    }], check_levels=False)
    if not any("internal narration gap" in item for item in report["issues"]):
        raise RuntimeError(f"narration gap guard did not trigger: {report}")
    good_voice = root / "voice-continuous-contract.wav"
    shutil.copyfile(bad_voice, good_voice)
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i",
        "sine=frequency=330:duration=1.5:sample_rate=48000",
        "-c:a", "pcm_s16le", str(good_voice),
    ], check=True)
    good_report = audio_qa.audit_timeline([{
        "path": good_voice,
        "label": "voice:test-continuous",
        "timeline_start_s": 0,
        "timeline_duration_s": 1.5,
    }], check_levels=False)
    if good_report["issues"]:
        raise RuntimeError(f"continuous narration was rejected: {good_report}")
    breathless_voice = root / "voice-breathless-contract.wav"
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i",
        "sine=frequency=330:duration=7:sample_rate=48000",
        "-c:a", "pcm_s16le", str(breathless_voice),
    ], check=True)
    breathless_report = audio_qa.audit_timeline([{
        "path": breathless_voice,
        "label": "voice:test-breathless",
        "timeline_start_s": 0,
        "timeline_duration_s": 7,
        "text": "第一句话说明问题。第二句话给出答案。",
    }], check_levels=False)
    if (
        not any("full breathing pause" in item for item in breathless_report["issues"])
        or not any("longest unbroken narration" in item
                   for item in breathless_report["issues"])
    ):
        raise RuntimeError(
            f"breathless narration guards did not trigger: {breathless_report}"
        )
    cross_gap_report = audio_qa.audit_timeline([
        {
            "path": good_voice,
            "label": "voice:test-a",
            "timeline_start_s": 0,
            "timeline_duration_s": 2.05,
        },
        {
            "path": good_voice,
            "label": "voice:test-b",
            "timeline_start_s": 2.05,
            "timeline_duration_s": 1.5,
        },
    ], check_levels=False)
    if not any("voice:test-a -> voice:test-b" in item
               for item in cross_gap_report["issues"]):
        raise RuntimeError(
            f"cross-clip narration gap guard did not trigger: {cross_gap_report}"
        )


def delivery_contract(root: Path) -> None:
    delivery_root = root / "delivery-contract"
    delivery_root.mkdir(parents=True, exist_ok=True)
    invalid_project = sample_project(root)
    invalid_project["motion"]["frame_conversion"] = "repeat"
    invalid_project["audio"]["delivery_qa"]["max_lufs"] = 3
    invalid_project["beats"][0]["shots"][0]["designed_holds"] = [{
        "start_s": 0.45,
        "end_s": 0.2,
        "reason": "",
    }]
    validation_errors, _ = studio.validate_project(
        root,
        invalid_project,
        "story",
    )
    expected_validation_errors = {
        "motion.frame_conversion",
        "audio.delivery_qa.max_lufs",
        "designed_holds[1]",
        "reason is required",
    }
    for expected in expected_validation_errors:
        if not any(expected in item for item in validation_errors):
            raise RuntimeError(
                f"delivery configuration guard did not trigger for {expected}: "
                f"{validation_errors}"
            )
    valid_tail = {
        "designed_holds": [{
            "start_s": 0.4,
            "end_s": 0.5,
            "reason": "reading hold",
        }]
    }
    if not qa.declares_tail_hold(valid_tail, 0.4, 0.5):
        raise RuntimeError("declared shot-tail hold was not recognized")
    if qa.declares_tail_hold(
        {"designed_holds": [{"start_s": "bad", "end_s": 0.5}]},
        0.4,
        0.5,
    ):
        raise RuntimeError("malformed shot-tail hold was accepted")

    static_video = delivery_root / "static.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=navy:s=360x640:r=30:d=0.6",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(static_video),
    ], check=True)
    if not qa.detect_freezes(static_video, 0.12):
        raise RuntimeError("pipeline-wide static-frame guard did not trigger")

    low_rate = delivery_root / "low-rate.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=s=360x640:r=24:d=0.8",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(low_rate),
    ], check=True)
    normalized_dir = delivery_root / "normalized"
    normalized_dir.mkdir()
    normalized = render.normalize_shots(
        root,
        normalized_dir,
        [{
            "key": "motion:test",
            "path": studio.portable_path(root, low_rate),
            "duration_s": 0.8,
            "start_s": 0.0,
        }],
        360,
        640,
        30,
        0.0,
        "auto",
    )[0]
    normalized_probe = qa.probe(normalized)
    normalized_video = next(
        stream
        for stream in normalized_probe["streams"]
        if stream.get("codec_type") == "video"
    )
    if abs(qa.frame_rate(normalized_video.get("avg_frame_rate")) - 30) > 0.15:
        raise RuntimeError("auto frame interpolation did not produce 30 fps")
    if qa.detect_freezes(normalized, 0.12):
        raise RuntimeError("auto frame interpolation introduced a long freeze")

    timing = delivery_root / "timing.json"
    studio.atomic_json(timing, {
        "schema_version": 1,
        "segments": [{
            "text": "test",
            "boundary": "end",
            "pause_after_s": 0,
            "start_s": 0,
            "speech_end_s": 0.5,
            "pause_start_s": 0.5,
            "pause_end_s": 0.5,
        }],
    })
    audio = delivery_root / "voice.wav"
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "sine=frequency=330:duration=0.5:sample_rate=48000",
        "-c:a", "pcm_s16le", str(audio),
    ], check=True)
    _, _, metadata = job_runner.normalize_result(
        root,
        {"id": "voice:test", "kind": "speech"},
        {"path": audio, "metadata": {"timing_path": timing}},
    )
    if (
        metadata.get("timing_status") != "provided"
        or metadata.get("timing_path") != studio.portable_path(root, timing)
    ):
        raise RuntimeError(f"adapter timing metadata was not normalized: {metadata}")
    _, _, fallback = job_runner.normalize_result(
        root,
        {"id": "voice:fallback", "kind": "speech"},
        audio,
    )
    if fallback.get("timing_status") != "missing":
        raise RuntimeError(f"legacy speech fallback was not identified: {fallback}")
    try:
        job_runner.normalize_result(
            root,
            {"id": "voice:unsafe", "kind": "speech"},
            {"path": audio, "metadata": {"secret_token": "must-not-persist"}},
        )
    except job_runner.RunnerError:
        pass
    else:
        raise RuntimeError("unknown adapter metadata was accepted")
    try:
        job_runner.normalize_result(
            root,
            {"id": "voice:none", "kind": "speech"},
            None,
        )
    except job_runner.RunnerError as exc:
        if "filesystem path" not in str(exc):
            raise RuntimeError(f"adapter path failure was unclear: {exc}") from exc
    else:
        raise RuntimeError("adapter None result was accepted")


def production_primitives_contract(root: Path) -> None:
    from PIL import Image, ImageDraw

    contract_root = root / "production-primitives"
    contract_root.mkdir(parents=True, exist_ok=True)
    board = Image.new("RGBA", (160, 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(board)
    draw.polygon([(8, 108), (34, 20), (58, 108)], fill="#20242b")
    draw.ellipse((88, 24, 146, 104), fill="#d94b3d")
    board_path = contract_root / "board.png"
    board.save(board_path)
    spec_path = contract_root / "spec.json"
    studio.atomic_json(spec_path, {
        "canvas": [160, 240],
        "items": [
            {"id": "pose-a", "source_rect": [0, 0, 72, 120], "place": [20, 96]},
            {"id": "pose-b", "source_rect": [80, 0, 80, 120], "place": [40, 96]},
        ],
    })
    registration_path = registered_sources.build(
        board_path, spec_path, contract_root / "registered"
    )
    registration = studio.load_json(registration_path)
    if len(registration["members"]) != 2:
        raise RuntimeError("registered source builder did not emit both states")
    for name, color in (
        ("background.png", "#eee4cf"),
        ("strip.png", "#3d6b73"),
        ("motif.png", "#f1bd42"),
    ):
        image = Image.new("RGBA", (160, 240), (0, 0, 0, 0))
        brush = ImageDraw.Draw(image)
        if name == "background.png":
            brush.rectangle((0, 0, 159, 239), fill=color)
        elif name == "strip.png":
            brush.rectangle((0, 190, 75, 224), fill=color)
        else:
            brush.ellipse((72, 108, 88, 124), fill=color)
        image.save(contract_root / name)
    manifest_path = contract_root / "layers.json"
    studio.atomic_json(manifest_path, {
        "schema_version": 1,
        "canvas": {
            "width": 160, "height": 240, "fps": 24, "duration_s": 1.0,
            "oversample": 1, "motion_blur_samples": 1,
        },
        "quality": {"min_layers": 4, "min_animated_layers": 3},
        "registration": {"members": ["subject"]},
        "layers": [
            {
                "id": "background", "path": "background.png", "z": 0,
                "keyframes": [{"t": 0}, {"t": 1.0}],
            },
            {
                "id": "strip", "path": "strip.png", "z": 1,
                "looping_strip": {"axis": "x", "speed_px_s": -36},
                "keyframes": [{"t": 0}, {"t": 1.0}],
            },
            {
                "id": "subject", "path": "registered/pose-a.png", "z": 2,
                "pose_sequence": {
                    "states": [
                        {"id": "a", "path": "registered/pose-a.png", "at_s": 0},
                        {"id": "b", "path": "registered/pose-b.png", "at_s": 0.5},
                    ],
                    "playback": "once", "transition": "cut", "crossfade_s": 0,
                },
                "visibility": {
                    "initial": False,
                    "events": [{"at_s": 0.08, "visible": True, "fade_s": 0.14}],
                },
                "easing": "catmull-rom",
                "motion_intent": "continuous",
                "keyframes": [
                    {"t": 0, "x": -8, "y": 0},
                    {"t": 0.5, "x": 2, "y": -2},
                    {"t": 1.0, "x": 12, "y": 0},
                ],
            },
            {
                "id": "motifs", "path": "motif.png", "z": 3,
                "motif_field": {
                    "seed": 2026, "count": 5, "area": [10, 20, 140, 100],
                    "scale_range": [0.5, 1.0], "drift_px": [3, 5],
                    "stagger_s": 0.03,
                },
                "keyframes": [{"t": 0}, {"t": 1.0}],
            },
        ],
    })
    errors, _, stats = layer_compositor.validate_manifest(manifest_path)
    if errors or stats != {"layers": 4, "animated_layers": 3}:
        raise RuntimeError(
            f"production primitive manifest failed: errors={errors}, stats={stats}"
        )
    early = layer_compositor.render_frame(manifest_path, 0.0)
    late = layer_compositor.render_frame(manifest_path, 0.75)
    if early.tobytes() == late.tobytes():
        raise RuntimeError("pose/visibility/loop/motif primitives produced no change")
    output = layer_compositor.render_manifest(
        manifest_path, contract_root / "motion.mp4"
    )
    activity = qa.audit_motion_activity(output, "kinetic")
    if not activity["low_motion_ranges"] and activity["mean_activity"] <= 0:
        raise RuntimeError(f"motion activity audit returned invalid data: {activity}")

    project = {
        "production": {
            "profile": "draft",
            "attempt_limits": {"visual_source": 1},
        }
    }
    state: dict[str, object] = {"attempts": []}
    group, limit, used = production_contract.check_attempt_available(
        project, state, "image_generation"
    )
    if (group, limit, used) != ("visual_source", 1, 0):
        raise RuntimeError("attempt budget did not resolve correctly")
    production_contract.append_attempt(
        state,
        group="visual_source",
        job_id="image:test",
        fingerprint="sha256:test",
        attempt_number=1,
        started_at=studio.now_iso(),
    )
    try:
        production_contract.check_attempt_available(
            project, state, "image_generation"
        )
    except production_contract.ProductionError:
        pass
    else:
        raise RuntimeError("exact attempt budget did not block excess work")
    first_job = {"id": "image:test", "kind": "image_generation", "params": {"seed": 1}}
    changed_job = copy.deepcopy(first_job)
    changed_job["params"]["seed"] = 2
    state_fingerprint = {
        "artifacts": {
            "image:test": {
                "job_fingerprint": studio.job_digest(first_job)
            }
        }
    }
    if not studio.artifact_current(state_fingerprint, first_job):
        raise RuntimeError("current artifact fingerprint was rejected")
    if studio.artifact_current(state_fingerprint, changed_job):
        raise RuntimeError("changed job did not invalidate registered artifact")


def editorial_protocol_contract(root: Path) -> None:
    from PIL import Image, ImageDraw

    contract_root = root / "editorial-protocol"
    contract_root.mkdir(parents=True, exist_ok=True)
    project = {
        "project": {"language": "zh"},
        "audio": {
            "voice": {
                "profile": "conversational",
                "rate": "+0%",
                "continuity_mode": "continuous",
            }
        },
        "editorial_timing": {
            "intro_hold_s": 0.3,
            "outro_hold_s": 0.4,
            "measured_voice_s": {"claim": 2.6},
        },
        "delivery": {"fps": 30},
        "semantic_contracts": [{
            "id": "route-order",
            "kind": "topology",
            "claim": "The route proceeds from source to proof",
            "protected_features": ["source before proof"],
            "evidence": [{"kind": "manual", "ref": "approved storyboard"}],
        }],
        "beats": [{
            "id": "claim",
            "narration": "先展示来源，再解释过程，最后给出证据。",
            "duration_s": 3.2,
            "proof_moments": [{
                "id": "proof-visible",
                "offset_s": 2.4,
                "checks": ["evidence label is readable"],
            }],
        }, {
            "id": "result",
            "narration": "不同画幅仍保持同一个结论。",
            "duration_s": 2.8,
            "transition_intent": "compare",
        }],
    }
    compiled_project = editorial_contract.compile_project(project)
    timeline = compiled_project["compiled_editorial_timing"]
    if (
        timeline["beats"][0]["duration_source"] != "measured-voice"
        or compiled_project["beats"][1]["transition"]["mechanism"] != "matched-cut"
        or len(compiled_project["compiled_proof_moments"]) != 1
    ):
        raise RuntimeError("editorial project compiler contract failed")

    composition = {
        "canvas": {
            "width": 160, "height": 240, "fps": 30, "duration_s": 1,
            "background": "#171411",
        },
        "quality": {"min_layers": 3, "min_animated_layers": 2},
        "camera": {
            "keyframes": [
                {"t": 0, "x": 0, "y": 0},
                {"t": 1, "x": 3, "y": 0},
            ]
        },
        "director_plans": {
            "9:16": {
                "width": 160,
                "height": 240,
                "safe_zones": [
                    {"id": "title", "policy": "contain", "rect": [8, 8, 144, 40]}
                ],
                "node_overrides": {},
            }
        },
        "composition": {
            "id": "root",
            "type": "group",
            "children": [{
                "id": "paper",
                "type": "primitive",
                "z": 0,
                "depth": -0.2,
                "primitive": {
                    "kind": "rectangle", "x": 4, "y": 4,
                    "width": 152, "height": 232, "fill": "#25211c",
                },
                "keyframes": [{"t": 0}, {"t": 1, "rotation": 0.3}],
            }, {
                "id": "title",
                "type": "primitive",
                "z": 1,
                "depth": 0.2,
                "primitive": {
                    "kind": "text", "text": "PROOF", "x": 12, "y": 12,
                    "width": 136, "height": 35, "font_size": 26,
                    "min_font_size": 16, "bold": True,
                },
                "keyframes": [
                    {"t": 0, "x": -5, "opacity": 0},
                    {"t": 0.5, "x": 0, "opacity": 1},
                    {"t": 1, "x": 0, "opacity": 1},
                ],
            }],
        },
    }
    variants = editorial_contract.compile_director_variants(composition)
    manifest_path = contract_root / "composition.json"
    studio.atomic_json(manifest_path, variants["9:16"])
    gate = asset_quality.audit_composition_manifest(manifest_path)
    if not gate["passed"] or gate["stats"]["layers"] != 3:
        raise RuntimeError(f"editorial composition gate failed: {gate}")
    loaded = layer_compositor.load_manifest(manifest_path)
    if not loaded.get("compiled_editorial", {}).get("camera_coupled"):
        raise RuntimeError("camera-coupled recursive composition was not compiled")

    keyed = Image.new("RGB", (40, 40), (12, 210, 38))
    draw = ImageDraw.Draw(keyed)
    draw.ellipse((8, 6, 32, 34), fill=(210, 80, 45))
    keyed_path = contract_root / "keyed.png"
    cleaned_path = contract_root / "cleaned.png"
    keyed.save(keyed_path)
    key_report = asset_quality.remove_observed_key(
        keyed_path, cleaned_path, tolerance=38, softness=24
    )
    alpha_report = asset_quality.alpha_edge_audit(cleaned_path)
    if (
        key_report["removed_pixels"] <= 0
        or alpha_report["transparent_ratio"] <= 0
        or alpha_report["opaque_ratio"] <= 0
    ):
        raise RuntimeError("observed-key/alpha audit contract failed")

    lifecycle_state: dict[str, Any] = {"provider_events": []}
    reserved = provider_lifecycle.reserve(
        lifecycle_state,
        job_id="image:test",
        fingerprint="sha256:test",
        group="visual_source",
        at="2026-01-01T00:00:00Z",
    )
    provider_lifecycle.transition(
        lifecycle_state,
        attempt_id=reserved["attempt_id"],
        event="rejected",
        at="2026-01-01T00:00:01Z",
        reason="identity contract failed",
    )
    provider_lifecycle.transition(
        lifecycle_state,
        attempt_id=reserved["attempt_id"],
        event="recovery-requested",
        at="2026-01-01T00:00:02Z",
        reason="preserve protected features",
    )
    audit = provider_lifecycle.audit(lifecycle_state)
    if audit["events"] != 3 or audit["open_attempts"]:
        raise RuntimeError(f"provider lifecycle contract failed: {audit}")


def run_test(root: Path) -> None:
    static_contract()
    editorial_protocol_contract(root)
    layered_compositor_contract(root)
    production_primitives_contract(root)
    voice_continuity_contract(root)
    delivery_contract(root)
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
    voice_record = studio.load_state(root)["artifacts"].get("voice:main", {})
    if (
        voice_record.get("metadata", {}).get("timing_status") != "provided"
        or not voice_record.get("metadata", {}).get("timing_path")
    ):
        raise RuntimeError(
            f"structured speech adapter metadata was not registered: {voice_record}"
        )
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
