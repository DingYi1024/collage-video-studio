#!/usr/bin/env python3
"""Build the V6 Musk wealth-path demo from three registered source sheets."""

from __future__ import annotations

import math
import shutil
import sys
import wave
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parent
SKILL_ROOT = ROOT.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import external_media  # noqa: E402
import production_protocol  # noqa: E402
import proof_system  # noqa: E402
import studio  # noqa: E402


WIDTH, HEIGHT, FPS = 1920, 1080, 30
SOURCE_DIR = ROOT / "source-media" / "v6"
DERIVED_DIR = ROOT / "media" / "v6-assets"
LAYER_DIR = ROOT / "media" / "layers-v6"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    raise RuntimeError("a Chinese TrueType font is required")


def chroma_alpha(source: Image.Image) -> Image.Image:
    rgba = source.convert("RGBA")
    pixels = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, _ = pixels[x, y]
            dominance = green - max(red, blue)
            if dominance >= 75 and green >= 145:
                alpha = 0
            elif dominance >= 25 and green >= 110:
                alpha = round(255 * (75 - dominance) / 50)
            else:
                alpha = 255
            if alpha < 255:
                spill = max(0, green - max(red, blue))
                green = max(0, green - round(spill * (1 - alpha / 255) * 0.9))
            pixels[x, y] = (red, green, blue, alpha)
    bbox = rgba.getchannel("A").getbbox()
    if bbox is None:
        raise RuntimeError("chroma extraction removed the whole sprite")
    return rgba.crop(bbox)


def split_sources() -> dict[str, Path]:
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}
    environments = Image.open(
        SOURCE_DIR / "career-environments-source.png"
    ).convert("RGB")
    mid_x, mid_y = environments.width // 2, environments.height // 2
    env_boxes = [
        (0, 0, mid_x - 5, mid_y - 5),
        (mid_x + 5, 0, environments.width, mid_y - 5),
        (0, mid_y + 5, mid_x - 5, environments.height),
        (mid_x + 5, mid_y + 5, environments.width, environments.height),
    ]
    for index, box in enumerate(env_boxes, 1):
        image = environments.crop(box).resize(
            (WIDTH, HEIGHT), Image.Resampling.LANCZOS
        )
        path = DERIVED_DIR / f"environment-{index}.jpg"
        image.save(path, quality=94, subsampling=0)
        outputs[f"environment-{index}"] = path

    poses = Image.open(
        SOURCE_DIR / "musk-career-poses-source.png"
    ).convert("RGBA")
    for index in range(4):
        left = round(index * poses.width / 4)
        right = round((index + 1) * poses.width / 4)
        sprite = chroma_alpha(poses.crop((left, 0, right, poses.height)))
        path = DERIVED_DIR / f"pose-{index + 1}.png"
        sprite.save(path)
        outputs[f"pose-{index + 1}"] = path

    props = Image.open(SOURCE_DIR / "career-props-source.png").convert("RGBA")
    names = (
        "computer",
        "map",
        "contract",
        "checks",
        "car",
        "rocket",
        "gears",
        "arrow",
    )
    for row in range(2):
        for column in range(4):
            index = row * 4 + column
            left = round(column * props.width / 4)
            right = round((column + 1) * props.width / 4)
            top = round(row * props.height / 2)
            bottom = round((row + 1) * props.height / 2)
            sprite = chroma_alpha(props.crop((left, top, right, bottom)))
            path = DERIVED_DIR / f"prop-{names[index]}.png"
            sprite.save(path)
            outputs[f"prop-{names[index]}"] = path
    return outputs


