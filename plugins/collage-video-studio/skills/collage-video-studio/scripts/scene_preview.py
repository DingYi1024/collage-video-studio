#!/usr/bin/env python3
"""Render a bounded composition scene preview without rebuilding an entire film."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import layer_compositor
import production_metrics


class ScenePreviewError(RuntimeError):
    pass


def render(
    manifest: Path,
    output: Path,
    *,
    start_s: float,
    end_s: float,
    scale: float = 0.5,
) -> Path:
    if not shutil.which("ffmpeg"):
        raise ScenePreviewError("ffmpeg is required")
    data = layer_compositor.load_manifest(manifest)
    canvas = data["canvas"]
    duration = float(canvas["duration_s"])
    fps = int(canvas["fps"])
    if not (0 <= start_s < end_s <= duration):
        raise ScenePreviewError("preview range must stay inside the composition")
    if not (0.1 <= scale <= 1.0):
        raise ScenePreviewError("preview scale must be between 0.1 and 1.0")
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="scene-preview-") as temporary:
        frame_dir = Path(temporary)
        first = round(start_s * fps)
        last = max(first + 1, round(end_s * fps))
        loaded = layer_compositor.load_layer_sources(manifest, data)
        for output_index, frame_index in enumerate(range(first, last)):
            image = layer_compositor.render_frame(
                manifest, frame_index / fps, loaded, data
            )
            if scale != 1:
                image = image.resize(
                    (
                        max(2, round(image.width * scale / 2) * 2),
                        max(2, round(image.height * scale / 2) * 2),
                    )
                )
            image.convert("RGB").save(frame_dir / f"{output_index:06d}.png")
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-framerate",
                str(fps),
                "-i",
                str(frame_dir / "%06d.png"),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "24",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output),
            ],
            check=True,
        )
    if not output.is_file() or output.stat().st_size <= 0:
        raise ScenePreviewError("preview render produced no output")
    project_root = manifest.parent
    if (project_root / "project.json").is_file():
        production_metrics.record(
            project_root,
            category="video-render",
            operation="scene-preview",
            duration_s=time.perf_counter() - started,
            artifact=output,
        )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--start-s", type=float, required=True)
    parser.add_argument("--end-s", type=float, required=True)
    parser.add_argument("--scale", type=float, default=0.5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = render(
            args.manifest.resolve(),
            args.output.resolve(),
            start_s=args.start_s,
            end_s=args.end_s,
            scale=args.scale,
        )
        print(f"scene preview: {output}")
        return 0
    except (
        OSError,
        ValueError,
        KeyError,
        subprocess.CalledProcessError,
        layer_compositor.LayerError,
        ScenePreviewError,
    ) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
