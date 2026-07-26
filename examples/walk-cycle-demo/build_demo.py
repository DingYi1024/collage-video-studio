#!/usr/bin/env python3
"""Build a deterministic 9:16 articulated-paper walk-cycle benchmark."""

from __future__ import annotations

import json
import math
import random
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
SKILL_ROOT = ROOT.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import layer_compositor  # noqa: E402


WIDTH = 720
HEIGHT = 1280
FPS = 30
DURATION = 3.2
HIP_X = 180
HIP_Y = 690
GROUND_Y = 920
THIGH = 135
SHIN = 135
ROOT_SPEED = 75

CREAM = "#ead9b7"
INK = "#17202a"
BLUE = "#245b78"
BLUE_LIGHT = "#7ea9b7"
RED = "#b74635"
GOLD = "#d6a62f"
MUTED = "#758087"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def blank() -> Image.Image:
    return Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))


def paper_texture(image: Image.Image, seed: int, amount: int = 9000) -> Image.Image:
    rng = random.Random(seed)
    overlay = blank()
    draw = ImageDraw.Draw(overlay)
    for _ in range(amount):
        x = rng.randrange(WIDTH)
        y = rng.randrange(HEIGHT)
        alpha = rng.randrange(4, 15)
        color = (25, 32, 38, alpha) if rng.random() < 0.55 else (255, 248, 220, alpha)
        draw.point((x, y), fill=color)
    overlay.putalpha(Image.composite(
        overlay.getchannel("A"),
        Image.new("L", (WIDTH, HEIGHT), 0),
        image.getchannel("A"),
    ))
    return Image.alpha_composite(image, overlay)


def background_layer() -> Image.Image:
    image = Image.new("RGBA", (WIDTH, HEIGHT), CREAM)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=CREAM)
    draw.ellipse((500, 130, 670, 300), fill="#d6ad55")
    draw.polygon(
        [(0, 620), (130, 440), (245, 590), (360, 390), (520, 610), (720, 470), (720, 900), (0, 900)],
        fill="#b9b09d",
    )
    draw.polygon(
        [(0, 720), (180, 550), (300, 715), (445, 530), (620, 725), (720, 640), (720, 940), (0, 940)],
        fill="#8b9a9a",
    )
    for index, x in enumerate(range(35, 720, 92)):
        height = 115 + (index % 3) * 35
        draw.rectangle((x, 900 - height, x + 64, 900), fill=("#314c5b", "#536a70")[index % 2])
        for wy in range(900 - height + 18, 885, 28):
            draw.rectangle((x + 12, wy, x + 23, wy + 12), fill="#d5b45c")
            draw.rectangle((x + 38, wy, x + 49, wy + 12), fill="#d5b45c")
    return paper_texture(image, 910)


def ground_layer() -> Image.Image:
    image = blank()
    draw = ImageDraw.Draw(image)
    draw.polygon([(0, 900), (720, 875), (720, 1280), (0, 1280)], fill="#272d30")
    draw.line((0, GROUND_Y + 14, WIDTH, GROUND_Y - 10), fill="#d0b36c", width=5)
    for x in range(55, 700, 95):
        draw.polygon(
            [(x, 1030), (x + 55, 1026), (x + 73, 1062), (x + 14, 1067)],
            fill="#3b4345",
        )
    return paper_texture(image, 911, 5000)


def title_layer() -> Image.Image:
    image = blank()
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((42, 42, 678, 190), radius=18, fill="#101719e8")
    draw.rectangle((42, 42, 56, 190), fill=GOLD)
    draw.text((82, 68), "PLANTED FOOT TEST", font=font(38, True), fill="#f6edd8")
    draw.text((84, 126), "双脚交替落地 · 30 FPS · 9:16", font=font(24), fill="#d8c79f")
    return image


