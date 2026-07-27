#!/usr/bin/env python3
"""Generate deterministic seamless paper-strip PNGs for the bundled world proof."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


def strip(
    size: tuple[int, int],
    *,
    background: tuple[int, int, int, int],
    shape: tuple[int, int, int, int],
    y: int,
    amplitude: int,
    transparent: bool = False,
) -> Image.Image:
    width, height = size
    image = Image.new(
        "RGBA",
        size,
        (0, 0, 0, 0) if transparent else background,
    )
    brush = ImageDraw.Draw(image)
    points = [(0, y)]
    for x in range(0, width + 1, 80):
        phase = (x // 80) % 4
        offset = (0, -amplitude, 0, amplitude)[phase]
        points.append((min(width, x), y + offset))
    points.extend([(width, height), (0, height)])
    brush.polygon(points, fill=shape)
    # Matching edge patches make source and render-scale seams deterministic.
    brush.rectangle((0, 0, 7, height), fill=background if not transparent else (0, 0, 0, 0))
    brush.rectangle(
        (width - 8, 0, width - 1, height),
        fill=background if not transparent else (0, 0, 0, 0),
    )
    if transparent:
        brush.polygon(points, fill=shape)
        edge_shape = [(0, y), (8, y), (8, height), (0, height)]
        brush.polygon(edge_shape, fill=shape)
        mirror_shape = [
            (width - 8, y),
            (width, y),
            (width, height),
            (width - 8, height),
        ]
        brush.polygon(mirror_shape, fill=shape)
    return image


def build(output: Path) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    specs = {
        "world-far.png": ((232, 222, 201, 255), (94, 110, 112, 255), 155, 18, False),
        "world-mid.png": ((0, 0, 0, 0), (67, 91, 76, 205), 176, 22, True),
        "world-ground.png": ((0, 0, 0, 0), (87, 72, 58, 255), 196, 4, True),
        "world-near.png": ((0, 0, 0, 0), (46, 66, 48, 230), 218, 16, True),
    }
    result: list[Path] = []
    for name, (background, shape, y, amplitude, transparent) in specs.items():
        path = output / name
        strip(
            (960, 270),
            background=background,
            shape=shape,
            y=y,
            amplitude=amplitude,
            transparent=transparent,
        ).save(path)
        result.append(path)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "workspace" / "public",
    )
    args = parser.parse_args()
    for path in build(args.output.resolve()):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
