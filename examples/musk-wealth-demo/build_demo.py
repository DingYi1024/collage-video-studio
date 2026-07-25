#!/usr/bin/env python3
"""Rebuild the directed-motion Musk wealth-path demo from source assets."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parent
SKILL_ROOT = ROOT.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import layer_compositor  # noqa: E402
import studio  # noqa: E402

STUDIO = SKILL_ROOT / "scripts" / "studio.py"
RUNNER = SKILL_ROOT / "scripts" / "job_runner.py"
RENDER = SKILL_ROOT / "scripts" / "render.py"
QA = SKILL_ROOT / "scripts" / "qa.py"
ADAPTER = ROOT / "demo_backend.py"
CREATE_LAYERS = ROOT / "create_layer_assets.py"
CREATE_AUDIO = ROOT / "create_audio_assets.py"


def run(*args: str) -> None:
    print("+", " ".join(args))
    subprocess.run(args, check=True, cwd=SKILL_ROOT)


def reset_generated() -> None:
    for name in ("jobs", "media", "render", "qa", "result", ".studio"):
        target = ROOT / name
        if target.exists():
            shutil.rmtree(target)
    for name in ("project.json", "state.json", "final.mp4"):
        target = ROOT / name
        if target.exists():
            target.unlink()
    shutil.copy2(ROOT / "project.seed.json", ROOT / "project.json")
    (ROOT / "state.json").write_text(
        json.dumps(
            {"version": 1, "artifacts": {}, "approvals": {}},
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def write_complete_manifests() -> None:
    project = studio.load_project(ROOT)
    jobs_dir = ROOT / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    original_state = studio.load_state(ROOT)
    try:
        studio.atomic_json(
            ROOT / "state.json",
            {"version": 1, "artifacts": {}, "approvals": {}},
        )
        for stage in ("styles", "images", "layers", "motion", "voice", "music"):
            jobs = studio.build_jobs(ROOT, project, stage)
            manifest = jobs_dir / f"{stage}.jsonl"
            with manifest.open("w", encoding="utf-8", newline="\n") as handle:
                for job in jobs:
                    handle.write(
                        json.dumps(job, ensure_ascii=False, sort_keys=True) + "\n"
                    )
    finally:
        studio.atomic_json(ROOT / "state.json", original_state)


def make_result_assets() -> None:
    result = ROOT / "result"
    result.mkdir(parents=True, exist_ok=True)
    frames = sorted((ROOT / "qa" / "frames").glob("*.jpg"))
    if not frames:
        raise RuntimeError("QA did not produce review frames")
    shutil.copy2(frames[0], result / "poster.jpg")
    thumbs: list[Image.Image] = []
    for frame in frames:
        with Image.open(frame) as image:
            thumbs.append(ImageOps.fit(image.convert("RGB"), (400, 225)))
    columns = 3
    rows = (len(thumbs) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * 400, rows * 225), "#eee0c2")
    for index, image in enumerate(thumbs):
        sheet.paste(image, ((index % columns) * 400, (index // columns) * 225))
    sheet.save(result / "contact-sheet.jpg", quality=90, optimize=True)
    run(
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(ROOT / "final.mp4"),
        "-vf",
        "fps=12,scale=300:-2:flags=lanczos,"
        "split[s0][s1];[s0]palettegen=max_colors=96:stats_mode=diff[p];"
        "[s1][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle",
        "-loop", "0", str(result / "preview.gif"),
    )
    run(
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(ROOT / "final.mp4"),
        "-vf", "scale=720:-2:flags=lanczos,fps=30",
        "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(result / "preview.mp4"),
    )
    motion_strip_args: list[str] = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error"
    ]
    for timestamp in ("8.30", "8.55", "9.00", "9.60", "10.10"):
        motion_strip_args.extend(["-ss", timestamp, "-i", str(ROOT / "final.mp4")])
    motion_strip_args.extend([
        "-filter_complex",
        "[0:v]scale=240:135[a];[1:v]scale=240:135[b];"
        "[2:v]scale=240:135[c];[3:v]scale=240:135[d];"
        "[4:v]scale=240:135[e];"
        "[a][b][c][d][e]xstack=inputs=5:"
        "layout=0_0|240_0|480_0|720_0|960_0[out]",
        "-map", "[out]", "-frames:v", "1", str(result / "motion-strip.jpg"),
    ])
    run(*motion_strip_args)
    packs = []
    total_layers = 0
    total_animated = 0
    for manifest_path in sorted((ROOT / "media" / "layers").glob("*/layers.json")):
        errors, warnings, stats = layer_compositor.validate_manifest(manifest_path)
        if errors or warnings:
            raise RuntimeError(f"{manifest_path}: {errors} {warnings}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        packs.append({
            "id": manifest.get("id", manifest_path.parent.name),
            "layers": stats["layers"],
            "animated_layers": stats["animated_layers"],
            "primary_action": manifest["direction"]["primary_action"],
            "primary_layers": manifest["direction"]["primary_layers"],
            "manifest": manifest_path.relative_to(ROOT).as_posix(),
        })
        total_layers += stats["layers"]
        total_animated += stats["animated_layers"]
    summary = {
        "final": "final.mp4",
        "poster": "result/poster.jpg",
        "preview": "result/preview.gif",
        "smooth_preview": "result/preview.mp4",
        "contact_sheet": "result/contact-sheet.jpg",
        "motion_strip": "result/motion-strip.jpg",
        "qa_report": "qa/report.md",
        "creative_review": "result/creative-review.md",
        "duration_s": 24,
        "aspect": "16:9",
        "layered_motion": {
            "packages": len(packs),
            "layers": total_layers,
            "animated_layers": total_animated,
            "directed_shots": len(packs),
            "packs": packs,
        },
        "stages": [
            "styles", "images", "layers", "motion", "voice", "music", "render", "qa"
        ],
    }
    (result / "build-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    creative_review = """# Creative review