def texture_assets() -> dict[str, Path]:
    result: dict[str, Path] = {}
    ambient = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ambient)
    draw.rectangle((0, 0, WIDTH, 92), fill=(33, 27, 23, 120))
    draw.rectangle((0, HEIGHT - 72, WIDTH, HEIGHT), fill=(32, 25, 20, 135))
    draw.line((0, 96, WIDTH, 96), fill=(224, 199, 148, 90), width=3)
    path = DERIVED_DIR / "ambient-frame.png"
    ambient.save(path)
    result["ambient"] = path

    foreground = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(foreground)
    draw.polygon(
        ((0, 920), (210, 884), (390, 1080), (0, 1080)),
        fill=(225, 208, 170, 225),
    )
    draw.polygon(
        ((WIDTH, 770), (1725, 835), (1660, 1080), (WIDTH, 1080)),
        fill=(39, 53, 58, 220),
    )
    draw.line((60, 1010, 330, 950), fill=(151, 58, 45, 225), width=16)
    path = DERIVED_DIR / "foreground-scraps.png"
    foreground.save(path)
    result["foreground"] = path

    grain = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    pixels = grain.load()
    for y in range(0, HEIGHT, 3):
        for x in range(0, WIDTH, 3):
            value = (x * 17 + y * 31 + (x * y) % 97) % 37
            alpha = 12 if value < 9 else 0
            pixels[x, y] = (35, 24, 17, alpha)
    grain = grain.filter(ImageFilter.GaussianBlur(0.35))
    path = DERIVED_DIR / "paper-grain.png"
    grain.save(path)
    result["grain"] = path
    return result


def style_previews(environment: Path) -> dict[str, Path]:
    image = Image.open(environment).convert("RGB").resize((960, 540))
    previews = {
        "archive-ledger": ImageEnhance.Color(image).enhance(0.35),
        "industrial-paper": image,
        "market-poster": ImageEnhance.Contrast(
            ImageEnhance.Color(image).enhance(1.3)
        ).enhance(1.25),
    }
    result: dict[str, Path] = {}
    for theme_id, preview in previews.items():
        card = Image.new("RGB", (960, 540), "#e7dcc4")
        card.paste(preview, (0, 0))
        brush = ImageDraw.Draw(card)
        brush.rectangle((36, 394, 924, 506), fill=(27, 23, 20))
        brush.text(
            (62, 414),
            {
                "archive-ledger": "档案账本",
                "industrial-paper": "工业纸艺",
                "market-poster": "市场海报",
            }[theme_id],
            font=font(44, True),
            fill="#f5ecd8",
        )
        path = DERIVED_DIR / f"style-{theme_id}.jpg"
        card.save(path, quality=93)
        result[theme_id] = path
    return result


