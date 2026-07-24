#!/usr/bin/env python3
"""Project, validation, job-manifest, and artifact-state CLI."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
ASPECTS = {"16:9", "9:16", "1:1", "4:5", "3:4", "4:3"}
MODES = {"topic", "footage", "photo"}
JOB_STAGES = {"styles", "images", "layers", "motion", "voice", "music"}
ARTIFACT_RE = re.compile(r"^(style|image|layers|motion|voice|music):[A-Za-z0-9._-]+$")


class StudioError(RuntimeError):
    pass


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def slugify(value: str, fallback: str = "project") -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    value = value.strip("-")
    return value[:64] or fallback


def atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    )
    try:
        with handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(handle.name, path)
    finally:
        if os.path.exists(handle.name):
            os.unlink(handle.name)


def project_file(root: Path) -> Path:
    return root / "project.json"


def state_file(root: Path) -> Path:
    return root / "state.json"


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as exc:
        raise StudioError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StudioError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StudioError(f"expected a JSON object in {path}")
    return value


def load_project(root: Path) -> dict[str, Any]:
    return load_json(project_file(root))


def load_state(root: Path) -> dict[str, Any]:
    path = state_file(root)
    if not path.exists():
        return {"version": 1, "artifacts": {}, "approvals": {}}
    data = load_json(path)
    data.setdefault("version", 1)
    data.setdefault("artifacts", {})
    data.setdefault("approvals", {})
    return data


def approval_digest(project: dict[str, Any], gate: str) -> str:
    pmeta = project.get("project", {})
    creative = project.get("creative", {})
    if gate == "story":
        payload = {
            "project": {key: pmeta.get(key) for key in
                        ("mode", "topic", "language", "duration_s", "aspect")},
            "source": project.get("source", {}),
            "arc": creative.get("arc"),
            "beats": project.get("beats", []),
        }
    elif gate == "style":
        payload = {
            "project": {key: pmeta.get(key) for key in ("mode", "aspect")},
            "source": project.get("source", {}),
            "candidate_themes": creative.get("candidate_themes", []),
            "theme": creative.get("theme"),
            "representative_beat": (project.get("beats") or [None])[0],
        }
    elif gate == "creative-qa":
        payload = project
    else:
        raise StudioError(f"unknown approval gate: {gate}")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def final_signature(root: Path) -> str | None:
    final = root / "final.mp4"
    if not final.is_file():
        return None
    stat = final.stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def approval_valid(root: Path, project: dict[str, Any], state: dict[str, Any],
                   gate: str) -> bool:
    record = state.get("approvals", {}).get(gate)
    if not isinstance(record, dict):
        return False
    if record.get("digest") != approval_digest(project, gate):
        return False
    if gate == "creative-qa":
        qa_path = root / "qa" / "report.json"
        if not qa_path.is_file():
            return False
        try:
            qa_report = load_json(qa_path)
        except StudioError:
            return False
        if qa_report.get("summary", {}).get("errors", 1):
            return False
        if record.get("qa_generated_at") != qa_report.get("generated_at"):
            return False
        if record.get("final_signature") != final_signature(root):
            return False
    return True


def record_approval(root: Path, gate: str, note: str = "") -> dict[str, Any]:
    project = load_project(root)
    state = load_state(root)
    if gate == "story":
        errors, _ = validate_project(root, project, "story")
        if errors:
            raise StudioError(f"story approval blocked by {len(errors)} validation error(s)")
    elif gate == "style":
        if not isinstance(project.get("creative", {}).get("theme"), dict):
            raise StudioError("style approval requires a selected creative.theme")
        expected = {job["id"] for job in build_jobs(root, project, "styles")}
        missing = expected - set(state["artifacts"])
        if missing:
            raise StudioError(f"style approval requires all previews; missing: {sorted(missing)}")
    elif gate == "creative-qa":
        qa_path = root / "qa" / "report.json"
        if not qa_path.is_file():
            raise StudioError("creative QA approval requires qa/report.json")
        qa_report = load_json(qa_path)
        if qa_report.get("summary", {}).get("errors", 1):
            raise StudioError("creative QA approval is blocked by technical QA errors")
        if final_signature(root) is None:
            raise StudioError("creative QA approval requires final.mp4")
    else:
        raise StudioError(f"unknown approval gate: {gate}")
    record: dict[str, Any] = {
        "approved_at": now_iso(),
        "digest": approval_digest(project, gate),
        "note": note,
    }
    if gate == "creative-qa":
        qa_report = load_json(root / "qa" / "report.json")
        record["qa_generated_at"] = qa_report.get("generated_at")
        record["final_signature"] = final_signature(root)
    state["approvals"][gate] = record
    state["updated_at"] = now_iso()
    atomic_json(state_file(root), state)
    return record


def resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def portable_path(root: Path, value: Path) -> str:
    value = value.resolve()
    try:
        return value.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(value)


def theme_fields(theme: dict[str, Any]) -> str:
    keys = ("medium", "palette", "typography", "texture", "composition", "motion")
    return "\n".join(f"{key.upper()}: {theme.get(key, '').strip()}" for key in keys)


def artifact_key(prefix: str, beat: dict[str, Any], shot: dict[str, Any] | None = None) -> str:
    suffix = str(beat["id"])
    if shot is not None:
        suffix += f"-{shot['id']}"
    return f"{prefix}:{suffix}"


def iter_shots(project: dict[str, Any]):
    for beat in project.get("beats", []):
        for shot in beat.get("shots", []):
            yield beat, shot


def source_input(root: Path, project: dict[str, Any]) -> dict[str, Any] | None:
    source = project.get("source", {})
    if source.get("path"):
        return {"role": "source", "path": portable_path(root, resolve_path(root, source["path"]))}
    return None


def image_prompt(project: dict[str, Any], beat: dict[str, Any], shot: dict[str, Any],
                 theme: dict[str, Any]) -> str:
    mode = project["project"]["mode"]
    display = beat.get("display_text", "").strip() if shot.get("show_display_text", True) else ""
    anchor = project.get("source", {}).get("anchor_policy", "").strip()
    lines = [
        "Create a finished editorial paper-collage poster.",
        theme_fields(theme),
        f"SCENE: {shot.get('scene', '').strip()}",
        f"FRAMING: {shot.get('framing', 'wide')}.",
        "LAYERS: build a clear foreground, middle layer, and background from separable paper elements.",
        "SURFACE: visible cut edges, restrained paper shadows, tactile print grain, and physical assembly.",
        f"ASPECT: {project['project']['aspect']}. Keep one unmistakable focal subject.",
    ]
    if display:
        lines.append(f'DISPLAY TEXT: spell exactly "{display}". Keep it short, sharp, and legible.')
    else:
        lines.append("DISPLAY TEXT: none; reserve clean space for captions.")
    if mode == "photo":
        subject = project.get("source", {}).get("subject", "subject")
        lines.extend([
            f"ANCHOR: preserve the supplied {subject} as photographic evidence, not a redesign.",
            f"ANCHOR POLICY: {anchor or 'preserve identity, proportions, labels, and recognizable details'}.",
            "Apply illustration, halftone, and paper texture to the environment unless explicitly allowed on the anchor.",
        ])
    lines.append("AVOID: smooth CGI, plastic 3D, weak pasted-on layouts, illegible text, and invented branding.")
    return "\n".join(lines)


def motion_prompt(project: dict[str, Any], beat: dict[str, Any], shot: dict[str, Any],
                  theme: dict[str, Any]) -> str:
    mode = project["project"]["mode"]
    locks = ["preserve layout", "preserve aspect", "preserve material style"]
    if shot.get("show_display_text", True) and beat.get("display_text"):
        locks.append(f'preserve exact title spelling "{beat["display_text"]}"')
    if mode == "photo":
        locks.append(project.get("source", {}).get("anchor_policy", "preserve the anchor exactly"))
    if mode == "footage":
        locks.extend(["preserve the performer frame-for-frame", "preserve lip timing and eye line"])
    return "\n".join([
        "Animate the supplied media as an editorial cut-paper motion piece.",
        f"THEME MOTION: {theme.get('motion', 'restrained tactile movement')}.",
        f"CAMERA: one {shot.get('camera', 'static')} move; do not reverse, reset, or loop.",
        f"ELEMENTS: {shot.get('element_motion', '').strip()}",
        "MATERIAL: rigid printed paper; use slide, hinge, flap, stamp, unfold, and layered parallax behavior.",
        f"LOCKS: {'; '.join(locks)}.",
        "AVOID: melting, morphing, text wobble, facial reconstruction, product-label drift, extra limbs, and newly invented objects.",
    ])


def expected_output(job_id: str, kind: str) -> str:
    safe = job_id.split(":", 1)[1]
    if kind in {"image_generation", "image_edit"}:
        return f"media/images/{safe}.png"
    if kind in {"image_to_video", "video_edit"}:
        return f"media/motion/{safe}.mp4"
    if kind == "layer_package":
        return f"media/layers/{safe}/layers.json"
    if kind == "layers_to_video":
        return f"media/motion/{safe}.mp4"
    if kind == "speech":
        return f"media/audio/{safe}.wav"
    if kind == "music":
        return "media/audio/music-main.wav"
    raise StudioError(f"unsupported job kind: {kind}")


def make_job(job_id: str, stage: str, kind: str, prompt: str, inputs: list[dict[str, Any]],
             params: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": job_id,
        "stage": stage,
        "kind": kind,
        "prompt": prompt,
        "inputs": inputs,
        "params": params,
        "output": {"path": expected_output(job_id, kind)},
        "meta": meta,
    }


def build_jobs(root: Path, project: dict[str, Any], stage: str) -> list[dict[str, Any]]:
    pmeta = project["project"]
    mode = pmeta["mode"]
    creative = project.get("creative", {})
    theme = creative.get("theme")
    aspect = pmeta["aspect"]
    fps = pmeta.get("fps", 24)
    jobs: list[dict[str, Any]] = []

    if stage == "styles":
        beats = project.get("beats", [])
        candidates = creative.get("candidate_themes", [])
        if not beats or not beats[0].get("shots"):
            return []
        beat, shot = beats[0], beats[0]["shots"][0]
        for candidate in candidates:
            job_id = f"style:{candidate['id']}"
            inputs: list[dict[str, Any]] = []
            if mode in {"photo", "footage"}:
                source = source_input(root, project)
                if source:
                    inputs.append(source)
            if mode == "footage":
                kind = "video_edit"
                params = {
                    "aspect": aspect,
                    "duration_s": min(float(shot.get("duration_s", 4)), 5),
                    "source_range": [beat.get("start_s", 0), beat.get("end_s", 5)],
                    "fps": fps,
                }
                prompt = motion_prompt(project, beat, shot, candidate)
            else:
                kind = "image_edit" if mode == "photo" else "image_generation"
                params = {"aspect": aspect, "purpose": "style-comparison"}
                prompt = image_prompt(project, beat, shot, candidate)
            jobs.append(make_job(job_id, stage, kind, prompt, inputs, params,
                                 {"theme_id": candidate["id"], "comparison": True}))
        return jobs

    if stage == "images":
        if mode == "footage":
            return []
        kind = "image_edit" if mode == "photo" else "image_generation"
        for beat, shot in iter_shots(project):
            job_id = artifact_key("image", beat, shot)
            inputs = []
            if mode == "photo":
                source = source_input(root, project)
                if source:
                    inputs.append(source)
            jobs.append(make_job(
                job_id, stage, kind, image_prompt(project, beat, shot, theme), inputs,
                {"aspect": aspect}, {"beat_id": beat["id"], "shot_id": shot["id"]}
            ))
        return jobs

    if stage == "layers":
        motion_config = project.get("motion", {})
        if motion_config.get("pipeline", "generative") != "layered" or mode == "footage":
            return []
        state = load_state(root)
        for beat, shot in iter_shots(project):
            job_id = artifact_key("layers", beat, shot)
            image_id = artifact_key("image", beat, shot)
            image_state = state["artifacts"].get(image_id, {})
            image_path = image_state.get("path") or expected_output(
                image_id, "image_edit" if mode == "photo" else "image_generation"
            )
            prompt = "\n".join([
                "Prepare a deterministic transparent layer package for paper-collage animation.",
                f"SCENE: {shot.get('scene', '').strip()}",
                f"ELEMENT ACTIONS: {shot.get('element_motion', '').strip()}",
                "Separate background, middle ground, foreground, and every named moving paper object.",
                "Remove moving objects from the clean plate. Preserve exact registration and canvas size.",
                "Return layers.json plus full-canvas RGBA PNG layers with explicit z-order and keyframes.",
            ])
            jobs.append(make_job(
                job_id, stage, "layer_package", prompt,
                [{"role": "keyframe", "path": image_path}],
                {
                    "aspect": aspect,
                    "duration_s": shot.get("duration_s", 4),
                    "fps": fps,
                    "min_layers": int(motion_config.get("min_layers", 4)),
                    "min_animated_layers": int(
                        motion_config.get("min_animated_layers", 3)
                    ),
                },
                {"beat_id": beat["id"], "shot_id": shot["id"]},
            ))
        return jobs

    if stage == "motion":
        state = load_state(root)
        layered = project.get("motion", {}).get("pipeline", "generative") == "layered"
        for beat, shot in iter_shots(project):
            job_id = artifact_key("motion", beat, shot)
            inputs: list[dict[str, Any]] = []
            if layered and mode != "footage":
                layer_id = artifact_key("layers", beat, shot)
                layer_state = state["artifacts"].get(layer_id, {})
                layer_path = layer_state.get("path") or expected_output(
                    layer_id, "layer_package"
                )
                inputs.append({"role": "layer_manifest", "path": layer_path})
                kind = "layers_to_video"
            elif mode == "footage":
                source = source_input(root, project)
                if source:
                    source["range_s"] = [beat.get("start_s"), beat.get("end_s")]
                    inputs.append(source)
                kind = "video_edit"
            else:
                image_id = artifact_key("image", beat, shot)
                image_state = state["artifacts"].get(image_id, {})
                image_path = image_state.get("path") or expected_output(
                    image_id, "image_edit" if mode == "photo" else "image_generation"
                )
                inputs.append({"role": "keyframe", "path": image_path})
                kind = "image_to_video"
            jobs.append(make_job(
                job_id, stage, kind, motion_prompt(project, beat, shot, theme), inputs,
                {"aspect": aspect, "duration_s": shot.get("duration_s", 4), "fps": fps,
                 "generate_audio": False},
                {"beat_id": beat["id"], "shot_id": shot["id"]}
            ))
        return jobs

    if stage == "voice":
        preserve = bool(project.get("source", {}).get("preserve_original_audio"))
        if mode == "footage" and preserve:
            return []
        voice = project.get("audio", {}).get("voice", {})
        for beat in project.get("beats", []):
            job_id = artifact_key("voice", beat)
            beat_duration = sum(float(shot.get("duration_s", 0))
                                for shot in beat.get("shots", []))
            jobs.append(make_job(
                job_id, stage, "speech", beat.get("narration", ""), [],
                {"language": pmeta.get("language", "en"),
                 "voice": voice.get("description", ""),
                 "speed": voice.get("speed", 1.0),
                 "duration_s": beat_duration},
                {"beat_id": beat["id"]}
            ))
        return jobs

    if stage == "music":
        prompt = project.get("audio", {}).get("music_prompt", "").strip()
        if not prompt:
            return []
        jobs.append(make_job(
            "music:main", stage, "music", prompt, [],
            {"duration_s": pmeta.get("duration_s", 30), "instrumental": True},
            {"loopable": True}
        ))
        return jobs

    raise StudioError(f"unknown stage: {stage}")


def validate_project(root: Path, project: dict[str, Any], stage: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if project.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    pmeta = project.get("project")
    if not isinstance(pmeta, dict):
        return ["project must be an object"], warnings
    mode = pmeta.get("mode")
    test_mode = bool(pmeta.get("test_mode", False))
    if mode not in MODES:
        errors.append(f"project.mode must be one of {sorted(MODES)}")
    motion_config = project.get("motion", {})
    motion_pipeline = motion_config.get("pipeline", "generative")
    if motion_pipeline not in {"generative", "layered"}:
        errors.append("motion.pipeline must be generative or layered")
    if motion_pipeline == "layered" and mode == "footage":
        warnings.append("footage mode uses video_edit; layered pipeline applies to topic/photo")
    if pmeta.get("aspect") not in ASPECTS:
        errors.append(f"project.aspect must be one of {sorted(ASPECTS)}")
    try:
        duration = float(pmeta.get("duration_s"))
        if duration <= 0:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("project.duration_s must be a positive number")
        duration = 0

    source = project.get("source", {})
    if mode in {"photo", "footage"}:
        source_path = source.get("path")
        if not source_path:
            errors.append(f"source.path is required for {mode} mode")
        elif not resolve_path(root, source_path).is_file():
            errors.append(f"source file does not exist: {source_path}")
    if mode == "photo" and source.get("subject") not in {"portrait", "product"}:
        errors.append("source.subject must be portrait or product in photo mode")
    if mode == "photo" and not source.get("anchor_policy", "").strip():
        warnings.append("photo mode should define source.anchor_policy")

    creative = project.get("creative", {})
    if not creative.get("arc", "").strip():
        warnings.append("creative.arc is empty")
    beats = project.get("beats")
    if not isinstance(beats, list) or not beats:
        errors.append("beats must be a non-empty array")
        return errors, warnings

    beat_ids: set[str] = set()
    shot_keys: set[str] = set()
    total_shot_duration = 0.0
    for index, beat in enumerate(beats, 1):
        bid = str(beat.get("id", "")).strip()
        label = bid or f"beat[{index}]"
        if not bid:
            errors.append(f"beat[{index}] is missing id")
        elif bid in beat_ids:
            errors.append(f"duplicate beat id: {bid}")
        beat_ids.add(bid)
        if not beat.get("purpose", "").strip():
            warnings.append(f"{label} has no purpose")
        if mode != "footage" and not beat.get("narration", "").strip():
            errors.append(f"{label} has no narration")
        if mode == "footage":
            try:
                start, end = float(beat["start_s"]), float(beat["end_s"])
                if start < 0 or end <= start:
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                errors.append(f"{label} needs valid start_s/end_s")
        shots = beat.get("shots")
        if not isinstance(shots, list) or not shots:
            errors.append(f"{label} must have at least one shot")
            continue
        for sindex, shot in enumerate(shots, 1):
            sid = str(shot.get("id", "")).strip()
            skey = f"{bid}-{sid}"
            if not sid:
                errors.append(f"{label}.shots[{sindex}] is missing id")
            elif skey in shot_keys:
                errors.append(f"duplicate shot key: {skey}")
            shot_keys.add(skey)
            if not shot.get("scene", "").strip():
                errors.append(f"{skey} has no scene")
            try:
                shot_dur = float(shot.get("duration_s"))
                if shot_dur <= 0:
                    raise ValueError
                total_shot_duration += shot_dur
                if shot_dur < 3 and not test_mode:
                    warnings.append(f"{skey} is {shot_dur:g}s; ordinary production shots "
                                    "should be at least 3s")
                if shot_dur > 7:
                    warnings.append(f"{skey} is {shot_dur:g}s; justify shots longer than 7s")
            except (TypeError, ValueError):
                errors.append(f"{skey} duration_s must be positive")
            if not shot.get("element_motion", "").strip():
                warnings.append(f"{skey} has no specific element_motion")

    if duration and total_shot_duration:
        delta = abs(total_shot_duration - duration) / duration
        if delta > 0.25:
            warnings.append(
                f"shot durations total {total_shot_duration:g}s versus project {duration:g}s"
            )

    candidates = creative.get("candidate_themes", [])
    if stage in {"styles", "images", "layers", "motion", "assemble"}:
        if len(candidates) != 3:
            warnings.append(f"expected exactly 3 candidate themes; found {len(candidates)}")
        candidate_ids = [c.get("id") for c in candidates if isinstance(c, dict)]
        if len(candidate_ids) != len(set(candidate_ids)):
            errors.append("candidate theme ids must be unique")
    if stage in {"images", "layers", "motion", "assemble"} and not isinstance(
        creative.get("theme"), dict
    ):
        errors.append("creative.theme must be selected before production")

    if stage == "assemble":
        state = load_state(root)
        artifacts = state.get("artifacts", {})
        if motion_pipeline == "layered" and mode != "footage":
            for beat, shot in iter_shots(project):
                key = artifact_key("layers", beat, shot)
                record = artifacts.get(key)
                if not record or not resolve_path(root, record.get("path", "")).is_file():
                    errors.append(f"missing registered layer artifact: {key}")
        for beat, shot in iter_shots(project):
            key = artifact_key("motion", beat, shot)
            record = artifacts.get(key)
            if not record or not resolve_path(root, record.get("path", "")).is_file():
                errors.append(f"missing registered motion artifact: {key}")
        preserve = mode == "footage" and bool(source.get("preserve_original_audio"))
        if not preserve:
            for beat in beats:
                key = artifact_key("voice", beat)
                record = artifacts.get(key)
                if not record or not resolve_path(root, record.get("path", "")).is_file():
                    errors.append(f"missing registered voice artifact: {key}")
        if project.get("audio", {}).get("music_prompt"):
            record = artifacts.get("music:main")
            if not record or not resolve_path(root, record.get("path", "")).is_file():
                errors.append("missing registered music artifact: music:main")
    return errors, warnings


def cmd_doctor(_: argparse.Namespace) -> int:
    checks = {
        "python": sys.executable,
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
    }
    try:
        import PIL  # type: ignore
        checks["pillow"] = getattr(PIL, "__version__", "installed")
    except ImportError:
        checks["pillow"] = None
    failed = False
    for name, value in checks.items():
        ok = bool(value)
        failed |= not ok
        print(f"{'OK' if ok else 'MISSING':7} {name}: {value or 'not found'}")
    return 1 if failed else 0


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.project_dir).resolve()
    pfile = project_file(root)
    if pfile.exists() and not args.force:
        raise StudioError(f"{pfile} already exists; use --force to replace it")
    root.mkdir(parents=True, exist_ok=True)
    for folder in ("jobs", "media/images", "media/motion", "media/audio", "render"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    topic = args.topic.strip()
    title = (args.title or topic or root.name).strip()
    project = {
        "schema_version": SCHEMA_VERSION,
        "project": {
            "id": slugify(root.name),
            "title": title,
            "mode": args.mode,
            "topic": topic,
            "language": args.language,
            "duration_s": args.duration,
            "aspect": args.aspect,
            "fps": args.fps,
        },
        "source": {},
        "creative": {"arc": "", "theme": None, "candidate_themes": []},
        "audio": {
            "voice": {"description": "", "speed": 1.0},
            "music_prompt": "",
            "captions": True,
            "caption_style": "clean",
            "watermark": "",
            "mix": {"voice": 1.0, "music": 0.35},
        },
        "motion": {
            "pipeline": "generative",
            "min_layers": 4,
            "min_animated_layers": 3
        },
        "beats": [],
    }
    atomic_json(pfile, project)
    atomic_json(state_file(root), {
        "version": 1, "artifacts": {}, "approvals": {}, "updated_at": now_iso()
    })
    print(f"created {pfile}")
    print("next: edit project.json, then run validate --stage story")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    root = Path(args.project_dir).resolve()
    project = load_project(root)
    errors, warnings = validate_project(root, project, args.stage)
    for item in warnings:
        print(f"WARNING: {item}")
    for item in errors:
        print(f"ERROR: {item}")
    print(f"validation: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


def cmd_jobs(args: argparse.Namespace) -> int:
    root = Path(args.project_dir).resolve()
    project = load_project(root)
    errors, warnings = validate_project(root, project, args.stage)
    for item in warnings:
        print(f"WARNING: {item}")
    if errors:
        for item in errors:
            print(f"ERROR: {item}")
        return 1
    jobs = build_jobs(root, project, args.stage)
    state = load_state(root)
    if not args.include_complete:
        jobs = [job for job in jobs if job["id"] not in state["artifacts"]]
    out = root / "jobs" / f"{args.stage}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as handle:
        for job in jobs:
            handle.write(json.dumps(job, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"wrote {len(jobs)} job(s): {out}")
    return 0


def cmd_register(args: argparse.Namespace) -> int:
    root = Path(args.project_dir).resolve()
    if not ARTIFACT_RE.match(args.job_id):
        raise StudioError(f"invalid artifact id: {args.job_id}")
    path = resolve_path(root, args.path).resolve()
    if not path.is_file() or path.stat().st_size <= 0:
        raise StudioError(f"artifact file is missing or empty: {path}")
    state = load_state(root)
    state["artifacts"][args.job_id] = {
        "path": portable_path(root, path),
        "url": args.url,
        "job_id": args.job_id,
        "updated_at": now_iso(),
    }
    state["updated_at"] = now_iso()
    atomic_json(state_file(root), state)
    print(f"registered {args.job_id} -> {portable_path(root, path)}")
    return 0


def cmd_choose_theme(args: argparse.Namespace) -> int:
    root = Path(args.project_dir).resolve()
    project = load_project(root)
    candidates = project.get("creative", {}).get("candidate_themes", [])
    selected = next((item for item in candidates if item.get("id") == args.theme_id), None)
    if not selected:
        raise StudioError(f"unknown theme id: {args.theme_id}")
    project["creative"]["theme"] = selected
    atomic_json(project_file(root), project)
    print(f"selected theme: {args.theme_id}")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    root = Path(args.project_dir).resolve()
    record = record_approval(root, args.gate, args.note)
    print(f"approved {args.gate}: {record['approved_at']}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = Path(args.project_dir).resolve()
    project = load_project(root)
    state = load_state(root)
    present = set(state.get("artifacts", {}))
    rows = []
    for stage in ("styles", "images", "layers", "motion", "voice", "music"):
        try:
            expected = {job["id"] for job in build_jobs(root, project, stage)}
        except (KeyError, TypeError):
            expected = set()
        rows.append((stage, len(expected & present), len(expected), sorted(expected - present)))
    for stage, complete, total, missing in rows:
        print(f"{stage:8} {complete}/{total}")
        if args.verbose and missing:
            print("  missing:", ", ".join(missing))
    for gate in ("story", "style", "creative-qa"):
        valid = approval_valid(root, project, state, gate)
        print(f"approval {gate:11} {'valid' if valid else 'missing/stale'}")
    errors, warnings = validate_project(root, project, "assemble")
    if warnings and args.verbose:
        for item in warnings:
            print(f"WARNING: {item}")
    print("render:", "ready" if not errors else f"blocked ({len(errors)} issue(s))")
    if args.verbose:
        for item in errors:
            print(f"  - {item}")
    return 0 if not errors else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check local render dependencies")
    doctor.set_defaults(func=cmd_doctor)

    init = sub.add_parser("init", help="create a new editable project")
    init.add_argument("project_dir")
    init.add_argument("--mode", choices=sorted(MODES), default="topic")
    init.add_argument("--topic", default="")
    init.add_argument("--title")
    init.add_argument("--duration", type=float, default=30)
    init.add_argument("--aspect", choices=sorted(ASPECTS), default="9:16")
    init.add_argument("--language", default="zh")
    init.add_argument("--fps", type=int, default=24)
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=cmd_init)

    validate = sub.add_parser("validate", help="validate a project for a stage")
    validate.add_argument("project_dir")
    validate.add_argument("--stage", choices=["story", *sorted(JOB_STAGES), "assemble"],
                          default="story")
    validate.set_defaults(func=cmd_validate)

    jobs = sub.add_parser("jobs", help="write a deterministic JSONL job manifest")
    jobs.add_argument("project_dir")
    jobs.add_argument("--stage", choices=sorted(JOB_STAGES), required=True)
    jobs.add_argument("--include-complete", action="store_true")
    jobs.set_defaults(func=cmd_jobs)

    register = sub.add_parser("register", help="register a completed media artifact")
    register.add_argument("project_dir")
    register.add_argument("--job-id", required=True)
    register.add_argument("--path", required=True)
    register.add_argument("--url")
    register.set_defaults(func=cmd_register)

    choose = sub.add_parser("choose-theme", help="promote one candidate theme")
    choose.add_argument("project_dir")
    choose.add_argument("theme_id")
    choose.set_defaults(func=cmd_choose_theme)

    approve = sub.add_parser("approve", help="record an auditable approval gate")
    approve.add_argument("project_dir")
    approve.add_argument("--gate", choices=["story", "style", "creative-qa"], required=True)
    approve.add_argument("--note", default="")
    approve.set_defaults(func=cmd_approve)

    status = sub.add_parser("status", help="show stage completion and render readiness")
    status.add_argument("project_dir")
    status.add_argument("--verbose", action="store_true")
    status.set_defaults(func=cmd_status)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        return int(args.func(args))
    except StudioError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
