#!/usr/bin/env python3
"""Create the deterministic transparent paper layers used by the dynamic demo."""

from __future__ import annotations

import json
import math
import random
import shutil
import sys
from pathlib import Path
from typing import Callable

from PIL import Image, ImageChops, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parent
SKILL_ROOT = ROOT.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import layer_compositor  # noqa: E402


WIDTH, HEIGHT = 720, 1280
CREAM = "#f4ead5"
PAPER = "#fff8e8"
BLUE = "#164e96"
BLUE_2 = "#2877c7"
RED = "#e64b2e"
RED_2 = "#ff7658"
CHARCOAL = "#282827"
TAUPE = "#b9aa91"


def blank() -> Image.Image:
    return Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))


def paper_texture(image: Image.Image, seed: int, strength: int = 18) -> Image.Image:
    random.seed(seed)
    alpha = image.getchannel("A")
    noise = Image.effect_noise((WIDTH, HEIGHT), 18).point(
        lambda value: max(0, min(255, int(abs(value - 128) * strength / 16)))
    )
    mask = ImageChops.multiply(alpha, noise)
    grain = Image.new("RGBA", image.size, (35, 28, 20, 0))
    grain.putalpha(mask)
    return Image.alpha_composite(image, grain)


def shadowed(draw_fn: Callable[[ImageDraw.ImageDraw, tuple[int, int]], None],
             seed: int) -> Image.Image:
    shadow = blank()
    draw_fn(ImageDraw.Draw(shadow), (7, 11))
    shadow = shadow.filter(ImageFilter.GaussianBlur(9))
    layer = blank()
    layer.alpha_composite(shadow)
    draw_fn(ImageDraw.Draw(layer), (0, 0))
    return paper_texture(layer, seed)


def background(seed: int, night: bool = False) -> Image.Image:
    base = Image.new("RGBA", (WIDTH, HEIGHT), CREAM)
    draw = ImageDraw.Draw(base)
    random.seed(seed)
    for _ in range(1200):
        x, y = random.randrange(WIDTH), random.randrange(HEIGHT)
        tone = random.choice(((96, 75, 47, 10), (255, 255, 255, 16)))
        draw.point((x, y), fill=tone)
    sky_color = "#d7d1c5" if night else "#efe4ce"
    draw.rectangle((0, 0, WIDTH, 720), fill=sky_color)
    for index, x in enumerate(range(-25, WIDTH + 40, 65)):
        h = 160 + ((index * 57 + seed) % 270)
        color = "#77736d" if night else ("#cbbca3" if index % 2 else "#ded1ba")
        draw.rectangle((x, 720 - h, x + 56, 720), fill=color)
        for wy in range(720 - h + 22, 700, 34):
            for wx in range(x + 12, x + 48, 18):
                draw.rectangle((wx, wy, wx + 6, wy + 12),
                               fill="#eee1c9" if night else "#a9987e")
    return paper_texture(base, seed + 101, 11)


