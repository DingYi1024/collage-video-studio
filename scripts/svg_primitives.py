#!/usr/bin/env python3
"""Render a deterministic, data-driven SVG subset with Pillow."""

from __future__ import annotations

import math
import re
from html import escape
from typing import Any

from PIL import Image, ImageDraw, ImageFont


class SvgPrimitiveError(RuntimeError):
    pass


TOKEN = re.compile(r"[MLHVZCQmlhvzcq]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")


def _font(size: int) -> ImageFont.ImageFont:
    for path in (
        "C:/Windows/Fonts/msyh.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, max(1, size))
        except OSError:
            continue
    return ImageFont.load_default()


def _curve(
    start: tuple[float, float],
    controls: list[tuple[float, float]],
    end: tuple[float, float],
    steps: int = 20,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for index in range(1, steps + 1):
        t = index / steps
        if len(controls) == 1:
            x = (
                (1 - t) ** 2 * start[0]
                + 2 * (1 - t) * t * controls[0][0]
                + t ** 2 * end[0]
            )
            y = (
                (1 - t) ** 2 * start[1]
                + 2 * (1 - t) * t * controls[0][1]
                + t ** 2 * end[1]
            )
        else:
            x = (
                (1 - t) ** 3 * start[0]
                + 3 * (1 - t) ** 2 * t * controls[0][0]
                + 3 * (1 - t) * t ** 2 * controls[1][0]
                + t ** 3 * end[0]
            )
            y = (
                (1 - t) ** 3 * start[1]
                + 3 * (1 - t) ** 2 * t * controls[0][1]
                + 3 * (1 - t) * t ** 2 * controls[1][1]
                + t ** 3 * end[1]
            )
        points.append((x, y))
    return points


def parse_path(value: str) -> tuple[list[tuple[float, float]], bool]:
    tokens = TOKEN.findall(value)
    if not tokens:
        raise SvgPrimitiveError("SVG path is empty")
    points: list[tuple[float, float]] = []
    cursor = (0.0, 0.0)
    start = cursor
    command = ""
    index = 0
    closed = False

    def number() -> float:
        nonlocal index
        if index >= len(tokens) or re.fullmatch(r"[A-Za-z]", tokens[index]):
            raise SvgPrimitiveError(f"SVG path {command} is missing coordinates")
        result = float(tokens[index])
        index += 1
        return result

    while index < len(tokens):
        token = tokens[index]
        if re.fullmatch(r"[A-Za-z]", token):
            command = token
            index += 1
        if not command:
            raise SvgPrimitiveError("SVG path must start with a command")
        relative = command.islower()
        upper = command.upper()
        if upper == "Z":
            points.append(start)
            cursor = start
            closed = True
            command = ""
            continue
        if upper == "H":
            x = number() + (cursor[0] if relative else 0)
            cursor = (x, cursor[1])
            points.append(cursor)
            continue
        if upper == "V":
            y = number() + (cursor[1] if relative else 0)
            cursor = (cursor[0], y)
            points.append(cursor)
            continue
        if upper in {"M", "L"}:
            x, y = number(), number()
            if relative:
                x += cursor[0]
                y += cursor[1]
            cursor = (x, y)
            points.append(cursor)
            if upper == "M":
                start = cursor
                command = "l" if relative else "L"
            continue
        if upper == "Q":
            values = [number() for _ in range(4)]
            if relative:
                values = [
                    values[0] + cursor[0], values[1] + cursor[1],
                    values[2] + cursor[0], values[3] + cursor[1],
                ]
            control = (values[0], values[1])
            end = (values[2], values[3])
            points.extend(_curve(cursor, [control], end))
            cursor = end
            continue
        if upper == "C":
            values = [number() for _ in range(6)]
            if relative:
                values = [
                    values[0] + cursor[0], values[1] + cursor[1],
                    values[2] + cursor[0], values[3] + cursor[1],
                    values[4] + cursor[0], values[5] + cursor[1],
                ]
            controls = [(values[0], values[1]), (values[2], values[3])]
            end = (values[4], values[5])
            points.extend(_curve(cursor, controls, end))
            cursor = end
            continue
        raise SvgPrimitiveError(f"unsupported SVG path command {command!r}")
    return points, closed


def _viewbox(svg: dict[str, Any], width: float, height: float) -> tuple[float, float, float, float]:
    raw = str(svg.get("viewBox", f"0 0 {width} {height}")).replace(",", " ").split()
    if len(raw) != 4:
        raise SvgPrimitiveError("svg.viewBox must contain four numbers")
    x, y, view_width, view_height = map(float, raw)
    if view_width <= 0 or view_height <= 0:
        raise SvgPrimitiveError("svg.viewBox size must be positive")
    return x, y, view_width, view_height


def render(
    primitive: dict[str, Any],
    canvas: tuple[int, int],
) -> Image.Image:
    svg = primitive.get("svg")
    if not isinstance(svg, dict):
        raise SvgPrimitiveError("data-svg primitive needs svg object")
    image = Image.new("RGBA", canvas, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    x = float(primitive.get("x", 0))
    y = float(primitive.get("y", 0))
    width = float(primitive.get("width", canvas[0]))
    height = float(primitive.get("height", canvas[1]))
    vx, vy, vw, vh = _viewbox(svg, width, height)
    scale = min(width / vw, height / vh)
    offset_x = x + (width - vw * scale) / 2 - vx * scale
    offset_y = y + (height - vh * scale) / 2 - vy * scale

    def point(item: tuple[float, float]) -> tuple[float, float]:
        return offset_x + item[0] * scale, offset_y + item[1] * scale

    for index, path in enumerate(svg.get("paths", []), 1):
        if not isinstance(path, dict):
            raise SvgPrimitiveError(f"svg.paths[{index}] must be an object")
        points, closed = parse_path(str(path.get("d", "")))
        transformed = [point(item) for item in points]
        fill = path.get("fill")
        stroke = path.get("stroke")
        if fill not in (None, "none") and closed:
            draw.polygon(transformed, fill=fill)
        if stroke not in (None, "none") and len(transformed) >= 2:
            draw.line(
                transformed,
                fill=stroke,
                width=max(1, round(float(path.get("strokeWidth", 1)) * scale)),
                joint="curve",
            )
    for circle in svg.get("circles", []):
        cx, cy = point((float(circle["cx"]), float(circle["cy"])))
        radius = float(circle["r"]) * scale
        draw.ellipse(
            (cx - radius, cy - radius, cx + radius, cy + radius),
            fill=circle.get("fill", "#ffffff"),
            outline=circle.get("stroke"),
        )
    for item in svg.get("text", []):
        tx, ty = point((float(item["x"]), float(item["y"])))
        draw.text(
            (tx, ty),
            str(item.get("value", "")),
            fill=item.get("fill", "#ffffff"),
            font=_font(round(float(item.get("size", 18)) * scale)),
        )
    return image


def to_svg_document(primitive: dict[str, Any]) -> str:
    svg = primitive.get("svg")
    if not isinstance(svg, dict):
        raise SvgPrimitiveError("data-svg primitive needs svg object")
    width = float(primitive.get("width", 100))
    height = float(primitive.get("height", 100))
    view_box = escape(str(svg.get("viewBox", f"0 0 {width:g} {height:g}")))
    elements: list[str] = []
    for path in svg.get("paths", []):
        elements.append(
            f'<path d="{escape(str(path.get("d", "")))}" '
            f'fill="{escape(str(path.get("fill", "none")))}" '
            f'stroke="{escape(str(path.get("stroke", "none")))}" '
            f'stroke-width="{float(path.get("strokeWidth", 1)):g}"/>'
        )
    for circle in svg.get("circles", []):
        elements.append(
            f'<circle cx="{float(circle["cx"]):g}" cy="{float(circle["cy"]):g}" '
            f'r="{float(circle["r"]):g}" fill="{escape(str(circle.get("fill", "#fff")))}"/>'
        )
    for item in svg.get("text", []):
        elements.append(
            f'<text x="{float(item["x"]):g}" y="{float(item["y"]):g}" '
            f'fill="{escape(str(item.get("fill", "#fff")))}" '
            f'font-size="{float(item.get("size", 18)):g}">'
            f'{escape(str(item.get("value", "")))}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}" '
        f'width="{width:g}" height="{height:g}">{"".join(elements)}</svg>'
    )
