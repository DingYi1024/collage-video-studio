#!/usr/bin/env python3
"""Create six directed-motion paper layer packages for the Musk demo."""

from __future__ import annotations

import json
import random
import shutil
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
SKILL_ROOT = ROOT.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import layer_compositor  # noqa: E402


WIDTH, HEIGHT = 960, 540
DURATION = 4.0
GENERATED = ROOT / "source-media" / "generated"
PLATES = {
    1: (GENERATED / "wealth-summit.png", (0.00, 0.64)),
    2: (GENERATED / "early-internet-payments.png", (0.00, 0.64)),
    3: (GENERATED / "early-internet-payments.png", (0.35, 1.00)),
    4: (GENERATED / "all-in-scale-up.png", (0.00, 0.64)),
    5: (GENERATED / "all-in-scale-up.png", (0.35, 1.00)),
    6: (GENERATED / "wealth-summit.png", (0.00, 1.00)),
}
CREAM = "#eee0c2"
IVORY = "#f6ecd6"
CHARCOAL = "#202426"
BLUE = "#163f62"
BLUE_LIGHT = "#5f8fa5"
RED = "#a84438"
GOLD = "#d7a94b"
GRAY = "#7a7b78"


def blank() -> Image.Image:
    return Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))


def kf(time_s: float, **values: Any) -> dict[str, Any]:
    return {"t": time_s, **values}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def paper_texture(image: Image.Image, seed: int, strength: int = 12) -> Image.Image:
    rng = random.Random(seed)
    alpha = image.getchannel("A")
    noise_size = (max(1, WIDTH // 8), max(1, HEIGHT // 8))
    noise = Image.new("L", noise_size)
    noise.putdata([
        rng.randrange(256) for _ in range(noise_size[0] * noise_size[1])
    ])
    noise = noise.resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR)
    noise = noise.point(
        lambda value: max(0, min(255, round(abs(value - 128) * strength / 11)))
    )
    mask = ImageChops.multiply(alpha, noise)
    grain = Image.new("RGBA", image.size, (38, 30, 22, 0))
    grain.putalpha(mask)
    return Image.alpha_composite(image, grain)


def paper_shape(
    draw_fn: Any,
    seed: int,
    shadow: tuple[int, int] = (6, 8),
) -> Image.Image:
    face = blank()
    draw_fn(ImageDraw.Draw(face))
    alpha = face.getchannel("A").filter(ImageFilter.GaussianBlur(4.5))
    shadow_layer = blank()
    shadow_color = Image.new("RGBA", face.size, (15, 14, 13, 0))
    shadow_color.putalpha(alpha.point(lambda value: round(value * 0.34)))
    shadow_layer.alpha_composite(shadow_color, shadow)
    return paper_texture(Image.alpha_composite(shadow_layer, face), seed)


def background(index: int) -> Image.Image:
    source_path, horizontal_window = PLATES[index]
    if not source_path.is_file():
        raise RuntimeError(f"missing generated background plate: {source_path}")
    source = Image.open(source_path).convert("RGBA")
    left = round(source.width * horizontal_window[0])
    right = round(source.width * horizontal_window[1])
    source = source.crop((left, 0, right, source.height))
    image = ImageOps.fit(
        source,
        (WIDTH, HEIGHT),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    tint = {
        1: (9, 28, 49, 18),
        2: (239, 222, 186, 12),
        3: (23, 60, 92, 12),
        4: (20, 19, 18, 22),
        5: (232, 208, 155, 10),
        6: (14, 34, 56, 14),
    }[index]
    return Image.alpha_composite(image, Image.new("RGBA", image.size, tint))


def title_card(year: str, title: str, accent: str = GOLD) -> Image.Image:
    def draw(drawer: ImageDraw.ImageDraw) -> None:
        drawer.rounded_rectangle(
            (36, 30, 340, 120), radius=8, fill=(29, 31, 31, 235)
        )
        drawer.rectangle((36, 30, 47, 120), fill=accent)
        drawer.text((66, 42), year, font=font(30, True), fill=IVORY)
        drawer.text((66, 79), title, font=font(20, True), fill=CREAM)
    return paper_shape(draw, seed=sum(ord(c) for c in year + title), shadow=(5, 7))


def foreground_frame(seed: int) -> Image.Image:
    def draw(drawer: ImageDraw.ImageDraw) -> None:
        drawer.polygon(
            [(0, 512), (180, 501), (365, 520), (620, 500), (960, 513), (960, 540), (0, 540)],
            fill=(29, 28, 26, 205),
        )
        drawer.polygon(
            [(0, 0), (0, 24), (190, 15), (380, 25), (570, 11), (760, 20), (960, 9), (960, 0)],
            fill=(244, 234, 213, 150),
        )
    return paper_shape(draw, seed, shadow=(0, 0))


def paper_vignette(seed: int) -> Image.Image:
    image = blank()
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, HEIGHT), outline=(20, 19, 18, 92), width=18)
    draw.rectangle((18, 18, WIDTH - 18, HEIGHT - 18), outline=(244, 232, 207, 36), width=3)
    return paper_texture(image, seed, strength=7)