def make_music(duration_s: float) -> Path:
    path = ROOT / "media" / "audio" / "v6-music.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 48000
    frames = round(duration_s * sample_rate)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        block = bytearray()
        notes = (55.0, 65.41, 73.42, 82.41)
        for index in range(frames):
            time_s = index / sample_rate
            note = notes[min(len(notes) - 1, int(time_s // 8))]
            pulse = 0.5 + 0.5 * math.sin(2 * math.pi * 0.5 * time_s)
            tone = (
                math.sin(2 * math.pi * note * time_s) * 0.28
                + math.sin(2 * math.pi * note * 2 * time_s) * 0.08
            )
            paper_tick = (
                math.sin(2 * math.pi * 930 * time_s)
                * math.exp(-32 * (time_s % 2.0))
                * 0.055
            )
            value = max(-1, min(1, tone * pulse + paper_tick))
            sample = round(value * 32767 * 0.22)
            block.extend(int(sample).to_bytes(2, "little", signed=True) * 2)
            if len(block) >= 65536:
                output.writeframes(block)
                block.clear()
        if block:
            output.writeframes(block)
    return path


def responsive_overrides(
    subject_id: str,
    subject_layouts: dict[str, dict[str, Any]],
    prop_layouts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    sizes = {
        "16:9": (WIDTH, HEIGHT),
        "9:16": (1080, 1920),
        "1:1": (1080, 1080),
    }
    for aspect, (width, height) in sizes.items():
        title_y = 104 if aspect == "16:9" else 150
        result[aspect] = {
            "width": width,
            "height": height,
            "safe_zones": [{
                "id": "subtitle",
                "policy": "exclude",
                "rect": [round(width * 0.08), round(height * 0.80),
                         round(width * 0.84), round(height * 0.16)],
            }],
            "node_overrides": {
                "environment": {
                    "layout": {
                        "x": 0, "y": 0, "width": width, "height": height,
                        "fit": "cover",
                    }
                },
                "ambient-frame": {
                    "layout": {
                        "x": 0, "y": 0, "width": width, "height": height,
                        "fit": "stretch",
                    }
                },
                subject_id: {"layout": subject_layouts[aspect]},
                "context-prop": {"layout": prop_layouts[aspect]},
                "title": {
                    "primitive": {
                        "kind": "text",
                        "x": round(width * 0.07),
                        "y": title_y,
                        "width": round(width * 0.72),
                        "height": round(height * 0.16),
                        "font_size": 62 if aspect == "16:9" else 54,
                        "min_font_size": 34,
                        "bold": True,
                        "fill": "#f3ead5",
                        "background": "#211d1a",
                        "align": "left",
                    }
                },
                "foreground": {
                    "layout": {
                        "x": 0, "y": 0, "width": width, "height": height,
                        "fit": "stretch",
                    }
                },
                "grain": {
                    "layout": {
                        "x": 0, "y": 0, "width": width, "height": height,
                        "fit": "stretch",
                    }
                },
            },
        }
    return result


def shot_manifest(
    *,
    beat_id: str,
    shot_id: str,
    duration_s: float,
    environment: Path,
    pose: Path,
    prop: Path,
    texture: dict[str, Path],
    title: str,
    scale: str,
    pattern: str,
    environment_id: str,
    index: int,
    source_ids: list[str],
) -> dict[str, Any]:
    subject_id = f"musk-stage-{(index // 2) + 1}"
    subject_layouts = {
        "16:9": {
            "x": 1040 if index % 2 == 0 else 104,
            "y": 230 if scale != "wide" else 320,
            "width": 700 if scale != "detail" else 900,
            "height": 820 if scale != "wide" else 690,
            "fit": "contain",
        },
        "9:16": {
            "x": 120, "y": 600, "width": 840, "height": 1020, "fit": "contain"
        },
        "1:1": {
            "x": 470 if index % 2 == 0 else 40,
            "y": 260, "width": 580, "height": 760, "fit": "contain"
        },
    }
    prop_layouts = {
        "16:9": {
            "x": 160 if index % 2 == 0 else 1180,
            "y": 500,
            "width": 590,
            "height": 430,
            "fit": "contain",
        },
        "9:16": {
            "x": 180, "y": 1250, "width": 720, "height": 460, "fit": "contain"
        },
        "1:1": {
            "x": 80 if index % 2 == 0 else 620,
            "y": 650, "width": 440, "height": 350, "fit": "contain"
        },
    }
    text_primitive = {
        "kind": "text",
        "x": 134,
        "y": 104,
        "width": 1120,
        "height": 150,
        "text": title,
        "font_size": 62,
        "min_font_size": 38,
        "bold": True,
        "fill": "#f3ead5",
        "background": "#211d1a",
        "align": "left",
    }
    data_primitive = (
        {
            "kind": "timeline",
            "x": 132,
            "y": 820,
            "width": 1000,
            "height": 110,
            "items": [
                {"position": 0.08, "label": "1995", "color": "#d4523d"},
                {"position": 0.40, "label": "1999", "color": "#dfaa3f"},
                {"position": 0.69, "label": "2008", "color": "#4b7f98"},
                {"position": 0.94, "label": "2021", "color": "#efe1bd"},
            ],
        }
        if index in {0, 6}
        else {
            "kind": "bar-chart",
            "x": 120,
            "y": 704,
            "width": 520,
            "height": 230,
            "values": [22, 170, 420, 1000 + index * 110],
            "labels": ["A", "B", "C", "D"],
            "colors": ["#954337", "#c28c3f", "#426a76", "#e5d8ba"],
            "gap": 16,
        }
    )
    layers = [
        {
            "id": "environment",
            "path": str(environment.resolve()),
            "z": 0,
            "role": "rear",
            "depth": 0.15,
            "layout": {
                "x": 0, "y": 0, "width": WIDTH, "height": HEIGHT, "fit": "cover"
            },
            "keyframes": [
                {"t": 0, "x": -8, "scale": 1.025},
                {"t": duration_s, "x": 8, "scale": 1.055, "ease": "smootherstep"},
            ],
        },
        {
            "id": "ambient-frame",
            "path": str(texture["ambient"].resolve()),
            "z": 2,
            "role": "rear",
            "depth": 0.08,
            "layout": {
                "x": 0, "y": 0, "width": WIDTH, "height": HEIGHT, "fit": "stretch"
            },
            "keyframes": [{"t": 0}, {"t": duration_s}],
        },
        {
            "id": "context-prop",
            "path": str(prop.resolve()),
            "z": 7,
            "role": "mid",
            "depth": 0.55,
            "layout": prop_layouts["16:9"],
            "keyframes": [
                {"t": 0, "x": -70 if index % 2 == 0 else 70, "opacity": 0},
                {"t": 0.64, "x": 0, "opacity": 1, "ease": "smootherstep"},
                {"t": duration_s, "x": 10 if index % 2 == 0 else -10},
            ],
        },
        {
            "id": subject_id,
            "path": str(pose.resolve()),
            "z": 10,
            "role": "subject",
            "depth": 0.75,
            "layout": subject_layouts["16:9"],
            "keyframes": [
                {"t": 0, "y": 45, "scale": 0.96, "opacity": 0},
                {"t": 0.62, "y": 0, "scale": 1, "opacity": 1,
                 "ease": "smootherstep"},
                {"t": duration_s, "x": 14 if index % 2 == 0 else -14, "scale": 1.025},
            ],
        },
        {
            "id": "data",
            "z": 14,
            "role": "mid",
            "primitive": data_primitive,
            "keyframes": [
                {"t": 0, "x": -90, "opacity": 0},
                {"t": 0.72, "x": 0, "opacity": 1, "ease": "ease-out-cubic"},
                {"t": duration_s, "x": 5},
            ],
        },
        {
            "id": "title",
            "z": 18,
            "role": "mid",
            "primitive": text_primitive,
            "keyframes": [
                {"t": 0, "y": -42, "opacity": 0},
                {"t": 0.58, "y": 0, "opacity": 1, "ease": "smootherstep"},
                {"t": duration_s, "y": 0},
            ],
        },
        {
            "id": "foreground",
            "path": str(texture["foreground"].resolve()),
            "z": 24,
            "role": "front",
            "depth": 1.18,
            "layout": {
                "x": 0, "y": 0, "width": WIDTH, "height": HEIGHT, "fit": "stretch"
            },
            # Foreground scraps are an optical anchor. Camera parallax already
            # supplies depth, so keeping this plane still prevents every layer
            # from competing for attention.
            "keyframes": [{"t": 0}, {"t": duration_s}],
        },
        {
            "id": "grain",
            "path": str(texture["grain"].resolve()),
            "z": 30,
            "role": "front",
            "layout": {
                "x": 0, "y": 0, "width": WIDTH, "height": HEIGHT, "fit": "stretch"
            },
            "keyframes": [{"t": 0}, {"t": duration_s}],
        },
    ]
    package = LAYER_DIR / f"{beat_id}-{shot_id}"
    package.mkdir(parents=True, exist_ok=True)
    for layer in layers:
        if layer.get("path"):
            source = Path(layer["path"])
            destination = package / source.name
            if source.resolve() != destination.resolve():
                shutil.copy2(source, destination)
            layer["path"] = destination.name
    return {
        "version": 3,
        "id": f"{beat_id}-{shot_id}",
        "canvas": {
            "width": WIDTH,
            "height": HEIGHT,
            "fps": FPS,
            "duration_s": duration_s,
            "oversample": 1,
            "motion_blur_samples": 1,
            "background": "#171411",
        },
        "quality": {
            "min_layers": 8,
            "min_animated_layers": 5,
            "paper_motion": True,
            "directed_motion": True,
        },
        "creative": {
            "production_ready": True,
            "shot_scale": scale,
            "composition_pattern": pattern,
            "environment_id": environment_id,
            "source_artifact_ids": source_ids,
        },
        "direction": {
            "primary_action": "subject and evidence enter, settle, and remain readable",
            "physical_cause": "the narrated business event changes the ownership path",
            "primary_layers": [subject_id, "context-prop", "data"],
            "motion_density": "medium",
            "phases": [
                {"name": "anticipation", "start_s": 0,
                 "end_s": round(duration_s * 0.16, 3)},
                {"name": "action", "start_s": round(duration_s * 0.16, 3),
                 "end_s": round(duration_s * 0.78, 3)},
                {"name": "settle", "start_s": round(duration_s * 0.78, 3),
                 "end_s": duration_s},
            ],
            "designed_holds": [{
                "start_s": max(0, duration_s - 0.62),
                "end_s": duration_s,
                "reason": "read the proof before the edit",
            }],
            "forbidden": [
                "idle wobble",
                "teleporting subject",
                "unmotivated loop",
                "whole-frame flash",
            ],
        },
        "camera": {
            "keyframes": [
                {"t": 0, "x": 0, "y": 0, "scale": 1},
                {"t": duration_s, "x": 8, "y": -3, "scale": 1.025,
                 "ease": "smootherstep"},
            ]
        },
        "director_plans": responsive_overrides(
            subject_id, subject_layouts, prop_layouts
        ),
        "edit_points": [
            {
                "id": "setup",
                "at_s": 0.42,
                "target": subject_id,
                "action": "arrive",
            },
            {
                "id": "payoff",
                "at_s": round(duration_s * 0.72, 3),
                "target": "data",
                "action": "prove",
            },
        ],
        "proof_moments": [
            {"id": "action-readable", "at_s": round(duration_s * 0.56, 3),
             "checks": ["identity", "depth", "evidence"]},
            {"id": "final-readable", "at_s": round(duration_s * 0.88, 3),
             "checks": ["title", "data", "no occlusion"]},
        ],
        "layers": layers,
    }


def project_data() -> dict[str, Any]:
    themes = [
        {
            "id": "archive-ledger",
            "medium": "商业档案与账本纸张",
            "palette": "旧白、墨黑、会计绿、警示红",
            "typography": "档案标签",
            "texture": "复印噪点与票据孔",
            "composition": "证据板",
            "motion": "票据抽拉与金额落位",
        },
        {
            "id": "industrial-paper",
            "medium": "工业纸艺纪录片",
            "palette": "暖米白、炭黑、暗红、钴蓝",
            "typography": "克制现代黑体",
            "texture": "卡纸纤维与撕边",
            "composition": "人物、环境、证据三层",
            "motion": "关键帧滑入、落位、回稳",
            "film_style": {
                "subtitle_background": "rgba(31,25,20,.86)",
                "subtitle_color": "#fff6df",
            },
        },
        {
            "id": "market-poster",
            "medium": "高对比金融剪报",
            "palette": "黑、白、钴蓝、电光红",
            "typography": "粗数字与窄标题",
            "texture": "报纸网点与胶带",
            "composition": "数据优先",
            "motion": "图表上升与排名推移",
        },
    ]
    beats = [
        (
            "b01",
            "一九九五年，马斯克和弟弟创办 Zip2；他睡在办公室，靠写代码换来第一笔股权。",
            ("1995 · 从代码换股权", "办公室就是起点"),
            ("computer", "map"),
            "paper-wipe",
        ),
        (
            "b02",
            "四年后，Zip2 被收购；他拿到约两千两百万美元，却没有停手，而是继续押注互联网金融。",
            ("1999 · 第一笔退出", "现金继续变成筹码"),
            ("contract", "checks"),
            "matched-cut",
        ),
        (
            "b03",
            "PayPal 出售后，他把大部分资金投进特斯拉和 SpaceX；二零零八年，两家公司同时逼近现金断裂。",
            ("2002 · 再次退出", "2008 · 同时濒临断裂"),
            ("car", "rocket"),
            "camera-travel",
        ),
        (
            "b04",
            "真正改变排名的，不是工资，而是股权；特斯拉市值上升，加上 SpaceX 估值，他最终登上全球财富榜首。",
            ("现金不是终点", "2021 · 股权放大结果"),
            ("gears", "arrow"),
            "chapter-turn",
        ),
    ]
    result_beats: list[dict[str, Any]] = []
    for beat_index, (beat_id, narration, titles, props, transition) in enumerate(
        beats, 1
    ):
        shots = []
        for shot_index in range(2):
            shots.append({
                "id": f"s{shot_index + 1:02d}",
                "duration_s": 4.5,
                "framing": ("wide", "close")[shot_index],
                "shot_scale": (
                    ("wide", "medium"),
                    ("close", "detail"),
                    ("wide", "close"),
                    ("medium", "detail"),
                )[beat_index - 1][shot_index],
                "camera": "coupled parallax push",
                "scene": titles[shot_index],
                "element_motion": (
                    "evidence slides into the authored depth stack; "
                    "subject settles without pose flicker"
                ),
                "direction": {
                    "primary_action": "evidence enters and settles",
                    "physical_cause": "the business event advances ownership",
                    "motion_density": "medium",
                    "shot_scale": (
                        ("wide", "medium"),
                        ("close", "detail"),
                        ("wide", "close"),
                        ("medium", "detail"),
                    )[beat_index - 1][shot_index],
                },
                "show_display_text": False,
                "asset_prop": props[shot_index],
            })
        result_beats.append({
            "id": beat_id,
            "purpose": titles[0],
            "narration": narration,
            "display_text": titles[0],
            "duration_s": 9,
            "feel": "克制、清楚、有推进",
            "semantic_actions": [narration],
            "motion_policy": "profile-driven",
            "source_package_ids": [
                "career-environments",
                "musk-career-family",
                "business-props",
            ],
            "treatments": [{
                "target_id": "musk-stage",
                "visible_change": "career state advances and settles",
                "mechanism": "registered-state-sheet keyframe",
                "state_family_id": "musk-career-poses",
            }, {
                "target_id": "evidence",
                "visible_change": "a new business proof enters",
                "mechanism": "rigid keyframe slide",
            }],
            "transition": {
                "intent": "advance the ownership argument",
                "mechanism": transition,
                "duration_s": 0.34,
            },
            "transition_intent": "advance the ownership argument",
            "transition_rationale": "the next event changes the capital state",
            "shots": shots,
        })
    return {
        "schema_version": 1,
        "project": {
            "id": "musk-wealth-demo",
            "title": "马斯克成为首富的路径 · V6",
            "mode": "topic",
            "topic": "从创业退出、再投资到长期持有公司股权的财富路径",
            "language": "zh-CN",
            "duration_s": 36,
            "aspect": "16:9",
            "fps": FPS,
            "aspect_policy": {
                "requested": "16:9",
                "reason": "横屏承载环境纵深、时间线与多主体证据",
            },
        },
        "source": {
            "fact_scope": "1995—2021 historical path; amounts are approximate"
        },
        "source_packages": [
            {
                "id": "musk-career-family",
                "relationship": "supported-subject",
                "motion_capability": "rigid-locked",
                "source_strategy": "registered-state-sheet",
                "roles": ["support-rear", "subject", "support-front"],
                "registration_id": "musk-career-poses-v6",
            },
            {
                "id": "career-environments",
                "relationship": "registered-depth-stack",
                "motion_capability": "bounded-relative",
                "source_strategy": "registered-sheet",
                "roles": ["support-rear", "subject", "support-front"],
                "registration_id": "career-environments-v6",
                "reveal_envelope": {
                    aspect: [0.04, 0.04, 0.96, 0.96]
                    for aspect in ("16:9", "9:16", "1:1")
                },
                "subject_travel_envelope": {
                    aspect: [0.08, 0.10, 0.92, 0.90]
                    for aspect in ("16:9", "9:16", "1:1")
                },
            },
            {
                "id": "business-props",
                "relationship": "free",
                "motion_capability": "rigid-locked",
                "source_strategy": "registered-sheet",
                "roles": ["computer", "map", "contract", "checks",
                          "car", "rocket", "gears", "arrow"],
            },
        ],
        "semantic_contracts": [
            {
                "id": "musk-identity-family",
                "kind": "identity",
                "claim": "all career poses derive from one registered identity sheet",
                "evidence": [{"kind": "artifact", "ref": "image:source-poses"}],
                "protected_features": ["face", "hairline", "paper-cut silhouette"],
                "automated_checks": [
                    {"type": "source-artifact-present",
                     "artifact_id": "image:source-poses"},
                    {"type": "layer-role-present", "role": "subject"},
                ],
            },
            {
                "id": "institution-context",
                "kind": "institution",
                "claim": "company context remains attached to the evidence layer",
                "evidence": [{"kind": "artifact", "ref": "image:source-environments"}],
                "automated_checks": [
                    {"type": "source-artifact-present",
                     "artifact_id": "image:source-environments"},
                    {"type": "layer-role-present", "role": "mid"},
                ],
            },
            {
                "id": "explanatory-order",
                "kind": "explanatory-diagram",
                "claim": "setup is visible before the proof payoff",
                "evidence": [{"kind": "edit-points", "ref": "setup--payoff"}],
                "automated_checks": [{
                    "type": "edit-order", "before": "setup", "after": "payoff"
                }],
            },
        ],
        "creative": {
            "arc": "从代码换股权，到退出、再投入、股权放大。",
            "theme": themes[1],
            "candidate_themes": themes,
        },
        "audio": {
            "voice": {
                "description": "自然普通话男声，像商业纪录片讲述",
                "provider": "edge-tts",
                "voice_id": "zh-CN-YunxiNeural",
                "rate": "+4%",
                "pitch": "-3Hz",
                "volume": "+0%",
                "profile": "conversational",
                "continuity_mode": "continuous",
                "visual_tail_s": 0.14,
                "prosody": {
                    "comma_pause_s": 0.12,
                    "clause_pause_s": 0.18,
                    "sentence_pause_s": 0.26,
                    "beat_pause_s": 0.08,
                    "safety_pause_s": 0.10,
                },
                "qa": {
                    "min_sentence_pause_s": 0.16,
                    "max_phrase_gap_s": 0.60,
                    "max_unbroken_s": 5.5,
                    "min_boundary_coverage": 0.75,
                    "max_leading_s": 0.25,
                    "max_trailing_s": 0.60,
                    "max_silence_ratio": 0.25,
                    "min_lufs": -23,
                    "max_lufs": -13,
                    "max_true_peak_db": -0.5,
                },
            },
            "music_prompt": "低频脉冲与纸张敲击，无人声",
            "music_volume": 0.09,
            "captions": True,
            "caption_style": "paper",
            "watermark": "",
            "delivery_qa": {
                "min_lufs": -22,
                "max_lufs": -11,
                "max_true_peak_db": -0.5,
            },
        },
        "motion": {
            "pipeline": "layered",
            "frame_conversion": "auto",
            "min_layers": 8,
            "min_animated_layers": 5,
            "directed_motion": True,
            "transitions": {"enabled": True, "duration_s": 0.34,
                            "types": ["wipeleft", "dissolve"]},
        },
        "production": {
            "profile": "balanced",
            "quality_standard": "portfolio",
            "render_engine": "remotion",
            "require_action_proof": True,
            "require_readiness_seal": True,
            "activity_profile": "kinetic",
            "strict_evidence": True,
        },
        "beats": result_beats,
    }


def main() -> None:
    assets = split_sources()
    assets.update(texture_assets())
    project = project_data()
    studio.atomic_json(ROOT / "project.json", project)
    studio.atomic_json(ROOT / "state.json", {
        "version": 2,
        "artifacts": {},
        "approvals": {},
        "attempts": [],
        "provider_events": [],
    })
    scenarios = production_protocol.compile_scenarios(project)
    decision = production_protocol.approve_scenario(
        scenarios, "balanced", "V6 portfolio production approval"
    )
    project["production"]["approved_visual_attempt_cap"] = decision[
        "budget"
    ]["human_approved_cap"]
    studio.atomic_json(ROOT / "project.json", project)
    studio.atomic_json(ROOT / "build" / "scenarios.json", scenarios)
    studio.atomic_json(ROOT / "build" / "scenario-decision.json", decision)
    storyboard = production_protocol.compile_storyboard(
        project, scenarios, decision
    )
    studio.atomic_json(ROOT / "build" / "storyboard.json", storyboard)

    source_specs = [
        (
            "image:source-poses",
            SOURCE_DIR / "musk-career-poses-source.png",
            "four-stage Musk paper-collage identity sheet",
        ),
        (
            "image:source-environments",
            SOURCE_DIR / "career-environments-source.png",
            "four authored career environments in paper collage",
        ),
        (
            "image:source-props",
            SOURCE_DIR / "career-props-source.png",
            "eight authored business and technology paper props",
        ),
    ]
    for artifact_id, path, prompt in source_specs:
        reservation = external_media.reserve(
            ROOT,
            artifact_id=artifact_id,
            provider="openai-imagegen-host",
            model="built-in-imagegen",
            prompt=prompt,
        )
        external_media.complete(
            ROOT, attempt_id=reservation["attempt_id"], source=path
        )

    styles = style_previews(assets["environment-3"])
    for theme_id, path in styles.items():
        studio.register_artifact(
            ROOT,
            f"style:{theme_id}",
            path,
            metadata={
                "candidate_theme_id": theme_id,
                "representative_beat_id": "b03",
                "provenance_class": "deterministic-derivative",
                "source_artifact_ids": ["image:source-environments"],
                "production_ready": True,
                "placeholder": False,
            },
        )

    texture = {
        "ambient": assets["ambient"],
        "foreground": assets["foreground"],
        "grain": assets["grain"],
    }
    scales = ("wide", "medium", "close", "detail", "wide", "close",
              "medium", "detail")
    patterns = ("archive-wide", "desk-asymmetry", "contract-center",
                "capital-split", "crisis-diagonal", "dual-engine",
                "ownership-timeline", "ranking-rise")
    environment_names = ("coding-office", "coding-office", "boardroom",
                         "boardroom", "crisis-factory", "crisis-factory",
                         "growth-complex", "growth-complex")
    shot_index = 0
    for beat_index, beat in enumerate(project["beats"], 1):
        for shot in beat["shots"]:
            env = assets[f"environment-{beat_index}"]
            pose = assets[f"pose-{beat_index}"]
            prop = assets[f"prop-{shot.pop('asset_prop')}"]
            duration_s = float(shot["duration_s"])
            manifest = shot_manifest(
                beat_id=beat["id"],
                shot_id=shot["id"],
                duration_s=duration_s,
                environment=env,
                pose=pose,
                prop=prop,
                texture=texture,
                title=shot["scene"],
                scale=scales[shot_index],
                pattern=patterns[shot_index],
                environment_id=environment_names[shot_index],
                index=shot_index,
                source_ids=[
                    "image:source-poses",
                    "image:source-environments",
                    "image:source-props",
                ],
            )
            package = LAYER_DIR / f"{beat['id']}-{shot['id']}"
            manifest_path = package / "layers.json"
            studio.atomic_json(manifest_path, manifest)
            studio.register_artifact(
                ROOT,
                studio.artifact_key("layers", beat, shot),
                manifest_path,
            )
            shot_index += 1
    studio.atomic_json(ROOT / "project.json", project)
    music = make_music(48)
    studio.register_artifact(
        ROOT,
        "music:main",
        music,
        metadata={
            "provider": "deterministic-local-audio",
            "model": "v6-paper-pulse",
            "provenance_class": "local-vector",
            "source_artifact_ids": ["image:source-props"],
            "production_ready": True,
            "placeholder": False,
        },
    )
    studio.record_approval(ROOT, "story", "V6 demo story approved")
    studio.record_approval(ROOT, "style", "industrial-paper approved")
    style = proof_system.style_proof(ROOT, approve="industrial-paper")
    style_path = ROOT / "proofs" / "style" / "proof.json"
    studio.atomic_json(style_path, style)
    state = studio.load_state(ROOT)
    state.setdefault("proofs", {})["style"] = {
        "path": studio.portable_path(ROOT, style_path),
        "fingerprint": style["fingerprint"],
        "status": style["status"],
        "passed": style["passed"],
    }
    state["storyboard"] = {
        "path": "build/storyboard.json",
        "fingerprint": storyboard["fingerprint"],
    }
    studio.atomic_json(ROOT / "state.json", state)
    print(f"built V6 source and {shot_index} authored layer packages")


if __name__ == "__main__":
    main()