def torso_layer() -> Image.Image:
    image = blank()
    draw = ImageDraw.Draw(image)
    draw.ellipse((HIP_X - 46, HIP_Y - 285, HIP_X + 46, HIP_Y - 193), fill="#d2a073", outline=INK, width=5)
    draw.polygon(
        [
            (HIP_X - 64, HIP_Y - 205),
            (HIP_X + 60, HIP_Y - 205),
            (HIP_X + 76, HIP_Y - 22),
            (HIP_X + 22, HIP_Y + 8),
            (HIP_X - 54, HIP_Y - 14),
        ],
        fill=BLUE,
        outline=INK,
    )
    draw.polygon(
        [(HIP_X - 6, HIP_Y - 205), (HIP_X + 28, HIP_Y - 205), (HIP_X + 7, HIP_Y - 80)],
        fill="#e8ddc3",
    )
    draw.polygon(
        [(HIP_X - 12, HIP_Y - 202), (HIP_X + 12, HIP_Y - 202), (HIP_X + 28, HIP_Y - 120), (HIP_X, HIP_Y - 91)],
        fill=RED,
    )
    draw.arc((HIP_X - 16, HIP_Y - 258, HIP_X + 38, HIP_Y - 218), 205, 345, fill=INK, width=4)
    draw.ellipse((HIP_X - 18, HIP_Y - 250, HIP_X - 8, HIP_Y - 240), fill=INK)
    draw.ellipse((HIP_X + 17, HIP_Y - 250, HIP_X + 27, HIP_Y - 240), fill=INK)
    draw.ellipse((HIP_X - 10, HIP_Y - 10, HIP_X + 10, HIP_Y + 10), fill=GOLD, outline=INK, width=3)
    return paper_texture(image, 912, 2200)


def limb_layer(pivot: tuple[int, int], length: int, width: int, color: str, seed: int) -> Image.Image:
    image = blank()
    draw = ImageDraw.Draw(image)
    x, y = pivot
    draw.line((x, y, x, y + length), fill=INK, width=width + 8)
    draw.line((x, y, x, y + length), fill=color, width=width)
    radius = width // 2 + 3
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=GOLD, outline=INK, width=3)
    draw.ellipse(
        (x - radius, y + length - radius, x + radius, y + length + radius),
        fill=color,
        outline=INK,
        width=3,
    )
    return paper_texture(image, seed, 900)


def foot_layer(pivot: tuple[int, int], color: str, seed: int) -> Image.Image:
    image = blank()
    draw = ImageDraw.Draw(image)
    x, y = pivot
    draw.polygon(
        [(x - 12, y - 15), (x + 17, y - 17), (x + 66, y + 3), (x + 61, y + 20), (x - 13, y + 17)],
        fill=color,
        outline=INK,
    )
    draw.ellipse((x - 13, y - 13, x + 13, y + 13), fill=GOLD, outline=INK, width=3)
    return paper_texture(image, seed, 700)


def shadow_layer() -> Image.Image:
    image = blank()
    draw = ImageDraw.Draw(image)
    draw.ellipse((HIP_X - 100, GROUND_Y - 4, HIP_X + 100, GROUND_Y + 35), fill="#080b0d66")
    return image


def smootherstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * value * (value * (value * 6 - 15) + 10)


def foot_target(side: str, time_s: float) -> tuple[float, float]:
    if side == "left":
        if time_s <= 0.8:
            return 190.0, GROUND_Y
        if time_s < 1.6:
            phase = (time_s - 0.8) / 0.8
            eased = smootherstep(phase)
            return 190 + 210 * eased, GROUND_Y - 62 * math.sin(math.pi * phase)
        if time_s <= 2.4:
            return 400.0, GROUND_Y
        phase = (time_s - 2.4) / 0.8
        eased = smootherstep(phase)
        return 400 + 160 * eased, GROUND_Y - 62 * math.sin(math.pi * phase)
    if time_s < 0.8:
        phase = time_s / 0.8
        eased = smootherstep(phase)
        return 250 + 50 * eased, GROUND_Y - 48 * math.sin(math.pi * phase)
    if time_s <= 1.6:
        return 300.0, GROUND_Y
    if time_s < 2.4:
        phase = (time_s - 1.6) / 0.8
        eased = smootherstep(phase)
        return 300 + 180 * eased, GROUND_Y - 62 * math.sin(math.pi * phase)
    return 480.0, GROUND_Y


