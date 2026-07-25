#!/usr/bin/env python3
"""Build the landscape demo with rigid paper parts and shot-safe pose changes."""

from __future__ import annotations

import json
import math
import random
import shutil
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parent
SKILL_ROOT = ROOT.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import layer_compositor  # noqa: E402


WIDTH, HEIGHT = 960, 540
GENERATED = ROOT / "source-media" / "generated"
BACKGROUND = GENERATED / "city-paper-landscape-v2.png"
CREAM = "#f4ead5"
BLUE = "#174f69"
BLUE_LIGHT = "#6fa9b5"
RED = "#c9553b"
CHARCOAL = "#292826"


def blank() -> Image.Image:
    return Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))


def kf(time_s: float, **values: float) -> dict[str, float]:
    return {"t": time_s, **values}


def paper_texture(image: Image.Image, seed: int, strength: int = 8) -> Image.Image:
    alpha = image.getchannel("A")
    noise = Image.effect_noise((WIDTH, HEIGHT), 22)
    noise = noise.point(
        lambda value: max(0, min(255, round(abs(value - 128) * strength / 12)))
    )
    mask = ImageChops.multiply(alpha, noise)
    grain = Image.new("RGBA", image.size, (42, 32, 23, 0))
    grain.putalpha(mask)
    return Image.alpha_composite(image, grain)


def background_plate(index: int) -> Image.Image:
    if not BACKGROUND.is_file():
        raise RuntimeError(f"missing generated landscape plate: {BACKGROUND}")
    source = Image.open(BACKGROUND).convert("RGBA")
    fitted = ImageOps.fit(
        source,
        (WIDTH, HEIGHT),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5),
    )
    tints = {
        1: (255, 244, 221, 10),
        2: (210, 239, 242, 16),
        3: (208, 221, 229, 25),
        4: (221, 242, 229, 18),
    }
    return Image.alpha_composite(fitted, Image.new("RGBA", fitted.size, tints[index]))


def soft_field(
    box: tuple[int, int, int, int],
    color: tuple[int, int, int, int],
    blur: int,
) -> Image.Image:
    image = blank()
    ImageDraw.Draw(image).ellipse(box, fill=color)
    return image.filter(ImageFilter.GaussianBlur(blur))


def heat_ribbons(index: int) -> Image.Image:
    image = blank()
    draw = ImageDraw.Draw(image)
    random.seed(40 + index)
    for column in range(4):
        x = 660 + column * 47
        points = []
        for step in range(8):
            y = 440 - step * 38
            wave = math.sin(step * 1.15 + column * 0.9) * 10
            points.append((x + round(wave), y))
        draw.line(points, fill=(201, 73, 48, 116), width=8)
        draw.line(
            [(x + 4, y + 2) for x, y in points],
            fill=(255, 221, 190, 75),
            width=2,
        )
    return paper_texture(image.filter(ImageFilter.GaussianBlur(0.55)), 44 + index)


def shade_patch(index: int) -> Image.Image:
    image = blank()
    draw = ImageDraw.Draw(image)
    draw.polygon(
        [(0, 320), (350, 280), (615, 420), (420, 540), (0, 540)],
        fill=(21, 80, 102, 63),
    )
    return paper_texture(image.filter(ImageFilter.GaussianBlur(7)), 50 + index)


def foreground_leaves(index: int) -> Image.Image:
    image = blank()
    draw = ImageDraw.Draw(image)
    random.seed(70 + index)
    for side in ("left", "right"):
        root_x = 15 if side == "left" else WIDTH - 15
        direction = 1 if side == "left" else -1
        for leaf_index in range(8):
            y = 525 - leaf_index * 28
            x = root_x + direction * (18 + (leaf_index % 3) * 18)
            draw.ellipse(
                (x - 22, y - 10, x + 22, y + 10),
                fill=(29, 94, 93, 160),
            )
    return paper_texture(image, 80 + index)


def paper_dust(index: int) -> Image.Image:
    image = blank()
    draw = ImageDraw.Draw(image)
    random.seed(90 + index)
    for _ in range(34):
        x = random.randint(80, WIDTH - 80)
        y = random.randint(70, HEIGHT - 80)
        radius = random.choice((1, 1, 2))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                     fill=(255, 247, 222, random.randint(42, 100)))
    return image.filter(ImageFilter.GaussianBlur(0.35))