def bar_layer(x: int, bottom: int, width: int, height: int, color: str, seed: int) -> Image.Image:
    return paper_shape(
        lambda d: d.rounded_rectangle(
            (x, bottom - height, x + width, bottom), radius=5, fill=color
        ),
        seed,
    )


def coin_layer(x: int, y: int, radius: int, seed: int) -> Image.Image:
    def draw(drawer: ImageDraw.ImageDraw) -> None:
        drawer.ellipse((x - radius, y - radius, x + radius, y + radius), fill=GOLD)
        drawer.ellipse(
            (x - radius + 7, y - radius + 7, x + radius - 7, y + radius - 7),
            outline=(248, 226, 158, 230),
            width=3,
        )
    return paper_shape(draw, seed)


def envelope_layer(x: int, y: int, width: int, height: int, seed: int) -> Image.Image:
    def draw(drawer: ImageDraw.ImageDraw) -> None:
        drawer.rounded_rectangle((x, y, x + width, y + height), radius=7, fill=IVORY)
        drawer.line((x, y, x + width / 2, y + height * 0.58, x + width, y), fill=GRAY, width=3)
        drawer.ellipse(
            (x + width * 0.42, y + height * 0.43, x + width * 0.58, y + height * 0.66),
            fill=RED,
        )
    return paper_shape(draw, seed)


def route_sprite(progress: int) -> Image.Image:
    points = [(154, 372), (272, 314), (405, 348), (520, 270), (650, 300)]
    image = blank()
    draw = ImageDraw.Draw(image)
    draw.line(points[: max(2, progress + 1)], fill=RED, width=9, joint="curve")
    for point in points[: max(2, progress + 1)]:
        draw.ellipse(
            (point[0] - 8, point[1] - 8, point[0] + 8, point[1] + 8),
            fill=IVORY,
            outline=RED,
            width=4,
        )
    return paper_texture(image, 300 + progress)