def solve_leg(
    hip: tuple[float, float],
    ankle: tuple[float, float],
    bend: int,
) -> tuple[float, float, float]:
    dx = ankle[0] - hip[0]
    dy = ankle[1] - hip[1]
    distance = max(1e-6, math.hypot(dx, dy))
    distance = min(distance, THIGH + SHIN - 0.5)
    ux = dx / math.hypot(dx, dy)
    uy = dy / math.hypot(dx, dy)
    along = (THIGH * THIGH - SHIN * SHIN + distance * distance) / (2 * distance)
    height = math.sqrt(max(0.0, THIGH * THIGH - along * along))
    knee = (
        hip[0] + ux * along + bend * (-uy) * height,
        hip[1] + uy * along + bend * ux * height,
    )
    upper_world = math.degrees(math.atan2(knee[1] - hip[1], knee[0] - hip[0]))
    lower_world = math.degrees(math.atan2(ankle[1] - knee[1], ankle[0] - knee[0]))
    thigh_rotation = upper_world - 90
    shin_rotation = lower_world - upper_world
    foot_rotation = 90 - lower_world
    return thigh_rotation, shin_rotation, foot_rotation


def keyframe(time_s: float, **values: float | str) -> dict[str, float | str]:
    return {"t": round(time_s, 6), **values}