def clean_character_source(name: str) -> Image.Image:
    source = Image.open(GENERATED / "designer" / f"{name}.png").convert("RGBA")
    if name == "look":
        # The generated sheet cell has two tiny neighboring fragments at its edges.
        source = source.crop((70, 0, min(560, source.width), source.height))
    bbox = source.getbbox()
    if bbox is None:
        raise RuntimeError(f"empty character sprite: {name}")
    return source.crop(bbox)


def place_character(
    name: str,
    center_x: int,
    bottom_y: int,
    target_height: int,
) -> tuple[Image.Image, list[float]]:
    source = clean_character_source(name)
    width = max(1, round(source.width * target_height / source.height))
    source = source.resize((width, target_height), Image.Resampling.LANCZOS)
    image = blank()
    image.alpha_composite(source, (center_x - width // 2, bottom_y - target_height))
    return image, [float(center_x), float(bottom_y)]


def shadow_from(image: Image.Image, dx: int = 8, dy: int = 10) -> Image.Image:
    alpha = image.getchannel("A").filter(ImageFilter.GaussianBlur(7))
    shadow = Image.new("RGBA", image.size, (20, 18, 16, 0))
    shadow.putalpha(alpha.point(lambda value: round(value * 0.28)))
    shifted = blank()
    shifted.alpha_composite(shadow, (dx, dy))
    return shifted


def butterfly_parts(
    center_x: int,
    center_y: int,
    target_width: int,
) -> tuple[dict[str, Image.Image], list[float]]:
    source = Image.open(GENERATED / "butterfly" / "open.png").convert("RGBA")
    bbox = source.getbbox()
    if bbox is None:
        raise RuntimeError("empty butterfly sprite")
    source = source.crop(bbox)
    source_center = source.width // 2
    alpha = source.getchannel("A")

    left_mask = alpha.copy()
    ImageDraw.Draw(left_mask).rectangle(
        (source_center + 12, 0, source.width, source.height), fill=0
    )
    right_mask = alpha.copy()
    ImageDraw.Draw(right_mask).rectangle(
        (0, 0, source_center - 12, source.height), fill=0
    )
    body_mask = Image.new("L", source.size, 0)
    body_draw = ImageDraw.Draw(body_mask)
    body_draw.rectangle(
        (source_center - 74, 0, source_center + 74, round(source.height * 0.43)),
        fill=255,
    )
    body_draw.rectangle(
        (source_center - 34, round(source.height * 0.30),
         source_center + 34, source.height),
        fill=255,
    )
    body_mask = ImageChops.multiply(body_mask, alpha)

    masks = {"left-wing": left_mask, "right-wing": right_mask, "body": body_mask}
    scale = target_width / source.width
    target_height = max(1, round(source.height * scale))
    target_size = (target_width, target_height)
    top_left = (center_x - target_width // 2, center_y - target_height // 2)
    result: dict[str, Image.Image] = {}
    for name, mask in masks.items():
        part = source.copy()
        part.putalpha(mask)
        part = part.resize(target_size, Image.Resampling.LANCZOS)
        canvas = blank()
        shadow_alpha = part.getchannel("A").filter(ImageFilter.GaussianBlur(2.2))
        shadow = Image.new("RGBA", part.size, (27, 24, 22, 0))
        shadow.putalpha(shadow_alpha.point(lambda value: round(value * 0.30)))
        canvas.alpha_composite(shadow, (top_left[0] + 3, top_left[1] + 5))
        canvas.alpha_composite(part, top_left)
        result[name] = canvas
    return result, [float(center_x), float(center_y)]


def butterfly_keyframes(
    side: str,
    perched: bool,
    phase: float,
) -> list[dict[str, float]]:
    frames: list[dict[str, float]] = []
    for step in range(17):
        time_s = step * 0.25
        angle = 2 * math.pi * (time_s / (1.35 if perched else 0.92)) + phase
        if side == "body":
            frames.append(kf(
                time_s,
                y=-1.7 * math.cos(angle),
                rotation=0.6 * math.sin(angle * 0.5),
            ))
            continue
        base = 31.0 if perched else 15.0
        amplitude = 7.0 if perched else 30.0
        rotation = base + amplitude * math.sin(angle)
        if side == "right-wing":
            rotation = -rotation
        frames.append(kf(time_s, rotation=rotation))
    return frames


def butterfly_motion(index: int, short_hop: bool) -> dict[str, Any]:
    if not short_hop:
        return {}
    directions = {
        1: [[-10, 4], [-2, -7], [6, -7], [15, -2]],
        2: [[10, 3], [2, -8], [-5, -6], [-14, -1]],
        4: [[-7, 2], [0, -4], [5, -5], [11, -1]],
    }
    return {
        "motion_path": {
            "start_s": 0,
            "end_s": 4,
            "points": directions.get(index, directions[1]),
            "easing": "ease-in-out",
        }
    }


def layer_record(
    layer_id: str,
    image: Image.Image,
    z: int,
    role: str,
    keyframes: list[dict[str, float]],
    **motion: Any,
) -> tuple[str, Image.Image, dict[str, Any]]:
    return layer_id, image, {
        "id": layer_id,
        "path": f"{layer_id}.png",
        "z": z,
        "role": role,
        "keyframes": keyframes,
        **motion,
    }


def build_shot(index: int) -> None:
    pack_id = f"b{index:02d}-s01"
    character_specs = {
        1: ("look", 310, 507, 330),
        2: ("look", 330, 508, 322),
        3: ("look", 300, 508, 326),
        4: ("plant", 350, 512, 315),
    }
    pose, character_x, character_bottom, character_height = character_specs[index]
    character, foot_pivot = place_character(
        pose, character_x, character_bottom, character_height
    )
    character_shadow = shadow_from(character)

    butterfly_specs = {
        1: (735, 190, 142, False, True),
        2: (760, 205, 128, False, True),
        3: (720, 215, 172, True, False),
        4: (750, 225, 106, True, True),
    }
    butterfly_x, butterfly_y, butterfly_width, perched, short_hop = (
        butterfly_specs[index]
    )
    butterfly, wing_pivot = butterfly_parts(
        butterfly_x, butterfly_y, butterfly_width
    )
    phase = index * 0.37
    shared_path = butterfly_motion(index, short_hop)

    background_motion = {
        1: [kf(0, x=-3, scale=1.025), kf(4, x=3, scale=1.045)],
        2: [kf(0, x=4, scale=1.04), kf(4, x=-4, scale=1.055)],
        3: [kf(0, y=2, scale=1.035), kf(4, y=-2, scale=1.05)],
        4: [kf(0, x=3, scale=1.05), kf(4, x=-3, scale=1.03)],
    }[index]
    character_motion = [
        kf(0, x=0, y=0, rotation=-0.25),
        kf(2, x=1.5, y=-1.0, rotation=0.35),
        kf(4, x=0, y=0, rotation=-0.2),
    ]
    heat_opacity = 0.9 if index in {1, 2, 3} else 0.45
    dust_motion = (
        [kf(0, x=-2, y=4, opacity=0.42),
         kf(2, x=3, y=-4, opacity=0.68),
         kf(3.55, x=-1, y=2, opacity=0.58),
         kf(4, x=8, y=-9, opacity=0.68)]
        if index == 1
        else [kf(0, x=-2, y=4, opacity=0.42),
              kf(2, x=3, y=-4, opacity=0.68),
              kf(4, x=-2, y=4, opacity=0.42)]
    )

    layers = [
        layer_record(
            "background", background_plate(index), 0, "background",
            background_motion, motion_class="camera", easing="smootherstep",
        ),
        layer_record(
            "cool-air", soft_field((30, 180, 610, 580), (40, 128, 150, 62), 48),
            1, "atmosphere",
            [kf(0, x=-7, opacity=0.58), kf(2, x=4, opacity=0.72),
             kf(4, x=-7, opacity=0.58)],
            motion_class="atmosphere", easing="catmull-rom",
        ),
        layer_record(
            "stored-warmth",
            soft_field((560, 175, 1005, 575), (205, 75, 47, 58), 55),
            2, "atmosphere",
            [kf(0, y=6, opacity=0.52), kf(2, y=-8, opacity=0.72),
             kf(4, y=6, opacity=0.52)],
            motion_class="atmosphere", easing="catmull-rom",
        ),
        layer_record(
            "shade", shade_patch(index), 3, "middle",
            [kf(0, x=-2, opacity=0.72), kf(2, x=3, opacity=0.84),
             kf(4, x=-2, opacity=0.72)],
            motion_class="rigid-body", easing="catmull-rom",
        ),
        layer_record(
            "heat-ribbons", heat_ribbons(index), 4, "effect",
            [kf(0, y=28, opacity=0.0),
             kf(0.55, y=10, opacity=heat_opacity),
             kf(2.2, y=-16, opacity=heat_opacity * 0.78),
             kf(4, y=-38, opacity=0.0)],
            motion_class="effect", easing="ease-in-out",
        ),
        layer_record(
            "character-shadow", character_shadow, 5, "shadow",
            character_motion, pivot=foot_pivot, motion_class="rigid-body",
            easing="smootherstep",
        ),
        layer_record(
            "character", character, 6, "character",
            character_motion, pivot=foot_pivot, motion_class="rigid-body",
            pose_change_policy="shot-cut", easing="smootherstep",
        ),
        layer_record(
            "butterfly-left-wing", butterfly["left-wing"], 7, "character-part",
            butterfly_keyframes("left-wing", perched, phase),
            pivot=wing_pivot, motion_class="hinged-part",
            easing="catmull-rom", **shared_path,
        ),
        layer_record(
            "butterfly-right-wing", butterfly["right-wing"], 8, "character-part",
            butterfly_keyframes("right-wing", perched, phase),
            pivot=wing_pivot, motion_class="hinged-part",
            easing="catmull-rom", **shared_path,
        ),
        layer_record(
            "butterfly-body", butterfly["body"], 9, "character-part",
            butterfly_keyframes("body", perched, phase),
            pivot=wing_pivot, motion_class="rigid-body",
            easing="catmull-rom", **shared_path,
        ),
        layer_record(
            "paper-dust", paper_dust(index), 10, "foreground",
            dust_motion,
            motion_class="atmosphere", easing="catmull-rom",
        ),
        layer_record(
            "foreground-leaves", foreground_leaves(index), 11, "foreground",
            [kf(0, rotation=-0.35), kf(2, rotation=0.35),
             kf(4, rotation=-0.35)],
            pivot=[WIDTH / 2, HEIGHT], motion_class="hinged-part",
            easing="catmull-rom",
        ),
    ]

    target = ROOT / "source-media" / "layers" / pack_id
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for _, image, record in layers:
        image.save(target / record["path"], optimize=True)
        records.append(record)
    manifest = {
        "version": 1,
        "id": pack_id,
        "canvas": {
            "width": WIDTH,
            "height": HEIGHT,
            "fps": 30,
            "duration_s": 4,
            "oversample": 2,
            "motion_blur_samples": 1,
            "shutter": 0.42,
        },
        "quality": {
            "min_layers": 8,
            "min_animated_layers": 7,
            "paper_motion": True,
        },
        "rigs": [{
            "id": "butterfly",
            "type": "hinged-paper",
            "parts": [
                "butterfly-left-wing",
                "butterfly-right-wing",
                "butterfly-body",
            ],
            "pivot": wing_pivot,
            "constraint": "body registration fixed; wings rotate only at roots",
        }],
        "layers": records,
    }
    manifest_path = target / "layers.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    errors, warnings, stats = layer_compositor.validate_manifest(manifest_path)
    if errors or warnings:
        raise RuntimeError(
            f"{pack_id}: invalid layer pack: errors={errors}, warnings={warnings}"
        )

    keyframe_dir = ROOT / "source-media" / "keyframes"
    keyframe_dir.mkdir(parents=True, exist_ok=True)
    layer_compositor.render_frame(manifest_path, 0.8).convert("RGB").save(
        keyframe_dir / f"{pack_id}.png", optimize=True
    )
    print(f"{pack_id}: {stats['layers']} layers, {stats['animated_layers']} animated")


def main() -> int:
    for index in range(1, 5):
        build_shot(index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
