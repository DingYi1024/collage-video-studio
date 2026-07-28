#!/usr/bin/env python3
"""Compile registered layer packages into one project-owned Remotion film."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import production_contract
import studio


CANVAS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "3:4": (1080, 1440),
    "4:3": (1440, 1080),
}
RUNTIME_FILES = (
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    "vite.config.ts",
    "index.html",
)
TRANSITION_ROUTES = {
    "paper-wipe": "paper-swipe-left",
    "matched-cut": "ink-match",
    "camera-travel": "paper-swipe-left",
    "layer-build": "page-build",
    "punch-in": "page-punch",
    "timeline-slide": "paper-swipe-up",
    "map-travel": "paper-swipe-left",
    "chapter-turn": "page-turn",
}


class ProductionRemotionError(RuntimeError):
    pass


def action_runtime_fingerprint() -> str:
    workspace = Path(__file__).resolve().parent.parent / "workspace"
    return production_contract.canonical_digest({
        "package": studio.load_json(workspace / "package.json"),
        "production_film": production_contract.file_digest(
            workspace / "src" / "remotion" / "ProductionFilm.tsx"
        ),
        "collage_video": production_contract.file_digest(
            workspace / "src" / "remotion" / "CollageVideo.tsx"
        ),
        "motion": production_contract.file_digest(
            workspace / "src" / "lib" / "motion.ts"
        ),
    })


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _copy_runtime(root: Path) -> Path:
    source = Path(__file__).resolve().parent.parent / "workspace"
    target = root / "remotion-workspace"
    target.mkdir(parents=True, exist_ok=True)
    for name in RUNTIME_FILES:
        src = source / name
        if src.is_file():
            shutil.copy2(src, target / name)
    for dirname in ("src",):
        destination = target / dirname
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source / dirname, destination)
    shutil.copytree(
        source / "public",
        target / "public",
        dirs_exist_ok=True,
    )
    return target


def _stage_file(
    source: Path,
    public: Path,
    asset_dir: Path,
    *,
    stem: str,
) -> str:
    if not source.is_file() or source.stat().st_size <= 0:
        raise ProductionRemotionError(f"missing staged media: {source}")
    digest = production_contract.file_digest(source).split(":", 1)[1][:16]
    suffix = source.suffix.lower() or ".bin"
    destination = asset_dir / f"{stem}-{digest}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.is_file() or (
        production_contract.file_digest(destination)
        != production_contract.file_digest(source)
    ):
        shutil.copy2(source, destination)
    return destination.relative_to(public).as_posix()


def _normalize_role(value: Any) -> str:
    role = str(value or "").lower()
    if any(token in role for token in ("background", "rear", "far")):
        return "rear"
    if any(token in role for token in ("subject", "character", "person", "hero")):
        return "subject"
    if any(token in role for token in ("foreground", "front", "near")):
        return "front"
    return role or "mid"


def _node_from_layer(
    layer: dict[str, Any],
    manifest_path: Path,
    public: Path,
    asset_dir: Path,
) -> dict[str, Any]:
    identifier = str(layer.get("id", "layer"))
    node: dict[str, Any] = {
        "id": identifier,
        "type": "image",
        "role": _normalize_role(layer.get("role")),
        "z": float(layer.get("z", 0)),
        "depth": float(layer.get("depth", 0)),
        "keyframes": layer.get("keyframes", [{"t": 0}]),
    }
    if isinstance(layer.get("layout"), dict):
        node["layout"] = layer["layout"]
    raw_path = layer.get("path")
    if raw_path:
        source = studio.resolve_path(manifest_path.parent, str(raw_path)).resolve()
        node["path"] = _stage_file(
            source, public, asset_dir, stem=identifier.replace(":", "-")
        )
    elif layer.get("primitive"):
        node["type"] = "primitive"
        node["primitive"] = layer["primitive"]
    else:
        raise ProductionRemotionError(
            f"{manifest_path}: layer {identifier!r} has no path or primitive"
        )
    for key in (
        "motion_policy",
        "visibility",
        "looping_strip",
        "world",
        "motif_field",
    ):
        if key in layer:
            node[key] = layer[key]
    if isinstance(layer.get("children"), list):
        node["children"] = [
            _node_from_layer(child, manifest_path, public, asset_dir)
            for child in layer["children"]
            if isinstance(child, dict)
        ]
    if isinstance(layer.get("pose_sequence"), dict):
        node["pose_sequence"] = json.loads(json.dumps(layer["pose_sequence"]))
    if node.get("pose_sequence"):
        for state in node["pose_sequence"].get("states", []):
            source = studio.resolve_path(
                manifest_path.parent, str(state.get("path", ""))
            ).resolve()
            state["path"] = _stage_file(
                source, public, asset_dir, stem=f"{identifier}-{state.get('id', 'pose')}"
            )
    return node


def _node_from_composition(
    node: dict[str, Any],
    manifest_path: Path,
    public: Path,
    asset_dir: Path,
) -> dict[str, Any]:
    compiled = json.loads(json.dumps(node))
    if compiled.get("type") == "image" and compiled.get("path"):
        source = studio.resolve_path(
            manifest_path.parent, str(compiled["path"])
        ).resolve()
        compiled["path"] = _stage_file(
            source,
            public,
            asset_dir,
            stem=str(compiled.get("id", "node")).replace(":", "-"),
        )
    if isinstance(compiled.get("pose_sequence"), dict):
        for state in compiled["pose_sequence"].get("states", []):
            source = studio.resolve_path(
                manifest_path.parent, str(state.get("path", ""))
            ).resolve()
            state["path"] = _stage_file(
                source,
                public,
                asset_dir,
                stem=f"{compiled.get('id', 'node')}-{state.get('id', 'pose')}",
            )
    compiled["children"] = [
        _node_from_composition(child, manifest_path, public, asset_dir)
        for child in compiled.get("children", [])
        if isinstance(child, dict)
    ]
    return compiled


def _director_plans(
    manifest: dict[str, Any],
    aspect: str,
    width: int,
    height: int,
) -> dict[str, Any]:
    plans = manifest.get("director_plans")
    if isinstance(plans, dict) and isinstance(plans.get(aspect), dict):
        return plans
    return {aspect: {"width": width, "height": height, "node_overrides": {}}}


def _compile_scene(
    root: Path,
    public: Path,
    asset_dir: Path,
    project: dict[str, Any],
    state: dict[str, Any],
    beat: dict[str, Any],
    shot: dict[str, Any],
    beat_index: int,
    shot_index: int,
) -> dict[str, Any]:
    artifact_id = studio.artifact_key("layers", beat, shot)
    record = state.get("artifacts", {}).get(artifact_id)
    if not isinstance(record, dict):
        raise ProductionRemotionError(f"missing registered layer package: {artifact_id}")
    manifest_path = studio.resolve_path(root, str(record.get("path", ""))).resolve()
    manifest = studio.load_json(manifest_path)
    aspect = str(project["project"]["aspect"])
    width, height = CANVAS[aspect]
    fps = int(project["project"].get("fps", 30))
    duration_s = (
        int(shot["duration_frames"]) / fps
        if shot.get("duration_frames") is not None
        else float(shot["duration_s"])
    )
    children = [
        _node_from_layer(layer, manifest_path, public, asset_dir)
        for layer in manifest.get("layers", [])
        if isinstance(layer, dict)
    ]
    children.sort(key=lambda item: float(item.get("z", 0)))
    composition = manifest.get("composition")
    if isinstance(composition, dict):
        composition = _node_from_composition(
            composition, manifest_path, public, asset_dir
        )
    else:
        composition = {
            "id": f"scene-{beat.get('id')}-{shot.get('id')}",
            "type": "group",
            "children": children,
        }
    scene_manifest = {
        "canvas": {
            "width": width,
            "height": height,
            "fps": fps,
            "duration_s": duration_s,
            "background": manifest.get("canvas", {}).get(
                "background",
                project.get("creative", {}).get("theme", {}).get(
                    "background", "#171411"
                ),
            ),
        },
        "camera": manifest.get("camera", {"keyframes": [{"t": 0}, {"t": duration_s}]}),
        "director_plans": _director_plans(manifest, aspect, width, height),
        "edit_points": manifest.get("edit_points", []),
        "events": manifest.get("events", []),
        "proof_moments": manifest.get("proof_moments", []),
        "scene_transitions": manifest.get("scene_transitions", []),
        "composition": composition,
    }
    transition = beat.get("transition", {}) if shot_index == 0 else {}
    if not isinstance(transition, dict):
        transition = {}
    mechanism = (
        transition.get("mechanism")
        or beat.get("transition_mechanism")
        or shot.get("transition_mechanism")
        or "matched-cut"
    )
    intent = (
        transition.get("intent")
        or beat.get("transition_intent")
        or shot.get("transition_intent")
        or "advance the argument"
    )
    return {
        "id": f"{beat.get('id', beat_index + 1)}-{shot.get('id', shot_index + 1)}",
        "duration_s": duration_s,
        "aspect": aspect,
        "manifest": scene_manifest,
        "source_artifact_id": artifact_id,
        "transition": {
            "intent": str(intent),
            "mechanism": TRANSITION_ROUTES.get(str(mechanism), str(mechanism)),
            "duration_s": float(
                transition.get("duration_s")
                or beat.get("transition_duration_s")
                or 0.34
            ),
        },
    }


def _timing_cues(root: Path, voice: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(voice, dict):
        return []
    metadata = voice.get("metadata", {})
    if not isinstance(metadata, dict) or not metadata.get("timing_path"):
        return []
    timing_path = studio.resolve_path(root, str(metadata["timing_path"])).resolve()
    timing = studio.load_json(timing_path)
    cues: list[dict[str, Any]] = []
    for index, segment in enumerate(timing.get("segments", []), 1):
        if not isinstance(segment, dict) or not str(segment.get("text", "")).strip():
            continue
        start = float(segment.get("start_s", 0))
        end = float(segment.get("speech_end_s", segment.get("end_s", start)))
        if end <= start:
            continue
        cues.append({
            "id": f"cue-{index:03d}",
            "text": str(segment["text"]).strip(),
            "start_s": start,
            "end_s": end,
        })
    return cues


def compile_film(root: Path) -> tuple[Path, dict[str, Any]]:
    root = root.resolve()
    project = studio.load_project(root)
    state = studio.load_state(root)
    workspace = _copy_runtime(root)
    public = workspace / "public"
    project_id = str(project["project"]["id"])
    asset_dir = public / "project" / project_id / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    scenes: list[dict[str, Any]] = []
    for beat_index, beat in enumerate(project.get("beats", [])):
        for shot_index, shot in enumerate(beat.get("shots", [])):
            scenes.append(
                _compile_scene(
                    root,
                    public,
                    asset_dir,
                    project,
                    state,
                    beat,
                    shot,
                    beat_index,
                    shot_index,
                )
            )
    if not scenes:
        raise ProductionRemotionError("production film has no scenes")
    aspect = str(project["project"]["aspect"])
    width, height = CANVAS[aspect]
    fps = int(project["project"].get("fps", 30))
    artifacts = state.get("artifacts", {})
    voice = artifacts.get("voice:main")
    music = artifacts.get("music:main")
    audio: dict[str, Any] = {}
    if isinstance(voice, dict):
        voice_path = studio.resolve_path(root, str(voice.get("path", ""))).resolve()
        audio["narration"] = {
            "path": _stage_file(voice_path, public, asset_dir, stem="narration"),
            "volume": _number(
                project.get("audio", {}).get("voice", {}).get("mix_volume", 1),
                1,
            ),
        }
    if isinstance(music, dict):
        music_path = studio.resolve_path(root, str(music.get("path", ""))).resolve()
        audio["music"] = {
            "path": _stage_file(music_path, public, asset_dir, stem="music"),
            "volume": _number(
                project.get("audio", {}).get("music_volume", 0.16), 0.16
            ),
            "loop": True,
        }
    total = sum(float(scene["duration_s"]) for scene in scenes)
    film = {
        "film": {
            "canvas": {
                "width": width,
                "height": height,
                "fps": fps,
                "duration_s": total,
                "background": "#171411",
            },
            "scenes": scenes,
            "subtitles": _timing_cues(root, voice),
            "audio": audio,
            "style": project.get("creative", {}).get("theme", {}).get(
                "film_style", {}
            ),
        }
    }
    props_path = public / "production.json"
    studio.atomic_json(props_path, film)
    visual = json.loads(json.dumps(film))
    visual["film"]["subtitles"] = []
    visual["film"]["audio"] = {}
    studio.atomic_json(public / "production-visual.json", visual)
    return workspace, film


def _run(command: list[str], cwd: Path) -> None:
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except FileNotFoundError as exc:
        raise ProductionRemotionError(f"command not found: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise ProductionRemotionError(
            f"Remotion command failed ({exc.returncode})"
        ) from exc


def _ensure_dependencies(workspace: Path) -> Path:
    binary = workspace / "node_modules" / ".bin" / (
        "remotion.cmd" if os.name == "nt" else "remotion"
    )
    if binary.is_file():
        return binary
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise ProductionRemotionError("Node.js/npm is required for Remotion rendering")
    _run([npm, "ci", "--no-audit", "--no-fund"], workspace)
    if not binary.is_file():
        raise ProductionRemotionError("Remotion dependency install completed without CLI")
    return binary


def _render_props(
    binary: Path,
    workspace: Path,
    props: str,
    output: Path,
    *,
    concurrency: int,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            str(binary),
            "render",
            "src/remotion/index.ts",
            "ProductionFilm",
            str(output),
            f"--props=public/{props}",
            "--codec=h264",
            "--crf=18",
            "--pixel-format=yuv420p",
            "--color-space=bt709",
            f"--concurrency={max(1, concurrency)}",
        ],
        workspace,
    )
    if not output.is_file() or output.stat().st_size <= 0:
        raise ProductionRemotionError(f"Remotion produced no output: {output}")


def render_action_sample(
    root: Path,
    manifest: Path,
    output: Path,
) -> dict[str, Any]:
    """Render a 3–5 second sample through the same runtime as the final film."""
    root = root.resolve()
    manifest = manifest.resolve()
    workspace, film = compile_film(root)
    state = studio.load_state(root)
    artifact_id = next(
        (
            key
            for key, record in state.get("artifacts", {}).items()
            if key.startswith("layers:")
            and isinstance(record, dict)
            and studio.resolve_path(root, str(record.get("path", ""))).resolve()
            == manifest
        ),
        None,
    )
    if not artifact_id:
        raise ProductionRemotionError(
            "action proof manifest must be a registered layers:* artifact"
        )
    scene = next(
        (
            item
            for item in film["film"]["scenes"]
            if item.get("source_artifact_id") == artifact_id
        ),
        None,
    )
    if not isinstance(scene, dict):
        raise ProductionRemotionError("registered action-proof scene was not compiled")
    duration = min(5.0, float(scene["duration_s"]))
    if duration < 3:
        raise ProductionRemotionError(
            "action-proof scene must be at least 3 seconds"
        )
    scene["duration_s"] = duration
    scene["manifest"]["canvas"]["duration_s"] = duration
    props = {
        "film": {
            **film["film"],
            "duration_s": duration,
            "scenes": [scene],
            "subtitles": [],
            "audio": {},
        }
    }
    props["film"]["canvas"]["duration_s"] = duration
    studio.atomic_json(workspace / "public" / "production-action.json", props)
    binary = _ensure_dependencies(workspace)
    _render_props(
        binary,
        workspace,
        "production-action.json",
        output.resolve(),
        concurrency=min(4, max(1, os.cpu_count() or 1)),
    )
    return {
        "duration_s": duration,
        "artifact_id": artifact_id,
        "engine": "remotion",
        "composition": "ProductionFilm",
        "runtime_fingerprint": action_runtime_fingerprint(),
    }


def render(root: Path, output: Path) -> Path:
    root = root.resolve()
    output = output.resolve()
    workspace, film = compile_film(root)
    binary = _ensure_dependencies(workspace)
    concurrency = min(4, max(1, os.cpu_count() or 1))
    subtitle_free = root / "render-cache" / "subtitle-free-master.mp4"
    _render_props(
        binary,
        workspace,
        "production-visual.json",
        subtitle_free,
        concurrency=concurrency,
    )
    _render_props(
        binary,
        workspace,
        "production.json",
        output,
        concurrency=concurrency,
    )
    report = {
        "schema_version": 1,
        "engine": "remotion",
        "composition": "ProductionFilm",
        "workspace": studio.portable_path(root, workspace),
        "props": "remotion-workspace/public/production.json",
        "film_fingerprint": production_contract.canonical_digest(film),
        "project_sha256": production_contract.file_digest(root / "project.json"),
        "output": studio.portable_path(root, output),
        "output_sha256": production_contract.file_digest(output),
        "subtitle_free_master": studio.portable_path(root, subtitle_free),
        "subtitle_free_sha256": production_contract.file_digest(subtitle_free),
        "scene_count": len(film["film"]["scenes"]),
        "duration_s": film["film"]["canvas"]["duration_s"],
        "fps": film["film"]["canvas"]["fps"],
    }
    studio.atomic_json(root / "reports" / "remotion-render.json", report)
    print(
        f"rendered {output} with Remotion "
        f"({report['duration_s']:.2f}s, {report['scene_count']} shots)"
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_dir")
    parser.add_argument("--output", default="final.mp4")
    args = parser.parse_args()
    root = Path(args.project_dir).resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output
    try:
        render(root, output)
        return 0
    except (ProductionRemotionError, studio.StudioError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
