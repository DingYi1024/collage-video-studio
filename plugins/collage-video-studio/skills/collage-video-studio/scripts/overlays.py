#!/usr/bin/env python3
"""Create transparent caption and watermark overlays with Pillow."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def font_candidates() -> list[Path]:
    windir = Path(os.environ.get("WINDIR", "C:/Windows"))
    return [
        windir / "Fonts/msyh.ttc",
        windir / "Fonts/arial.ttf",
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in font_candidates():
        if candidate.is_file():
            try:
                return ImageFont.truetype(str(candidate), size=size)
            except OSError:
                pass
    return ImageFont.load_default()


def wrap_text(text: str, width_px: int, font: ImageFont.ImageFont) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    draw = ImageDraw.Draw(Image.new("L", (1, 1)))
    lines: list[str] = []
    current = ""
    for char in text:
        trial = current + char
        box = draw.textbbox((0, 0), trial, font=font)
        if current and box[2] - box[0] > width_px:
            lines.append(current.rstrip())
            current = char.lstrip()
        else:
            current = trial
    if current:
        lines.append(current.rstrip())
    return lines[:3]


def render_caption(text: str, output: Path, width: int, height: int,
                   style: str = "clean") -> Path:
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font_size = max(34, int(height * 0.038))
    font = load_font(font_size)
    lines = wrap_text(text, int(width * 0.78), font)
    if not lines:
        layer.save(output)
        return output

    spacing = int(font_size * 0.34)
    boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    text_w = max(box[2] - box[0] for box in boxes)
    line_h = max(box[3] - box[1] for box in boxes)
    text_h = line_h * len(lines) + spacing * (len(lines) - 1)
    pad_x, pad_y = int(font_size * 0.65), int(font_size * 0.42)
    x0 = (width - text_w) // 2 - pad_x
    y0 = int(height * 0.82) - text_h // 2 - pad_y
    x1 = (width + text_w) // 2 + pad_x
    y1 = y0 + text_h + 2 * pad_y

    if style == "paper":
        fill, ink, outline = (244, 232, 199, 238), (25, 24, 22, 255), (25, 24, 22, 90)
    else:
        fill, ink, outline = (10, 10, 10, 190), (255, 255, 255, 255), (255, 255, 255, 35)
    draw.rounded_rectangle((x0, y0, x1, y1), radius=pad_y, fill=fill, outline=outline,
                           width=max(1, font_size // 24))
    y = y0 + pad_y
    for line, box in zip(lines, boxes):
        line_w = box[2] - box[0]
        draw.text(((width - line_w) // 2, y), line, font=font, fill=ink)
        y += line_h + spacing
    output.parent.mkdir(parents=True, exist_ok=True)
    layer.save(output)
    return output


def render_watermark(text: str, output: Path, width: int, height: int) -> Path:
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if text.strip():
        draw = ImageDraw.Draw(layer)
        font = load_font(max(18, int(height * 0.018)))
        box = draw.textbbox((0, 0), text, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        pad = max(12, int(height * 0.012))
        x, y = width - tw - 2 * pad, pad
        draw.rounded_rectangle((x - pad, y, width - pad, y + th + 2 * pad),
                               radius=pad // 2, fill=(0, 0, 0, 115))
        draw.text((x, y + pad), text, font=font, fill=(255, 255, 255, 210))
    output.parent.mkdir(parents=True, exist_ok=True)
    layer.save(output)
    return output