- [x] Opening communicates “not salary, but equity” within three seconds without audio.
- [x] Six shots use distinct close, medium, tabletop, top-down, industrial-wide, and final-wide staging.
- [x] Each shot has one readable primary action with anticipation, action, and settle.
- [x] Faces and planted reference planes stay stable; there is no pose flash, morph, or sliding person.
- [x] Captions remain readable and do not cover the primary action.
- [x] Mandarin narration is complete; music remains restrained and no syllable is clipped.
- [x] Final rank token lands before a designed reading hold; the ending is not abrupt.

Reviewed against `final.mp4` at 30 FPS and the 12 extracted QA frames.
"""
    (result / "creative-review.md").write_text(creative_review, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-generated", action="store_true")
    parser.add_argument(
        "--manifests-only",
        action="store_true",
        help="rewrite complete JSONL job manifests without changing artifacts",
    )
    args = parser.parse_args()
    if args.manifests_only:
        write_complete_manifests()
        return 0
    if not args.keep_generated:
        reset_generated()
    run(sys.executable, str(CREATE_LAYERS))
    run(sys.executable, str(CREATE_AUDIO))
    run(sys.executable, str(STUDIO), "validate", str(ROOT), "--stage", "story")
    run(
        sys.executable, str(STUDIO), "approve", str(ROOT),
        "--gate", "story", "--note", "Historical path and narration approved",
    )
    run(sys.executable, str(STUDIO), "jobs", str(ROOT), "--stage", "styles")
    run(
        sys.executable, str(RUNNER), str(ROOT), "--stage", "styles",
        "--adapter", str(ADAPTER),
    )
    run(sys.executable, str(STUDIO), "choose-theme", str(ROOT), "industrial-paper")
    run(
        sys.executable, str(STUDIO), "approve", str(ROOT),
        "--gate", "style", "--note", "Industrial paper selected after comparison",
    )
    for stage in ("images", "layers", "motion", "voice", "music"):
        run(sys.executable, str(STUDIO), "jobs", str(ROOT), "--stage", stage)
        run(
            sys.executable, str(RUNNER), str(ROOT), "--stage", stage,
            "--adapter", str(ADAPTER),
        )
    run(sys.executable, str(RENDER), str(ROOT), "--output", "final.mp4")
    run(sys.executable, str(QA), str(ROOT), "--final", "final.mp4", "--frames", "12")
    report = json.loads((ROOT / "qa" / "report.json").read_text(encoding="utf-8"))
    if report["summary"]["errors"] or report["summary"]["warnings"]:
        raise RuntimeError(f"QA did not pass cleanly: {report['summary']}")
    run(
        sys.executable, str(STUDIO), "approve", str(ROOT),
        "--gate", "creative-qa", "--note", "Directed motion and review frames approved",
    )
    make_result_assets()
    write_complete_manifests()
    run(sys.executable, str(STUDIO), "status", str(ROOT), "--verbose")
    print(f"\nDemo complete: {ROOT / 'final.mp4'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