def tree_layer(x: int, ground_y: int, scale: float, seed: int,
               color: str = BLUE) -> Image.Image:
    def draw_tree(draw: ImageDraw.ImageDraw, offset: tuple[int, int]) -> None:
        ox, oy = offset
        trunk_w = int(34 * scale)
        draw.polygon([
            (x - trunk_w // 2 + ox, ground_y + oy),
            (x + trunk_w // 2 + ox, ground_y + oy),
            (x + 10 + ox, int(ground_y - 280 * scale) + oy),
            (x - 8 + ox, int(ground_y - 280 * scale) + oy),
        ], fill="#5b5147" if offset == (0, 0) else (0, 0, 0, 90))
        if offset == (0, 0):
            draw.line((x, ground_y - 230 * scale, x - 90 * scale,
                       ground_y - 360 * scale), fill="#5b5147", width=max(5, int(13 * scale)))
            draw.line((x, ground_y - 220 * scale, x + 90 * scale,
                       ground_y - 350 * scale), fill="#5b5147", width=max(5, int(13 * scale)))
        rng = random.Random(seed)
        for _ in range(24):
            cx = x + int(rng.uniform(-145, 145) * scale)
            cy = ground_y - int(rng.uniform(300, 470) * scale)
            radius = int(rng.uniform(42, 76) * scale)
            fill = (0, 0, 0, 85) if offset != (0, 0) else color
            draw.ellipse((cx - radius + ox, cy - radius + oy,
                          cx + radius + ox, cy + radius + oy), fill=fill)
    return shadowed(draw_tree, seed)


def sun_layer(x: int, y: int, radius: int, seed: int) -> Image.Image:
    def draw_sun(draw: ImageDraw.ImageDraw, offset: tuple[int, int]) -> None:
        ox, oy = offset
        fill = (0, 0, 0, 75) if offset != (0, 0) else RED
        for angle in range(0, 360, 30):
            radians = math.radians(angle)
            inner = radius + 12
            outer = radius + 58
            px = x + math.cos(radians) * inner
            py = y + math.sin(radians) * inner
            qx = x + math.cos(radians - 0.08) * outer
            qy = y + math.sin(radians - 0.08) * outer
            rx = x + math.cos(radians + 0.08) * outer
            ry = y + math.sin(radians + 0.08) * outer
            draw.polygon([(px + ox, py + oy), (qx + ox, qy + oy),
                          (rx + ox, ry + oy)], fill=fill)
        draw.ellipse((x - radius + ox, y - radius + oy,
                      x + radius + ox, y + radius + oy), fill=fill)
    return shadowed(draw_sun, seed)


def waves_layer(xs: list[int], top: int, bottom: int, seed: int,
                color: str = RED, width: int = 12) -> Image.Image:
    def draw_waves(draw: ImageDraw.ImageDraw, offset: tuple[int, int]) -> None:
        ox, oy = offset
        fill = (0, 0, 0, 70) if offset != (0, 0) else color
        for index, x in enumerate(xs):
            points = []
            for y in range(top, bottom + 1, 8):
                px = x + math.sin((y - top) / 34 + index) * 13
                points.append((px + ox, y + oy))
            draw.line(points, fill=fill, width=width, joint="curve")
    return shadowed(draw_waves, seed)


def droplets_layer(points: list[tuple[int, int]], seed: int) -> Image.Image:
    def draw_drops(draw: ImageDraw.ImageDraw, offset: tuple[int, int]) -> None:
        ox, oy = offset
        fill = (0, 0, 0, 65) if offset != (0, 0) else BLUE_2
        for x, y in points:
            draw.polygon([(x + ox, y - 22 + oy), (x - 12 + ox, y + 7 + oy),
                          (x + 12 + ox, y + 7 + oy)], fill=fill)
            draw.ellipse((x - 12 + ox, y - 5 + oy, x + 12 + ox, y + 17 + oy),
                         fill=fill)
    return shadowed(draw_drops, seed)


def people_layer(people: list[tuple[int, int, str]], seed: int) -> Image.Image:
    def draw_people(draw: ImageDraw.ImageDraw, offset: tuple[int, int]) -> None:
        ox, oy = offset
        for x, y, color in people:
            fill = (0, 0, 0, 65) if offset != (0, 0) else color
            draw.ellipse((x - 10 + ox, y - 54 + oy, x + 10 + ox, y - 34 + oy),
                         fill=fill)
            draw.rounded_rectangle((x - 12 + ox, y - 35 + oy,
                                    x + 12 + ox, y + 6 + oy), 7, fill=fill)
            draw.line((x - 6 + ox, y + oy, x - 14 + ox, y + 38 + oy),
                      fill=fill, width=7)
            draw.line((x + 6 + ox, y + oy, x + 14 + ox, y + 38 + oy),
                      fill=fill, width=7)
    return shadowed(draw_people, seed)


def arrows_layer(points: list[tuple[int, int]], direction: str,
                 seed: int, color: str) -> Image.Image:
    def draw_arrows(draw: ImageDraw.ImageDraw, offset: tuple[int, int]) -> None:
        ox, oy = offset
        fill = (0, 0, 0, 70) if offset != (0, 0) else color
        sign = -1 if direction == "up" else 1
        for x, y in points:
            end_y = y + sign * 120
            draw.line((x + ox, y + oy, x + ox, end_y + oy), fill=fill, width=12)
            draw.polygon([
                (x + ox, end_y + sign * 22 + oy),
                (x - 22 + ox, end_y - sign * 8 + oy),
                (x + 22 + ox, end_y - sign * 8 + oy),
            ], fill=fill)
    return shadowed(draw_arrows, seed)


def save_pack(pack_id: str, layers: list[tuple],
              duration: float = 4.0) -> None:
    target = ROOT / "source-media" / "layers" / pack_id
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    records = []
    for spec in layers:
        layer_id, image, z, role, keyframes, *rest = spec
        motion = rest[0] if rest else {}
        filename = f"{layer_id}.png"
        image.save(target / filename, optimize=True)
        record = {
            "id": layer_id,
            "path": filename,
            "z": z,
            "role": role,
            "easing": "catmull-rom" if len(keyframes) >= 3 else "linear",
            "keyframes": keyframes,
        }
        record.update(motion)
        records.append(record)
    manifest = {
        "version": 1,
        "id": pack_id,
        "canvas": {
            "width": WIDTH,
            "height": HEIGHT,
            "fps": 30,
            "duration_s": duration,
            "oversample": 2,
            "motion_blur_samples": 1,
            "shutter": 0.5,
        },
        "quality": {"min_layers": 6, "min_animated_layers": 4},
        "layers": records,
    }
    manifest_path = target / "layers.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    errors, warnings, stats = layer_compositor.validate_manifest(manifest_path)
    if errors:
        raise RuntimeError(f"{pack_id}: {errors}")
    for warning in warnings:
        print(f"WARNING {pack_id}: {warning}")
    keyframe_dir = ROOT / "source-media" / "keyframes"
    keyframe_dir.mkdir(parents=True, exist_ok=True)
    layer_compositor.render_frame(manifest_path, 0.0).convert("RGB").save(
        keyframe_dir / f"{pack_id}.png", optimize=True
    )
    print(f"{pack_id}: {stats['layers']} layers, {stats['animated_layers']} animated")


def kf(t: float, **values: float) -> dict:
    return {"t": t, **values}


def shot_one() -> None:
    def grounds(draw: ImageDraw.ImageDraw, offset: tuple[int, int]) -> None:
        ox, oy = offset
        shadow = offset != (0, 0)
        draw.polygon([(0 + ox, 690 + oy), (360 + ox, 690 + oy),
                      (360 + ox, 1280 + oy), (0 + ox, 1280 + oy)],
                     fill=(0, 0, 0, 60) if shadow else "#d7e7ef")
        draw.polygon([(360 + ox, 690 + oy), (720 + ox, 690 + oy),
                      (720 + ox, 1280 + oy), (360 + ox, 1280 + oy)],
                     fill=(0, 0, 0, 60) if shadow else CHARCOAL)
        if not shadow:
            for y in range(750, 1260, 110):
                draw.rectangle((342, y, 378, y + 58), fill=PAPER)
    grounds_layer = shadowed(grounds, 11)
    layers = [
        ("background", background(1), 0, "background",
         [kf(0, scale=1.01), kf(4, scale=1.045)]),
        ("split-ground", grounds_layer, 1, "middle",
         [kf(0, x=-4), kf(4, x=4)]),
        ("people", people_layer([
            (155, 985, BLUE), (265, 1100, BLUE_2), (465, 1060, RED),
            (585, 960, RED_2),
        ], 12), 3, "objects",
         [kf(0, x=-16, y=0), kf(1.3, x=-7, y=-7),
          kf(2.7, x=8, y=3), kf(4, x=18, y=-4)]),
        ("cool-tree", tree_layer(165, 1000, 1.05, 13), 4, "foreground",
         [kf(0, rotation=-1.4, x=-5), kf(1, rotation=0.8, x=0),
          kf(2, rotation=-0.4, x=4), kf(3, rotation=1.0, x=0),
          kf(4, rotation=-1.4, x=-5)],
         {"loop": True, "phase_s": 0.17}),
        ("sun", sun_layer(570, 215, 72, 14), 5, "object",
         [kf(0, scale=0.96, rotation=-5), kf(0.7, scale=1.06, rotation=0),
          kf(1.4, scale=0.98, rotation=6), kf(2.1, scale=1.04, rotation=11),
          kf(2.8, scale=0.96, rotation=-5)],
         {"loop": True, "phase_s": 0.31}),
        ("heat-waves", waves_layer([430, 500, 570, 635], 470, 875, 15), 6, "object",
         [kf(0, y=120, opacity=0.0, scale_y=0.78),
          kf(0.45, y=65, opacity=0.9, scale_y=0.92),
          kf(1.15, y=-40, opacity=0.75, scale_y=1.08),
          kf(1.7, y=-135, opacity=0.0, scale_y=1.2)],
         {"loop": True, "phase_s": 0.08}),
    ]
    save_pack("b01-s01", layers)


def shot_two() -> None:
    def table(draw: ImageDraw.ImageDraw, offset: tuple[int, int]) -> None:
        ox, oy = offset
        shade = (0, 0, 0, 60) if offset != (0, 0) else PAPER
        draw.rounded_rectangle((38 + ox, 610 + oy, 682 + ox, 1110 + oy), 28, fill=shade)
        if offset == (0, 0):
            draw.rectangle((55, 800, 348, 1050), fill="#d9e8ef")
            draw.rectangle((372, 800, 665, 1050), fill=CHARCOAL)
            draw.line((360, 640, 360, 1070), fill=TAUPE, width=5)
    def gauges(draw: ImageDraw.ImageDraw, offset: tuple[int, int]) -> None:
        ox, oy = offset
        for x, color, level in ((85, BLUE_2, 905), (635, RED, 825)):
            fill = (0, 0, 0, 60) if offset != (0, 0) else PAPER
            draw.rounded_rectangle((x - 24 + ox, 725 + oy, x + 24 + ox,
                                    1015 + oy), 20, fill=fill)
            if offset == (0, 0):
                draw.ellipse((x - 31, 970, x + 31, 1032), fill=color)
                draw.rectangle((x - 10, level, x + 10, 992), fill=color)
    def rings(draw: ImageDraw.ImageDraw, offset: tuple[int, int]) -> None:
        ox, oy = offset
        fill = (0, 0, 0, 60) if offset != (0, 0) else RED_2
        for radius in (35, 70, 110):
            draw.ellipse((515 - radius + ox, 915 - radius + oy,
                          515 + radius + ox, 915 + radius + oy),
                         outline=fill, width=13)
    layers = [
        ("background", background(21), 0, "background",
         [kf(0, scale=1.03, x=-8), kf(4, scale=1.03, x=8)]),
        ("experiment-table", shadowed(table, 22), 1, "middle",
         [kf(0, y=12), kf(4, y=-6)]),
        ("gauges", shadowed(gauges, 23), 2, "objects",
         [kf(0, scale=0.985), kf(0.9, scale=1.025),
          kf(1.8, scale=0.985)],
         {"loop": True, "phase_s": 0.22}),
        ("cool-tree", tree_layer(220, 925, 0.65, 24), 3, "foreground",
         [kf(0, rotation=-1.5, scale=0.97),
          kf(0.85, rotation=0.8, scale=1.02),
          kf(1.7, rotation=-0.3, scale=1.0),
          kf(2.55, rotation=1.1, scale=1.015),
          kf(3.4, rotation=-1.5, scale=0.97)],
         {"loop": True, "phase_s": 0.43}),
        ("sun", sun_layer(360, 230, 68, 25), 4, "object",
         [kf(0, scale=0.96, rotation=-4), kf(0.75, scale=1.06, rotation=2),
          kf(1.5, scale=0.96, rotation=8), kf(2.25, scale=1.03, rotation=2),
          kf(3.0, scale=0.96, rotation=-4)],
         {"loop": True, "phase_s": 0.12}),
        ("cool-droplets", droplets_layer([
            (155, 620), (215, 560), (280, 645), (325, 580),
        ], 26), 5, "object",
         [kf(0, y=105, opacity=0.0), kf(0.45, y=55, opacity=0.9),
          kf(1.15, y=-30, opacity=0.75), kf(1.75, y=-110, opacity=0.0)],
         {"loop": True, "phase_s": 0.56}),
        ("heat-rings", shadowed(rings, 27), 5, "object",
         [kf(0, scale=0.58, opacity=0.0), kf(0.35, scale=0.72, opacity=0.9),
          kf(1.1, scale=1.18, opacity=0.65),
          kf(1.6, scale=1.42, opacity=0.0)],
         {"loop": True, "phase_s": 0.21}),
        ("heat-waves", waves_layer([465, 525, 585], 510, 800, 28), 6, "object",
         [kf(0, y=95, opacity=0.0), kf(0.5, y=35, opacity=0.85),
          kf(1.2, y=-55, opacity=0.7), kf(1.8, y=-135, opacity=0.0)],
         {"loop": True, "phase_s": 0.73}),
    ]
    save_pack("b02-s01", layers)


def shot_three() -> None:
    def ground_blocks(draw: ImageDraw.ImageDraw, offset: tuple[int, int]) -> None:
        ox, oy = offset
        shadow = offset != (0, 0)
        left = (0, 0, 0, 65) if shadow else "#d6e3db"
        right = (0, 0, 0, 65) if shadow else "#4a4038"
        draw.polygon([(25 + ox, 700 + oy), (350 + ox, 700 + oy), (350 + ox, 1120 + oy),
                      (25 + ox, 1120 + oy)], fill=left)
        draw.polygon([(370 + ox, 700 + oy), (695 + ox, 700 + oy), (695 + ox, 1120 + oy),
                      (370 + ox, 1120 + oy)], fill=right)
        if not shadow:
            for y, color in ((830, "#b7d1d8"), (930, BLUE_2), (1020, BLUE)):
                draw.rectangle((25, y, 350, y + 58), fill=color)
            for y, color in ((830, "#8e4d37"), (930, "#a93427"), (1020, "#622d28")):
                draw.rectangle((370, y, 695, y + 58), fill=color)
    def roots(draw: ImageDraw.ImageDraw, offset: tuple[int, int]) -> None:
        ox, oy = offset
        fill = (0, 0, 0, 60) if offset != (0, 0) else BLUE
        for dx in (-105, -55, 0, 55, 105):
            draw.line((190 + ox, 705 + oy, 190 + dx + ox, 1010 + oy),
                      fill=fill, width=10)
    def hot_building(draw: ImageDraw.ImageDraw, offset: tuple[int, int]) -> None:
        ox, oy = offset
        fill = (0, 0, 0, 70) if offset != (0, 0) else CHARCOAL
        draw.rectangle((430 + ox, 465 + oy, 635 + ox, 800 + oy), fill=fill)
        if offset == (0, 0):
            for y in range(520, 745, 58):
                for x in range(465, 610, 52):
                    draw.rectangle((x, y, x + 18, y + 28), fill=RED_2)
    layers = [
        ("background", background(31, night=True), 0, "background",
         [kf(0, scale=1.0), kf(4, scale=1.035)]),
        ("ground-cutaway", shadowed(ground_blocks, 32), 1, "middle",
         [kf(0, y=35), kf(4, y=-18)]),
        ("roots", shadowed(roots, 33), 2, "object",
         [kf(0, scale_y=0.45, opacity=0.05),
          kf(1.35, scale_y=0.88, opacity=0.85),
          kf(2.65, scale_y=1.04, opacity=1),
          kf(4, scale_y=1.07, opacity=1)]),
        ("cool-tree", tree_layer(190, 720, 0.72, 34), 3, "foreground",
         [kf(0, rotation=-1.25), kf(0.95, rotation=0.75),
          kf(1.9, rotation=-0.35), kf(2.85, rotation=0.9),
          kf(3.8, rotation=-1.25)],
         {"loop": True, "phase_s": 0.29}),
        ("hot-building", shadowed(hot_building, 35), 3, "foreground",
         [kf(0, x=20, y=8), kf(4, x=-5, y=-8)]),
        ("sun-rays", arrows_layer([
            (425, 300), (500, 270), (575, 300), (650, 270),
        ], "down", 36, RED_2), 4, "object",
         [kf(0, y=-150, opacity=0.0), kf(0.45, y=-80, opacity=0.85),
          kf(1.15, y=25, opacity=0.7), kf(1.75, y=120, opacity=0.0)],
         {"loop": True, "phase_s": 0.16}),
        ("cool-vapor", droplets_layer([
            (95, 530), (155, 465), (225, 520), (290, 450),
        ], 37), 5, "object",
         [kf(0, y=100, opacity=0.0), kf(0.55, y=35, opacity=0.8),
          kf(1.35, y=-70, opacity=0.7), kf(2.0, y=-155, opacity=0.0)],
         {"loop": True, "phase_s": 0.62}),
        ("stored-heat", arrows_layer([
            (430, 1030), (500, 980), (570, 1040), (640, 970),
        ], "up", 38, RED), 5, "object",
         [kf(0, y=130, opacity=0.0), kf(0.5, y=60, opacity=0.9),
          kf(1.25, y=-55, opacity=0.75), kf(1.9, y=-175, opacity=0.0)],
         {"loop": True, "phase_s": 0.91}),
    ]
    save_pack("b03-s01", layers)


def shot_four() -> None:
    def district(draw: ImageDraw.ImageDraw, offset: tuple[int, int]) -> None:
        ox, oy = offset
        shadow = offset != (0, 0)
        fill = (0, 0, 0, 65) if shadow else "#e8dfca"
        draw.polygon([(50 + ox, 520 + oy), (665 + ox, 520 + oy), (710 + ox, 1120 + oy),
                      (20 + ox, 1120 + oy)], fill=fill)
        if not shadow:
            draw.polygon([(300, 520), (420, 520), (470, 1120), (250, 1120)],
                         fill=BLUE_2)
            for x, y, w, h in ((85, 570, 145, 225), (480, 600, 145, 210),
                               (70, 850, 165, 180), (490, 860, 150, 175)):
                draw.rectangle((x, y, x + w, y + h), fill=PAPER)
                draw.rectangle((x + 12, y - 18, x + w - 12, y + 4), fill="#d5e8ef")
                for wy in range(y + 42, y + h - 20, 48):
                    for wx in range(x + 26, x + w - 20, 42):
                        draw.rectangle((wx, wy, wx + 14, wy + 22), fill=BLUE)
    def plaza(draw: ImageDraw.ImageDraw, offset: tuple[int, int]) -> None:
        ox, oy = offset
        fill = (0, 0, 0, 55) if offset != (0, 0) else "#6bb8dd"
        draw.ellipse((445 + ox, 885 + oy, 630 + ox, 1040 + oy), fill=fill)
        if offset == (0, 0):
            for x in (485, 535, 585):
                draw.line((x, 970, x, 910), fill=PAPER, width=8)
                draw.ellipse((x - 7, 895, x + 7, 915), fill=PAPER)
    def bus(draw: ImageDraw.ImageDraw, offset: tuple[int, int]) -> None:
        ox, oy = offset
        fill = (0, 0, 0, 65) if offset != (0, 0) else RED
        draw.rounded_rectangle((315 + ox, 850 + oy, 405 + ox, 1050 + oy), 18, fill=fill)
        if offset == (0, 0):
            draw.rectangle((330, 875, 390, 925), fill="#bfe0ed")
            draw.ellipse((322, 1010, 342, 1030), fill=CHARCOAL)
            draw.ellipse((378, 1010, 398, 1030), fill=CHARCOAL)
    trees = blank()
    for index, (x, y, scale) in enumerate([
        (145, 760, 0.45), (255, 870, 0.38), (455, 755, 0.43),
        (555, 880, 0.38), (180, 1030, 0.34),
    ]):
        trees.alpha_composite(tree_layer(x, y, scale, 50 + index))
    layers = [
        ("background", background(41, night=True), 0, "background",
         [kf(0, scale=1.06, opacity=0.7), kf(4, scale=1.0, opacity=0.35)]),
        ("cool-district", shadowed(district, 42), 1, "middle",
         [kf(0, y=30, scale=0.97), kf(4, y=-10, scale=1.02)]),
        ("water-plaza", shadowed(plaza, 43), 2, "object",
         [kf(0, scale=0.3, opacity=0.05),
          kf(1.15, scale=0.86, opacity=0.85),
          kf(2.35, scale=1.03, opacity=1),
          kf(4, scale=1.07, opacity=1)]),
        ("tree-corridor", paper_texture(trees, 44), 3, "foreground",
         [kf(0, scale=0.5, opacity=0.1),
          kf(1.35, scale=0.83, opacity=0.78),
          kf(2.55, scale=1.02, opacity=1),
          kf(4, scale=1.045, opacity=1)]),
        ("bus", shadowed(bus, 45), 4, "object",
         [kf(0, y=170, x=-8, opacity=0.25),
          kf(1.25, y=98, x=2, opacity=0.7),
          kf(2.7, y=15, x=-3, opacity=1),
          kf(4, y=-60, x=6, opacity=1)]),
        ("people", people_layer([
            (110, 1080, BLUE), (220, 970, RED), (465, 1100, BLUE),
            (600, 1040, RED_2),
        ], 46), 5, "objects",
         [kf(0, x=-28, y=3, opacity=0.3),
          kf(1.2, x=-13, y=-6, opacity=0.65),
          kf(2.6, x=8, y=4, opacity=0.9),
          kf(4, x=30, y=-5, opacity=1)]),
        ("departing-heat", waves_layer([475, 545, 615], 285, 585, 47), 6, "object",
         [kf(0, x=0, y=0, opacity=1),
          kf(1.1, x=28, y=-55, rotation=3, opacity=0.85),
          kf(2.45, x=82, y=-130, rotation=8, opacity=0.45),
          kf(4, x=155, y=-225, rotation=14, opacity=0)]),
        ("sun", sun_layer(125, 205, 58, 48), 7, "object",
         [kf(0, scale=1.12, opacity=0.9, rotation=-4),
          kf(1.4, scale=1.0, opacity=0.82, rotation=1),
          kf(2.8, scale=0.84, opacity=0.68, rotation=5),
          kf(4, scale=0.7, opacity=0.52, rotation=9)]),
    ]
    save_pack("b04-s01", layers)


def main() -> int:
    shot_one()
    shot_two()
    shot_three()
    shot_four()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