def rocket_layer(x: int, y: int, scale: float = 1.0) -> Image.Image:
    def draw(drawer: ImageDraw.ImageDraw) -> None:
        w, h = int(52 * scale), int(150 * scale)
        drawer.polygon(
            [(x, y - h), (x - w // 2, y - h + 45), (x - w // 2, y - 24),
             (x + w // 2, y - 24), (x + w // 2, y - h + 45)],
            fill=IVORY,
        )
        drawer.polygon(
            [(x - w // 2, y - 48), (x - w, y - 5), (x - w // 2, y - 18)],
            fill=RED,
        )
        drawer.polygon(
            [(x + w // 2, y - 48), (x + w, y - 5), (x + w // 2, y - 18)],
            fill=RED,
        )
        drawer.ellipse((x - 10, y - h + 50, x + 10, y - h + 70), fill=BLUE)
    return paper_shape(draw, 411 + x + y)


def car_layer(
    x: int,
    y: int,
    scale: float = 1.0,
    include_wheels: bool = True,
) -> Image.Image:
    def draw(drawer: ImageDraw.ImageDraw) -> None:
        w, h = int(170 * scale), int(60 * scale)
        drawer.rounded_rectangle((x - w // 2, y - h, x + w // 2, y), radius=16, fill=RED)
        drawer.polygon(
            [(x - w * 0.28, y - h), (x - w * 0.12, y - h * 1.58),
             (x + w * 0.24, y - h * 1.58), (x + w * 0.39, y - h)],
            fill=BLUE,
        )
        if include_wheels:
            for wheel_x in (x - w * 0.30, x + w * 0.30):
                drawer.ellipse(
                    (wheel_x - 16, y - 15, wheel_x + 16, y + 17),
                    fill=CHARCOAL,
                )
                drawer.ellipse(
                    (wheel_x - 7, y - 6, wheel_x + 7, y + 8),
                    fill=GRAY,
                )
    return paper_shape(draw, 510 + x + y)


def wheel_layer(x: int, y: int, radius: int, seed: int) -> Image.Image:
    def draw(drawer: ImageDraw.ImageDraw) -> None:
        drawer.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=CHARCOAL,
        )
        drawer.ellipse(
            (x - radius // 2, y - radius // 2, x + radius // 2, y + radius // 2),
            fill=GRAY,
        )
        drawer.line((x - radius + 4, y, x + radius - 4, y), fill=CREAM, width=3)
        drawer.line((x, y - radius + 4, x, y + radius - 4), fill=CREAM, width=3)
    return paper_shape(draw, seed)


def flame_layer(x: int, y: int, seed: int) -> Image.Image:
    def draw(drawer: ImageDraw.ImageDraw) -> None:
        drawer.polygon(
            [(x - 20, y), (x, y + 66), (x + 20, y)],
            fill=GOLD,
        )
        drawer.polygon(
            [(x - 9, y + 3), (x, y + 43), (x + 9, y + 3)],
            fill=RED,
        )
    return paper_shape(draw, seed, shadow=(3, 5))


def founder_torso_layer(x: int, hip_y: int, seed: int) -> Image.Image:
    def draw(drawer: ImageDraw.ImageDraw) -> None:
        drawer.ellipse(
            (x - 22, hip_y - 158, x + 22, hip_y - 114),
            fill=CHARCOAL,
        )
        drawer.polygon(
            [
                (x - 36, hip_y - 112),
                (x + 34, hip_y - 112),
                (x + 48, hip_y - 18),
                (x + 18, hip_y + 2),
                (x - 22, hip_y + 2),
                (x - 50, hip_y - 18),
            ],
            fill=BLUE,
        )
        drawer.polygon(
            [
                (x - 22, hip_y - 2),
                (x - 2, hip_y - 2),
                (x - 12, hip_y + 76),
                (x - 38, hip_y + 76),
            ],
            fill=CHARCOAL,
        )
        drawer.polygon(
            [
                (x + 2, hip_y - 2),
                (x + 22, hip_y - 2),
                (x + 38, hip_y + 76),
                (x + 12, hip_y + 76),
            ],
            fill=CHARCOAL,
        )
        drawer.rounded_rectangle(
            (x - 46, hip_y + 70, x - 10, hip_y + 82),
            radius=5,
            fill=CHARCOAL,
        )
        drawer.rounded_rectangle(
            (x + 10, hip_y + 70, x + 46, hip_y + 82),
            radius=5,
            fill=CHARCOAL,
        )
        drawer.polygon(
            [(x - 28, hip_y - 106), (x + 4, hip_y - 106), (x - 5, hip_y - 24)],
            fill=BLUE_LIGHT,
        )
    return paper_shape(draw, seed)


def limb_layer(
    start: tuple[int, int],
    end: tuple[int, int],
    width: int,
    color: str,
    seed: int,
) -> Image.Image:
    def draw(drawer: ImageDraw.ImageDraw) -> None:
        drawer.line((*start, *end), fill=color, width=width)
        radius = max(6, width // 2)
        for point in (start, end):
            drawer.ellipse(
                (
                    point[0] - radius,
                    point[1] - radius,
                    point[0] + radius,
                    point[1] + radius,
                ),
                fill=color,
            )
        pin_radius = max(4, width // 4)
        drawer.ellipse(
            (
                start[0] - pin_radius,
                start[1] - pin_radius,
                start[0] + pin_radius,
                start[1] + pin_radius,
            ),
            fill=GOLD,
        )
    return paper_shape(draw, seed)


def solar_layer(x: int, y: int) -> Image.Image:
    def draw(drawer: ImageDraw.ImageDraw) -> None:
        drawer.polygon([(x - 80, y - 50), (x + 60, y - 70), (x + 84, y), (x - 58, y + 20)], fill=BLUE)
        for row in range(1, 3):
            drawer.line((x - 73, y - 50 + row * 23, x + 76, y - 70 + row * 24), fill=CREAM, width=2)
        for col in range(1, 4):
            px = x - 80 + col * 36
            drawer.line((px, y - 56, px + 20, y + 12), fill=CREAM, width=2)
        drawer.line((x, y + 6, x, y + 52), fill=GRAY, width=6)
    return paper_shape(draw, 620 + x + y)


def note_layer(text: str, x: int, y: int, width: int, color: str = IVORY) -> Image.Image:
    def draw(drawer: ImageDraw.ImageDraw) -> None:
        drawer.rounded_rectangle((x, y, x + width, y + 64), radius=7, fill=color)
        drawer.text((x + 18, y + 16), text, font=font(24, True), fill=CHARCOAL)
    return paper_shape(draw, sum(ord(c) for c in text))


def record(
    layer_id: str,
    image: Image.Image,
    z: int,
    role: str,
    frames: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> tuple[Image.Image, dict[str, Any]]:
    return image, {
        "id": layer_id,
        "path": f"{layer_id}.png",
        "z": z,
        "role": role,
        "keyframes": frames or [kf(0), kf(DURATION)],
        **extra,
    }


def scene_layers(index: int) -> tuple[list[tuple[Image.Image, dict[str, Any]]], dict[str, Any]]:
    layers: list[tuple[Image.Image, dict[str, Any]]] = []
    bg_frames = [kf(0), kf(DURATION)]
    if index in {1, 3, 5}:
        bg_frames = [kf(0, x=-4, scale=1.025, ease="smootherstep"), kf(4, x=4, scale=1.045)]
    else:
        bg_frames = [kf(0, x=-20, scale=1.035), kf(4, x=20, scale=1.035)]
    layers.append(record(
        "background", background(index), 0, "background", bg_frames,
        motion_class="camera", easing="linear",
    ))
    layers.append(record("paper-vignette", paper_vignette(70 + index), 19, "texture"))

    titles = {
        1: ("路径", "不是工资，是股权"),
        2: ("1999", "ZIP2 退出"),
        3: ("2002", "PAYPAL 退出"),
        4: ("2008", "几乎全部再投入"),
        5: ("规模", "现金换成长期股权"),
        6: ("2021", "首次成为世界首富"),
    }
    layers.append(record("title-card", title_card(*titles[index]), 20, "label"))

    primary: list[str] = []
    action = ""
    cause = ""
    density = "medium"

    if index == 1:
        specs = [
            ("equity-bar-1", 646, 440, 64, 100, BLUE_LIGHT, 1.00),
            ("equity-bar-2", 724, 440, 64, 174, BLUE, 1.28),
            ("equity-bar-3", 802, 440, 64, 248, GOLD, 1.56),
        ]
        for order, (layer_id, x, bottom, width, height, color, start) in enumerate(specs):
            frames = [
                kf(0, y=height + 18),
                kf(start - 0.18, y=height + 18, ease="back-in"),
                kf(start + 0.68, y=0, ease="back-out"),
                kf(3.35, y=0),
                kf(4, y=0),
            ]
            layers.append(record(
                layer_id, bar_layer(x, bottom, width, height, color, 100 + order),
                6 + order, "primary-object", frames, motion_class="rigid-body",
            ))
            primary.append(layer_id)
        layers.append(record("frame", foreground_frame(101), 30, "foreground"))
        action = "three equity columns rise in sequence and settle"
        cause = "company ownership appreciates while the founder holds equity"

    elif index == 2:
        layers.append(record(
            "garage-label",
            note_layer("PALO ALTO", 142, 116, 198, BLUE_LIGHT),
            3,
            "evidence",
        ))
        layers.append(record(
            "directory-card",
            note_layer("CITY GUIDE", 720, 154, 196, IVORY),
            4,
            "evidence",
        ))
        route_paths: list[str] = []
        route_images: list[Image.Image] = []
        for progress in range(1, 5):
            route_paths.append(f"route-{progress}.png")
            route_images.append(route_sprite(progress))
        route_record = {
            "id": "zip-route",
            "path": route_paths[0],
            "z": 7,
            "role": "primary-object",
            "pose_sequence": {
                "states": [
                    {
                        "id": f"route-{i + 1}",
                        "at_s": 0.55 + i * 0.40,
                        "path": path,
                    }
                    for i, path in enumerate(route_paths)
                ],
                "playback": "once",
                "transition": "cut",
                "crossfade_s": 0,
            },
            "keyframes": [kf(0), kf(4)],
            "_extra_images": dict(zip(route_paths, route_images)),
        }
        layers.append((route_images[0], route_record))
        layers.append(record(
            "exit-note", note_layer("约 2200 万美元", 602, 352, 292, GOLD),
            9, "primary-object",
            [
                kf(0, x=-190, rotation=-5),
                kf(0.55, x=-190, rotation=-5, ease="ease-in"),
                kf(1.65, x=0, rotation=1.5, ease="back-out"),
                kf(2.05, x=0, rotation=0),
                kf(4, x=0, rotation=0),
            ],
            visibility={
                "initial": False,
                "events": [{"at_s": 0.48, "visible": True, "fade_s": 0.28}],
            },
            motion_class="rigid-body",
        ))
        layers.append(record(
            "map-tab", bar_layer(520, 438, 50, 86, RED, 208),
            5, "secondary-object",
            [kf(0, y=95), kf(1.4, y=95, ease="back-out"), kf(2.3, y=0), kf(4, y=0)],
            motion_class="rigid-body",
        ))
        layers.append(record("frame", foreground_frame(202), 30, "foreground"))
        primary = ["zip-route", "exit-note"]
        action = "map route assembles, then the exit proceeds card slides into place"
        cause = "the first company sale creates reusable investment capital"
        density = "low"

    elif index == 3:
        layers.append(record(
            "acquisition-envelope", envelope_layer(565, 280, 260, 142, 301),
            7, "primary-object",
            [
                kf(0, x=175, rotation=7),
                kf(0.48, x=195, rotation=9, ease="back-in"),
                kf(1.62, x=0, rotation=-2, ease="back-out"),
                kf(2.10, x=0, rotation=0),
                kf(4, x=0, rotation=0),
            ],
            pivot=[695, 351], motion_class="rigid-body",
        ))
        for order, (x, radius) in enumerate(((540, 30), (612, 27), (674, 23))):
            layer_id = f"paypal-coin-{order + 1}"
            layers.append(record(
                layer_id, coin_layer(x, 438, radius, 320 + order),
                8 + order, "secondary-object",
                [
                    kf(0, y=-110, opacity=0),
                    kf(1.35 + order * 0.22, y=-110, opacity=0, ease="ease-in"),
                    kf(2.20 + order * 0.22, y=8, opacity=1, ease="back-out"),
                    kf(2.55 + order * 0.22, y=0, opacity=1),
                    kf(4, y=0, opacity=1),
                ],
                motion_class="rigid-body",
            ))
        layers.append(record("frame", foreground_frame(303), 30, "foreground"))
        primary = ["acquisition-envelope"]
        action = "acquisition envelope slides in and three proceeds coins land"
        cause = "PayPal acquisition converts company equity into a larger cash stake"

    elif index == 4:
        layers.append(record("car-project", car_layer(242, 430, 0.74), 5, "project"))
        layers.append(record("rocket-project", rocket_layer(488, 420, 0.70), 5, "project"))
        layers.append(record("solar-project", solar_layer(752, 386), 5, "project"))
        layers.append(record(
            "founder-torso",
            founder_torso_layer(410, 420, 460),
            6,
            "primary-character",
            [
                kf(0, rotation=-2),
                kf(0.48, rotation=-3, ease="back-in"),
                kf(1.28, rotation=2, ease="back-out"),
                kf(1.92, rotation=0, ease="smootherstep"),
                kf(4, rotation=0),
            ],
            pivot=[410, 498],
            motion_class="rigid-body",
        ))
        layers.append(record(
            "founder-upper-arm",
            limb_layer((425, 322), (475, 345), 20, BLUE, 461),
            7,
            "primary-character-part",
            [
                kf(0, rotation=-22),
                kf(0.48, rotation=-30, ease="back-in"),
                kf(1.28, rotation=16, ease="back-out"),
                kf(1.92, rotation=0, ease="smootherstep"),
                kf(4, rotation=0),
            ],
            pivot=[425, 322],
            motion_class="hinged-part",
            follow={
                "parent": "founder-torso",
                "space": "rig",
                "lag_s": 0,
                "inherit": {"x": 1, "y": 1, "rotation": 1},
            },
        ))
        layers.append(record(
            "founder-forearm",
            limb_layer((475, 345), (520, 371), 18, BLUE_LIGHT, 462),
            7,
            "primary-character-part",
            [
                kf(0, rotation=20),
                kf(0.48, rotation=30, ease="back-in"),
                kf(1.28, rotation=-18, ease="back-out"),
                kf(1.92, rotation=0, ease="smootherstep"),
                kf(4, rotation=0),
            ],
            pivot=[475, 345],
            motion_class="hinged-part",
            follow={
                "parent": "founder-upper-arm",
                "space": "rig",
                "lag_s": 0,
                "inherit": {"x": 1, "y": 1, "rotation": 1},
            },
        ))
        primary.extend([
            "founder-torso",
            "founder-upper-arm",
            "founder-forearm",
        ])
        destinations = [(-220, 120), (0, -172), (230, 92)]
        for order, (x, y) in enumerate(destinations):
            layer_id = f"capital-{order + 1}"
            layers.append(record(
                layer_id, coin_layer(488, 374, 29, 420 + order),
                8 + order, "primary-object",
                [
                    kf(0, x=0, y=0),
                    kf(0.52 + order * 0.12, x=0, y=12, ease="back-in"),
                    kf(1.75 + order * 0.28, x=x, y=y, ease="ease-out"),
                    kf(2.18 + order * 0.28, x=x - (5 if x > 0 else -5), y=y, ease="back-out"),
                    kf(3.42, x=x, y=y),
                    kf(4, x=x, y=y),
                ],
                motion_class="rigid-body",
            ))
            primary.append(layer_id)
        layers.append(record("frame", foreground_frame(404), 30, "foreground"))
        action = "an articulated founder pushes one capital stack into three operating projects"
        cause = "sale proceeds are deliberately reinvested instead of kept as cash"

    elif index == 5:
        density = "high"
        layers.append(record(
            "factory-strip",
            note_layer("", 0, 486, 168, BLUE_LIGHT),
            4,
            "environment",
            looping_strip={
                "axis": "x",
                "speed_px_s": -44,
                "spacing_px": 8,
                "phase_px": 18,
            },
        ))
        layers.append(record(
            "scale-car", car_layer(260, 445, 0.80, include_wheels=False),
            7, "primary-object",
            [
                kf(0, x=-260),
                kf(0.52, x=-290, ease="back-in"),
                kf(1.55, x=0, ease="ease-out"),
                kf(1.90, x=8, ease="back-out"),
                kf(4, x=8),
            ],
            motion_class="rigid-body",
        ))
        for wheel_index, wheel_x in enumerate((219, 301), 1):
            layers.append(record(
                f"scale-car-wheel-{wheel_index}",
                wheel_layer(wheel_x, 446, 15, 570 + wheel_index),
                6, "secondary-response",
                [
                    kf(0, rotation=0),
                    kf(0.52, rotation=0),
                    kf(1.55, rotation=540, ease="linear"),
                    kf(1.90, rotation=560, ease="back-out"),
                    kf(4, rotation=560),
                ],
                pivot=[wheel_x, 446],
                motion_class="hinged-part",
                follow={
                    "parent": "scale-car",
                    "lag_s": 0,
                    "inherit": {"x": 1, "y": 1},
                },
            ))
        layers.append(record(
            "scale-rocket", rocket_layer(690, 438, 0.95), 8, "primary-object",
            [
                kf(0, y=115),
                kf(1.25, y=115, ease="back-in"),
                kf(2.58, y=-115, ease="ease-in-out"),
                kf(2.90, y=-105, ease="back-out"),
                kf(4, y=-105),
            ],
            motion_class="rigid-body",
        ))
        layers.append(record(
            "scale-rocket-flame",
            flame_layer(690, 433, 590),
            7,
            "secondary-response",
            [
                kf(0, scale_y=0.35, opacity=0),
                kf(1.05, scale_y=0.35, opacity=0),
                kf(1.55, scale_y=0.75, opacity=0.88, ease="smootherstep"),
                kf(2.38, scale_y=1.02, opacity=1, ease="smootherstep"),
                kf(3.02, scale_y=0.45, opacity=0, ease="smootherstep"),
                kf(4, scale_y=0.45, opacity=0),
            ],
            pivot=[690, 433],
            motion_class="hinged-part",
            follow={
                "parent": "scale-rocket",
                "lag_s": 0.04,
                "inherit": {"x": 1, "y": 1},
            },
        ))
        for order, height in enumerate((72, 116, 164)):
            layer_id = f"scale-bar-{order + 1}"
            layers.append(record(
                layer_id, bar_layer(780 + order * 52, 460, 38, height, (BLUE_LIGHT, BLUE, GOLD)[order], 530 + order),
                5 + order, "secondary-object",
                [
                    kf(0, y=height + 20),
                    kf(2.0 + order * 0.23, y=height + 20, ease="back-out"),
                    kf(3.05 + order * 0.20, y=0),
                    kf(4, y=0),
                ],
                motion_class="rigid-body",
            ))
        layers.append(record("frame", foreground_frame(505), 30, "foreground"))
        primary = ["scale-car", "scale-rocket"]
        action = "car crosses, rocket rises, and ownership blocks follow"
        cause = "operating scale and market value compound the retained equity"

    else:
        layers.append(record(
            "market-date",
            note_layer("JAN 2021", 760, 116, 184, IVORY),
            3,
            "evidence",
        ))
        layers.append(record(
            "rank-motifs",
            coin_layer(500, 250, 18, 777),
            4,
            "atmosphere",
            motif_field={
                "seed": 2021,
                "count": 7,
                "area": [180, 88, 600, 220],
                "scale_range": [0.55, 0.95],
                "drift_px": [4, 8],
                "spin_deg": 4,
                "stagger_s": 0.05,
            },
        ))
        positions = [
            (458, 454, 164, 58, CHARCOAL),
            (516, 396, 164, 58, BLUE),
            (574, 338, 164, 58, CHARCOAL),
            (632, 280, 164, 58, BLUE),
            (690, 222, 164, 58, GOLD),
        ]
        for order, (x, bottom, width, height, color) in enumerate(positions):
            layer_id = f"equity-step-{order + 1}"
            anticipation_end = 0.45 + order * 0.28
            arrival = 1.15 + order * 0.36
            layers.append(record(
                layer_id, bar_layer(x, bottom, width, height, color, 610 + order),
                6 + order, "primary-object",
                [
                    kf(0, y=96, opacity=0),
                    kf(anticipation_end, y=104, opacity=0.34, ease="back-in"),
                    kf(arrival, y=0, opacity=1, ease="back-out"),
                    kf(3.25, y=0, opacity=1),
                    kf(4, y=0, opacity=1),
                ],
                motion_class="rigid-body",
            ))
            primary.append(layer_id)
        rank = coin_layer(802, 134, 48, 680)
        rank_draw = ImageDraw.Draw(rank)
        rank_draw.text((787, 104), "1", font=font(48, True), fill=CHARCOAL)
        layers.append(record(
            "rank-token", rank, 14, "primary-object",
            [
                kf(0, y=-140, rotation=-12, opacity=0),
                kf(2.72, y=-140, rotation=-12, opacity=0, ease="back-out"),
                kf(3.28, y=0, rotation=3, opacity=1),
                kf(3.52, y=0, rotation=0, opacity=1),
                kf(4, y=0, rotation=0, opacity=1),
            ],
            pivot=[802, 134], motion_class="rigid-body",
        ))
        primary.append("rank-token")
        layers.append(record("frame", foreground_frame(606), 30, "foreground"))
        action = "equity staircase assembles from bottom to top and rank token stamps down"
        cause = "the 2020 Tesla rally raises the market value of retained shares"

    designed_holds = [
        {
            "start_s": {
                1: 3.20,
                2: 2.30,
                3: 3.20,
                4: 3.20,
                5: 3.20,
                6: 3.50,
            }[index],
            "end_s": 4.0,
            "reason": "hold the evidence long enough to read before the cut",
        }
    ]
    if index == 6:
        designed_holds.insert(0, {
            "start_s": 0.0,
            "end_s": 0.28,
            "reason": "brief empty-stage anticipation before the first step appears",
        })
    contacts = {
        1: [
            {
                "layer": "equity-bar-3", "property": "y",
                "start_s": 2.30, "end_s": 4.0, "tolerance": 0.5,
            }
        ],
        2: [
            {
                "layer": "exit-note", "property": "rotation",
                "start_s": 2.05, "end_s": 4.0, "tolerance": 0.5,
            }
        ],
        3: [
            {
                "layer": "paypal-coin-3", "property": "y",
                "start_s": 3.00, "end_s": 4.0, "tolerance": 0.5,
            }
        ],
        4: [
            {
                "layer": "capital-3", "property": "y",
                "start_s": 2.80, "end_s": 4.0, "tolerance": 0.5,
            },
            {
                "layer": "founder-torso", "property": "y",
                "start_s": 0.0, "end_s": 4.0, "tolerance": 0,
            },
            {
                "layer": "founder-torso", "property": "x",
                "start_s": 0.0, "end_s": 4.0, "tolerance": 0,
            }
        ],
        5: [
            {
                "layer": "scale-car", "property": "x",
                "start_s": 1.90, "end_s": 4.0, "tolerance": 0.5,
            },
            {
                "layer": "scale-rocket", "property": "y",
                "start_s": 2.90, "end_s": 4.0, "tolerance": 0.5,
            },
        ],
        6: [
            {
                "layer": "rank-token", "property": "rotation",
                "start_s": 3.52, "end_s": 4.0, "tolerance": 0.25,
            }
        ],
    }[index]
    direction = {
        "primary_action": action,
        "physical_cause": cause,
        "primary_layers": primary,
        "motion_density": density,
        "phases": [
            {"name": "anticipation", "start_s": 0.0, "end_s": 0.55},
            {"name": "action", "start_s": 0.55, "end_s": 3.20},
            {"name": "settle", "start_s": 3.20, "end_s": 4.0},
        ],
        "designed_holds": designed_holds,
        "contacts": contacts,
        "forbidden": [
            "continuous idle wobble",
            "whole-body morph",
            "unmotivated floating",
            "repeating more than two identical cycles",
        ],
    }
    if index == 5:
        direction["secondary_responses"] = [
            {
                "layers": ["scale-car-wheel-1", "scale-car-wheel-2"],
                "driven_by": "scale-car",
                "reason": "wheels rotate only while the car translates",
            },
            {
                "layers": ["scale-rocket-flame"],
                "driven_by": "scale-rocket",
                "reason": "the flame appears only during powered ascent",
            },
        ]
    return layers, direction


def save_styles() -> None:
    styles = ROOT / "source-media" / "styles"
    styles.mkdir(parents=True, exist_ok=True)
    base = background(4).convert("RGBA")
    options = {
        "archive-ledger": ((79, 104, 77, 52), "档案账本"),
        "industrial-paper": ((20, 63, 98, 35), "工业纸艺"),
        "market-poster": ((146, 48, 39, 48), "市场海报"),
    }
    for name, (tint, label) in options.items():
        image = Image.alpha_composite(base, Image.new("RGBA", base.size, tint))
        overlay = title_card("视觉方向", label)
        image = Image.alpha_composite(image, overlay)
        image.convert("RGB").save(styles / f"{name}.png", optimize=True)


def build_shot(index: int) -> None:
    pack_id = f"b{index:02d}-s01"
    target = ROOT / "source-media" / "layers" / pack_id
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    layers, direction = scene_layers(index)
    records: list[dict[str, Any]] = []
    for image, layer in layers:
        extra_images = layer.pop("_extra_images", {})
        image.save(target / layer["path"], optimize=True)
        for name, extra_image in extra_images.items():
            extra_image.save(target / name, optimize=True)
        records.append(layer)
    manifest = {
        "version": 2,
        "id": pack_id,
        "canvas": {
            "width": WIDTH,
            "height": HEIGHT,
            "fps": 30,
            "duration_s": DURATION,
            "oversample": 2,
            "motion_blur_samples": 1,
            "shutter": 0.45,
        },
        "quality": {
            "min_layers": 7,
            "min_animated_layers": 3,
            "paper_motion": True,
            "directed_motion": True,
            "motion_audit": {
                "sample_fps": 30,
                "max_speed_px_s": 2300,
                "max_rotation_deg_s": 900,
                "max_scale_per_s": 3,
                "max_opacity_per_s": 8,
            },
        },
        "direction": direction,
        "layers": records,
    }
    if index == 2:
        manifest["registration"] = {"members": ["zip-route"]}
    if index == 4:
        manifest["rigs"] = [
            {
                "id": "founder-arm-rig",
                "type": "articulated-paper",
                "root": "founder-torso",
                "parts": [
                    "founder-torso",
                    "founder-upper-arm",
                    "founder-forearm",
                ],
            }
        ]
    manifest_path = target / "layers.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    errors, warnings, stats = layer_compositor.validate_manifest(manifest_path)
    if errors or warnings:
        raise RuntimeError(
            f"{pack_id}: invalid directed layer pack: errors={errors}, warnings={warnings}"
        )
    keyframes = ROOT / "source-media" / "keyframes"
    keyframes.mkdir(parents=True, exist_ok=True)
    layer_compositor.render_frame(manifest_path, 2.65).convert("RGB").save(
        keyframes / f"{pack_id}.png", optimize=True
    )
    print(
        f"{pack_id}: {stats['layers']} layers, "
        f"{stats['animated_layers']} animated, primary={direction['primary_layers']}"
    )


def main() -> int:
    save_styles()
    for index in range(1, 7):
        build_shot(index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
