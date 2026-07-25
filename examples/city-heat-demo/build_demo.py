#!/usr/bin/env python3
"""Rebuild the bundled city-heat demo from manifests to final QA artifacts."""

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
STUDIO = SKILL_ROOT / "scripts" / "studio.py"
RUNNER = SKILL_ROOT / "scripts" / "job_runner.py"
RENDER = SKILL_ROOT / "scripts" / "render.py"
QA = SKILL_ROOT / "scripts" / "qa.py"
ADAPTER = ROOT / "demo_backend.py"
CREATE_LAYERS = ROOT / "create_layer_assets.py"


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
            thumbs.append(ImageOps.fit(image.convert("RGB"), (270, 480)))
    columns = 4
    rows = (len(thumbs) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * 270, rows * 480), "#f2ead8")
    for index, image in enumerate(thumbs):
        sheet.paste(image, ((index % columns) * 270, (index // columns) * 480))
    sheet.save(result / "contact-sheet.jpg", quality=88, optimize=True)

    run(
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(ROOT / "final.mp4"),
        "-vf",
        "fps=15,scale=270:-2:flags=lanczos,"
        "split[s0][s1];[s0]palettegen=max_colors=96:stats_mode=diff[p];"
        "[s1][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle",
        "-loop", "0", str(result / "preview.gif"),
    )
    run(
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(ROOT / "final.mp4"),
        "-vf", "scale=540:-2:flags=lanczos,fps=30",
        "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "24",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(result / "preview.mp4"),
    )
    layer_packs = []
    total_layers = 0
    total_animated = 0
    for manifest_path in sorted((ROOT / "media" / "layers").glob("*/layers.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        layers = manifest["layers"]
        animated = sum(
            len(layer.get("keyframes", [])) >= 2
            and any(
                frame != layer["keyframes"][0]
                for frame in layer["keyframes"][1:]
            )
            for layer in layers
        )
        layer_packs.append({
            "id": manifest.get("id", manifest_path.parent.name),
            "layers": len(layers),
            "animated_layers": animated,
            "manifest": manifest_path.relative_to(ROOT).as_posix(),
        })
        total_layers += len(layers)
        total_animated += animated
    summary = {
        "final": "final.mp4",
        "poster": "result/poster.jpg",
        "preview": "result/preview.gif",
        "smooth_preview": "result/preview.mp4",
        "contact_sheet": "result/contact-sheet.jpg",
        "qa_report": "qa/report.md",
        "duration_s": 16,
        "aspect": "9:16",
        "layered_motion": {
            "packages": len(layer_packs),
            "layers": total_layers,
            "animated_layers": total_animated,
            "packs": layer_packs,
        },
        "stages": [
            "styles", "images", "layers", "motion", "voice", "music", "render", "qa"
        ],
    }
    (result / "build-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keep-generated",
        action="store_true",
        help="do not reset project.json, state.json, media, render, QA, and result files",
    )
    args = parser.parse_args()

    if not args.keep_generated:
        reset_generated()

    run(sys.executable, str(CREATE_LAYERS))
    run(sys.executable, str(STUDIO), "validate", str(ROOT), "--stage", "story")
    run(
        sys.executable, str(STUDIO), "approve", str(ROOT),
        "--gate", "story", "--note", "Bundled demo story approved",
    )
    run(sys.executable, str(STUDIO), "jobs", str(ROOT), "--stage", "styles")
    run(
        sys.executable, str(RUNNER), str(ROOT), "--stage", "styles",
        "--adapter", str(ADAPTER),
    )
    run(sys.executable, str(STUDIO), "choose-theme", str(ROOT), "paper-lab")
    run(
        sys.executable, str(STUDIO), "approve", str(ROOT),
        "--gate", "style", "--note", "Selected paper-lab after a three-way comparison",
    )

    for stage in ("images", "layers", "motion", "voice", "music"):
        run(sys.executable, str(STUDIO), "jobs", str(ROOT), "--stage", stage)
        run(
            sys.executable, str(RUNNER), str(ROOT), "--stage", stage,
            "--adapter", str(ADAPTER),
        )

    run(sys.executable, str(STUDIO), "status", str(ROOT), "--verbose")
    run(sys.executable, str(RENDER), str(ROOT), "--output", "final.mp4")
    run(sys.executable, str(QA), str(ROOT), "--final", "final.mp4", "--frames", "8")
    run(
        sys.executable, str(STUDIO), "approve", str(ROOT),
        "--gate", "creative-qa", "--note", "Technical QA passed; demo frames reviewed",
    )
    make_result_assets()
    run(sys.executable, str(STUDIO), "status", str(ROOT), "--verbose")
    print(f"\nDemo complete: {ROOT / 'final.mp4'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