def build_manifest(layer_dir: Path) -> dict:
    frame_count = round(DURATION * FPS)
    times = [index / FPS for index in range(frame_count + 1)]
    root_frames = []
    shadow_frames = []
    left_thigh_frames = []
    left_shin_frames = []
    left_foot_frames = []
    right_thigh_frames = []
    right_shin_frames = []
    right_foot_frames = []
    left_arm_frames = []
    right_arm_frames = []
    for time_s in times:
        bob = -4.0 * abs(math.sin(math.pi * time_s / 0.8))
        root_x = ROOT_SPEED * time_s
        root_frames.append(keyframe(time_s, x=root_x, y=bob, ease="linear"))
        shadow_frames.append(keyframe(
            time_s,
            scale_x=1 - 0.025 * abs(math.sin(math.pi * time_s / 0.8)),
            opacity=0.52,
            ease="linear",
        ))
        phase = 2 * math.pi * time_s / 1.6
        left_arm_frames.append(keyframe(time_s, rotation=17 * math.sin(phase), ease="linear"))
        right_arm_frames.append(keyframe(time_s, rotation=-17 * math.sin(phase), ease="linear"))
        for side, hip_offset, bend, containers in (
            (
                "left", -12, -1,
                (left_thigh_frames, left_shin_frames, left_foot_frames),
            ),
            (
                "right", 12, 1,
                (right_thigh_frames, right_shin_frames, right_foot_frames),
            ),
        ):
            target = foot_target(side, time_s)
            angles = solve_leg(
                (HIP_X + hip_offset + root_x, HIP_Y + bob),
                target,
                bend,
            )
            containers[0].append(keyframe(time_s, rotation=angles[0], ease="linear"))
            containers[1].append(keyframe(time_s, rotation=angles[1], ease="linear"))
            containers[2].append(keyframe(time_s, rotation=angles[2], ease="linear"))

    def rig_follow(parent: str) -> dict:
        return {
            "parent": parent,
            "space": "rig",
            "lag_s": 0,
            "inherit": {"x": 1, "y": 1, "rotation": 1},
        }

    contacts = []
    for foot, start, end in (
        ("left-foot", 0.0, 0.8),
        ("right-foot", 0.8, 1.6),
        ("left-foot", 1.6, 2.4),
        ("right-foot", 2.4, 3.2),
    ):
        for property_name in ("x", "y"):
            contacts.append({
                "layer": foot,
                "property": property_name,
                "start_s": start,
                "end_s": end,
                "tolerance": 1.5,
            })

    return {
        "version": 1,
        "id": "walk-cycle-demo",
        "canvas": {
            "width": WIDTH,
            "height": HEIGHT,
            "fps": FPS,
            "duration_s": DURATION,
            "oversample": 2,
            "motion_blur_samples": 1,
            "shutter": 0.5,
        },
        "quality": {
            "min_layers": 10,
            "min_animated_layers": 9,
            "directed_motion": True,
            "motion_audit": {
                "sample_fps": 30,
                "max_speed_px_s": 1700,
                "max_rotation_deg_s": 900,
                "max_scale_per_s": 3,
                "max_opacity_per_s": 8,
            },
        },
        "direction": {
            "primary_action": "a full-body paper walker crosses with alternating planted feet",
            "physical_cause": "hip travel is transferred through two joint chains into each planted foot",
            "primary_layers": [
                "walker-root", "left-thigh", "left-shin", "left-foot",
                "right-thigh", "right-shin", "right-foot",
            ],
            "motion_density": "high",
            "phases": [
                {"name": "anticipation", "start_s": 0, "end_s": 0.4},
                {"name": "action", "start_s": 0.4, "end_s": 2.8},
                {"name": "settle", "start_s": 2.8, "end_s": 3.2},
            ],
            "contacts": contacts,
            "secondary_responses": [
                {
                    "layers": ["walker-shadow"],
                    "driven_by": "walker-root",
                    "reason": "the ground shadow follows horizontal body travel but not hip bob",
                }
            ],
        },
        "layers": [
            {
                "id": "background", "path": "background.png", "z": 0,
                "keyframes": [{"t": 0}, {"t": DURATION}],
            },
            {
                "id": "ground", "path": "ground.png", "z": 1,
                "keyframes": [{"t": 0}, {"t": DURATION}],
            },
            {
                "id": "walker-shadow", "path": "shadow.png", "z": 2,
                "motion_class": "effect",
                "follow": {
                    "parent": "walker-root",
                    "lag_s": 0,
                    "inherit": {"x": 1},
                },
                "keyframes": shadow_frames,
            },
            {
                "id": "right-thigh", "path": "right-thigh.png", "z": 3,
                "pivot": [HIP_X + 12, HIP_Y], "motion_class": "hinged-part",
                "follow": rig_follow("walker-root"), "keyframes": right_thigh_frames,
            },
            {
                "id": "right-shin", "path": "right-shin.png", "z": 3,
                "pivot": [HIP_X + 12, HIP_Y + THIGH], "motion_class": "hinged-part",
                "follow": rig_follow("right-thigh"), "keyframes": right_shin_frames,
            },
            {
                "id": "right-foot", "path": "right-foot.png", "z": 3,
                "pivot": [HIP_X + 12, HIP_Y + THIGH + SHIN], "motion_class": "hinged-part",
                "follow": rig_follow("right-shin"), "keyframes": right_foot_frames,
            },
            {
                "id": "right-arm", "path": "right-arm.png", "z": 4,
                "pivot": [HIP_X + 44, HIP_Y - 178], "motion_class": "hinged-part",
                "follow": rig_follow("walker-root"), "keyframes": right_arm_frames,
            },
            {
                "id": "walker-root", "path": "torso.png", "z": 5,
                "pivot": [HIP_X, HIP_Y], "motion_class": "rigid-body",
                "keyframes": root_frames,
            },
            {
                "id": "left-thigh", "path": "left-thigh.png", "z": 6,
                "pivot": [HIP_X - 12, HIP_Y], "motion_class": "hinged-part",
                "follow": rig_follow("walker-root"), "keyframes": left_thigh_frames,
            },
            {
                "id": "left-shin", "path": "left-shin.png", "z": 6,
                "pivot": [HIP_X - 12, HIP_Y + THIGH], "motion_class": "hinged-part",
                "follow": rig_follow("left-thigh"), "keyframes": left_shin_frames,
            },
            {
                "id": "left-foot", "path": "left-foot.png", "z": 6,
                "pivot": [HIP_X - 12, HIP_Y + THIGH + SHIN], "motion_class": "hinged-part",
                "follow": rig_follow("left-shin"), "keyframes": left_foot_frames,
            },
            {
                "id": "left-arm", "path": "left-arm.png", "z": 7,
                "pivot": [HIP_X - 42, HIP_Y - 178], "motion_class": "hinged-part",
                "follow": rig_follow("walker-root"), "keyframes": left_arm_frames,
            },
            {
                "id": "title", "path": "title.png", "z": 20,
                "keyframes": [{"t": 0}, {"t": DURATION}],
            },
        ],
        "rigs": [
            {
                "id": "full-body-walker",
                "type": "articulated-paper",
                "root": "walker-root",
                "parts": [
                    "walker-root",
                    "left-arm", "right-arm",
                    "left-thigh", "left-shin", "left-foot",
                    "right-thigh", "right-shin", "right-foot",
                ],
                "locomotion": {
                    "root_axis": "x",
                    "feet": ["left-foot", "right-foot"],
                    "min_stride_px": 220,
                    "min_contact_s": 0.7,
                    "max_double_support_s": 0.02,
                    "max_plant_drift_px": 2,
                },
            }
        ],
    }


