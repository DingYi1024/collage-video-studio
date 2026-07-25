#!/usr/bin/env python3
"""Split an RGBA sprite sheet into consistently alpha-trimmed cells."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image


class SpriteError(RuntimeError):
    pass


def split_sheet(
    source: Path,
    output_dir: Path,
    columns: int,
    rows: int,
    names: list[str],
    padding: int,
) -> list[Path]:
    with Image.open(source) as opened:
        sheet = opened.convert("RGBA")
    cell_width = sheet.width // columns
    cell_height = sheet.height // rows
    expected = columns * rows
    if len(names) != expected:
        raise SpriteError(f"expected {expected} names, received {len(names)}")
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for index, name in enumerate(names):
        column = index % columns
        row = index // columns
        left = column * cell_width
        top = row * cell_height
        right = sheet.width if column == columns - 1 else left + cell_width
        bottom = sheet.height if row == rows - 1 else top + cell_height
        sprite = sheet.crop((left, top, right, bottom))
        alpha_box = sprite.getchannel("A").getbbox()
        if not alpha_box:
            raise SpriteError(f"cell {index + 1} ({name}) contains no visible pixels")
        x0, y0, x1, y1 = alpha_box
        bounds = (
            max(0, x0 - padding),
            max(0, y0 - padding),
            min(sprite.width, x1 + padding),
            min(sprite.height, y1 + padding),
        )
        output = output_dir / f"{name}.png"
        sprite.crop(bounds).save(output)
        outputs.append(output)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description="Split and trim an RGBA sprite sheet.")
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--columns", type=int, required=True)
    parser.add_argument("--rows", type=int, default=1)
    parser.add_argument("--names", nargs="+", required=True)
    parser.add_argument("--padding", type=int, default=12)
    args = parser.parse_args()
    if args.columns <= 0 or args.rows <= 0 or args.padding < 0:
        raise SpriteError("columns/rows must be positive and padding cannot be negative")
    outputs = split_sheet(
        args.source,
        args.output_dir,
        args.columns,
        args.rows,
        args.names,
        args.padding,
    )
    for output in outputs:
        print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SpriteError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