def save_assets(layer_dir: Path) -> None:
    layer_dir.mkdir(parents=True, exist_ok=True)
    assets = {
        "background.png": background_layer(),
        "ground.png": ground_layer(),
        "title.png": title_layer(),
        "torso.png": torso_layer(),
        "shadow.png": shadow_layer(),
        "left-thigh.png": limb_layer((HIP_X - 12, HIP_Y), THIGH, 34, BLUE, 920),
        "left-shin.png": limb_layer((HIP_X - 12, HIP_Y + THIGH), SHIN, 30, BLUE_LIGHT, 921),
        "left-foot.png": foot_layer((HIP_X - 12, HIP_Y + THIGH + SHIN), BLUE_LIGHT, 922),
        "right-thigh.png": limb_layer((HIP_X + 12, HIP_Y), THIGH, 32, MUTED, 923),
        "right-shin.png": limb_layer((HIP_X + 12, HIP_Y + THIGH), SHIN, 28, "#9a8264", 924),
        "right-foot.png": foot_layer((HIP_X + 12, HIP_Y + THIGH + SHIN), "#9a8264", 925),
        "left-arm.png": limb_layer((HIP_X - 42, HIP_Y - 178), 115, 25, BLUE_LIGHT, 926),
        "right-arm.png": limb_layer((HIP_X + 44, HIP_Y - 178), 115, 25, MUTED, 927),
    }
    for name, image in assets.items():
        image.save(layer_dir / name, optimize=True)


def make_evidence(manifest_path: Path, result_dir: Path) -> None:
    result_dir.mkdir(parents=True, exist_ok=True)
    times = (0.2, 0.8, 1.4, 2.0, 2.8)
    frames = []
    for time_s in times:
        frame = layer_compositor.render_frame(manifest_path, time_s)
        frames.append(ImageOps.fit(frame.convert("RGB"), (270, 480)))
    strip = Image.new("RGB", (270 * len(frames), 480), CREAM)
    for index, frame in enumerate(frames):
        strip.paste(frame, (index * 270, 0))
    strip.save(result_dir / "walk-strip.jpg", quality=92, optimize=True)
    frames[2].save(result_dir / "poster.jpg", quality=94, optimize=True)


def main() -> int:
    generated = ROOT / "generated"
    if generated.exists():
        shutil.rmtree(generated)
    layer_dir = generated / "layers"
    result_dir = ROOT / "result"
    result_dir.mkdir(parents=True, exist_ok=True)
    save_assets(layer_dir)
    manifest = build_manifest(layer_dir)
    manifest_path = layer_dir / "layers.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    errors, warnings, stats = layer_compositor.validate_manifest(manifest_path)
    if errors or warnings:
        raise RuntimeError(
            f"walk manifest failed: errors={errors} warnings={warnings} stats={stats}"
        )
    audit = layer_compositor.audit_motion_continuity(manifest)
    if audit["issues"]:
        raise RuntimeError(f"walk audit failed: {audit}")
    (result_dir / "audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    layer_compositor.render_manifest(manifest_path, result_dir / "walk-cycle.mp4")
    make_evidence(manifest_path, result_dir)
    print(
        f"PASS: {stats['layers']} layers · {stats['animated_layers']} animated · "
        f"{audit['rig_followers']} rig joints · "
        f"{audit['plant_intervals']} planted intervals"
    )
    print(f"video: {result_dir / 'walk-cycle.mp4'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
