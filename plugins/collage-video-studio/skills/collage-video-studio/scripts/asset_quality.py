#!/usr/bin/env python3
"""Observed-key cleanup and independent asset/composition quality gates."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

import layer_compositor
import production_contract


class AssetQualityError(RuntimeError):
    pass


def _distance(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))


def observed_key_plane(image: Image.Image) -> tuple[int, int, int]:
    rgb = image.convert("RGB")
    width, height = rgb.size
    border: list[tuple[int, int, int]] = []
    for x in range(width):
        border.append(rgb.getpixel((x, 0)))
        border.append(rgb.getpixel((x, height - 1)))
    for y in range(1, height - 1):
        border.append(rgb.getpixel((0, y)))
        border.append(rgb.getpixel((width - 1, y)))
    if not border:
        raise AssetQualityError("image has no border pixels")
    quantized = [
        tuple(min(255, (channel // 8) * 8 + 4) for channel in pixel)
        for pixel in border
    ]
    modal, _ = Counter(quantized).most_common(1)[0]
    close = [pixel for pixel in border if _distance(pixel, modal) <= 28]
    values = close or border
    return tuple(round(sum(pixel[channel] for pixel in values) / len(values))
                 for channel in range(3))


def observe_key_plane(
    source: Path,
    *,
    policy_id: str = "flat-border-v1",
) -> dict[str, Any]:
    """Bind a provider-native key observation to the untouched source bytes."""
    image = Image.open(source).convert("RGB")
    key = observed_key_plane(image)
    width, height = image.size
    border: list[tuple[int, int, int]] = []
    for x in range(width):
        border.extend((image.getpixel((x, 0)), image.getpixel((x, height - 1))))
    for y in range(1, max(1, height - 1)):
        border.extend((image.getpixel((0, y)), image.getpixel((width - 1, y))))
    distances = [_distance(pixel, key) for pixel in border]
    close_ratio = sum(value <= 28 for value in distances) / max(1, len(distances))
    mean_distance = sum(distances) / max(1, len(distances))
    maximum_distance = max(distances, default=0.0)
    clusters = len({
        tuple((channel // 16) * 16 for channel in pixel)
        for pixel in border
        if _distance(pixel, key) > 28
    })
    passed = close_ratio >= 0.92 and mean_distance <= 14 and maximum_distance <= 70
    source_sha = production_contract.file_digest(source)
    policy = {
        "id": policy_id,
        "minimum_close_ratio": 0.92,
        "maximum_mean_distance": 14,
        "maximum_outlier_distance": 70,
    }
    result = {
        "schema_version": 1,
        "mode": "provider-native-observation",
        "policy": policy,
        "policy_fingerprint": production_contract.canonical_digest(policy),
        "source": str(source),
        "source_sha256": source_sha,
        "observed_key_rgb": list(key),
        "statistics": {
            "border_samples": len(border),
            "close_ratio": close_ratio,
            "mean_distance": mean_distance,
            "maximum_distance": maximum_distance,
            "outlier_clusters": clusters,
        },
        "passed": passed,
        "issues": [] if passed else ["provider key plane is not flat and stable"],
    }
    result["observation_fingerprint"] = production_contract.canonical_digest(result)
    return result


def remove_observed_key(
    source: Path,
    output: Path,
    *,
    tolerance: float = 42.0,
    softness: float = 24.0,
) -> dict[str, Any]:
    image = Image.open(source).convert("RGBA")
    observation = observe_key_plane(source)
    if not observation["passed"]:
        raise AssetQualityError("; ".join(observation["issues"]))
    key = tuple(observation["observed_key_rgb"])
    output_image = Image.new("RGBA", image.size)
    source_pixels = image.load()
    target_pixels = output_image.load()
    removed = partial = 0
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue, original_alpha = source_pixels[x, y]
            distance = _distance((red, green, blue), key)
            if distance <= tolerance:
                alpha = 0
                removed += 1
            elif distance < tolerance + softness:
                alpha = round(
                    original_alpha
                    * (distance - tolerance)
                    / max(1e-6, softness)
                )
                partial += 1
            else:
                alpha = original_alpha
            if alpha == 0:
                target_pixels[x, y] = 0, 0, 0, 0
                continue
            # Despill toward neutral luminance only around the alpha edge.
            if alpha < original_alpha and alpha > 0:
                luminance = round((red + green + blue) / 3)
                strength = 1.0 - alpha / max(1, original_alpha)
                red = round(red + (luminance - red) * strength)
                green = round(green + (luminance - green) * strength)
                blue = round(blue + (luminance - blue) * strength)
            target_pixels[x, y] = red, green, blue, alpha
    output.parent.mkdir(parents=True, exist_ok=True)
    output_image.save(output)
    return {
        "source": str(source),
        "output": str(output),
        "observed_key_rgb": list(key),
        "source_sha256": observation["source_sha256"],
        "observation_fingerprint": observation["observation_fingerprint"],
        "policy_fingerprint": observation["policy_fingerprint"],
        "removed_pixels": removed,
        "partial_edge_pixels": partial,
        "content_sha256": production_contract.file_digest(output),
    }


def alpha_edge_audit(path: Path) -> dict[str, Any]:
    image = Image.open(path).convert("RGBA")
    alpha = image.getchannel("A")
    histogram = alpha.histogram()
    total = image.width * image.height
    transparent = histogram[0]
    opaque = histogram[255]
    partial = total - transparent - opaque
    pixels = list(image.getdata())
    transparent_rgb = sum(
        alpha == 0 and (red > 3 or green > 3 or blue > 3)
        for red, green, blue, alpha in pixels
    )
    partial_pixels = [
        (red, green, blue)
        for red, green, blue, alpha in pixels
        if 0 < alpha < 255
    ]
    chroma_residual = 0
    for red, green, blue in partial_pixels:
        maximum = max(red, green, blue)
        minimum = min(red, green, blue)
        saturation = (maximum - minimum) / max(1, maximum)
        ordered = sorted((red, green, blue), reverse=True)
        dominance = (ordered[0] - ordered[1]) / max(1, ordered[0])
        if saturation > 0.35 and dominance > 0.18:
            chroma_residual += 1
    transparent_rgb_ratio = transparent_rgb / max(1, transparent)
    chroma_residual_ratio = chroma_residual / max(1, len(partial_pixels))
    bbox = alpha.getbbox()
    touches = False
    if bbox:
        left, top, right, bottom = bbox
        touches = left == 0 or top == 0 or right == image.width or bottom == image.height
    issues: list[str] = []
    if transparent == 0:
        issues.append("no transparent pixels; source may be flattened")
    if opaque == 0:
        issues.append("no opaque pixels; source may be over-keyed")
    if partial == 0 and transparent and opaque:
        issues.append("no partial alpha edge; cutout is likely jagged")
    if transparent_rgb_ratio > 0.02:
        issues.append(
            "transparent pixels retain RGB energy; premultiplied fringe risk"
        )
    if partial_pixels and chroma_residual_ratio > 0.45:
        issues.append(
            "partial-alpha edge retains dominant chroma; key-colour spill is likely"
        )
    if touches:
        issues.append("opaque subject touches canvas edge; crop safety is unknown")
    low_alpha = [
        (index % image.width, index // image.width)
        for index, value in enumerate(alpha.getdata())
        if 4 <= value <= 96
    ]
    edge_band = 0
    if low_alpha:
        margin_x = max(1, round(image.width * 0.025))
        margin_y = max(1, round(image.height * 0.025))
        edge_band = sum(
            x < margin_x or x >= image.width - margin_x
            or y < margin_y or y >= image.height - margin_y
            for x, y in low_alpha
        )
    rectangular_residue_ratio = edge_band / max(1, len(low_alpha))
    if len(low_alpha) >= 24 and rectangular_residue_ratio > 0.72:
        issues.append(
            "low-alpha pixels form a canvas-correlated rectangular residue band"
        )
    return {
        "path": str(path),
        "size": [image.width, image.height],
        "transparent_ratio": transparent / total,
        "opaque_ratio": opaque / total,
        "partial_alpha_ratio": partial / total,
        "transparent_rgb_residual_ratio": transparent_rgb_ratio,
        "partial_edge_chroma_residual_ratio": chroma_residual_ratio,
        "rectangular_low_alpha_residual_ratio": rectangular_residue_ratio,
        "content_bbox": list(bbox) if bbox else None,
        "issues": issues,
        "passed": not issues,
    }


def audit_asset_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssetQualityError("asset manifest must be an object")
    records: list[dict[str, Any]] = []
    issues: list[str] = []
    for index, item in enumerate(value.get("assets", []), 1):
        if not isinstance(item, dict):
            issues.append(f"asset[{index}] must be an object")
            continue
        source = path.parent / str(item.get("path", ""))
        if not source.is_file():
            issues.append(f"asset[{index}] missing: {source}")
            continue
        report = alpha_edge_audit(source)
        report["id"] = str(item.get("id") or f"asset-{index}")
        required = bool(item.get("requires_alpha", True))
        if not required:
            report["issues"] = [
                issue for issue in report["issues"]
                if not issue.startswith("no transparent")
            ]
            report["passed"] = not report["issues"]
        records.append(report)
        issues.extend(f"{report['id']}: {issue}" for issue in report["issues"])
    return {
        "gate": "assets",
        "assets": records,
        "issues": issues,
        "passed": bool(records) and not issues,
    }


def audit_composition_manifest(path: Path) -> dict[str, Any]:
    errors, warnings, stats = layer_compositor.validate_manifest(path)
    motion = (
        layer_compositor.audit_motion_continuity(
            layer_compositor.load_manifest(path)
        )
        if not errors
        else {"issues": []}
    )
    issues = [*errors, *motion.get("issues", [])]
    return {
        "gate": "composition",
        "stats": stats,
        "warnings": warnings,
        "issues": issues,
        "passed": not issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--output")
    parser.add_argument(
        "--mode",
        choices=("observe-key", "key", "alpha", "assets", "composition"),
        default="alpha",
    )
    parser.add_argument("--tolerance", type=float, default=42.0)
    parser.add_argument("--softness", type=float, default=24.0)
    args = parser.parse_args()
    source = Path(args.input).resolve()
    try:
        if args.mode == "observe-key":
            report = observe_key_plane(source)
        elif args.mode == "key":
            if not args.output:
                raise AssetQualityError("--output is required for key mode")
            report = remove_observed_key(
                source, Path(args.output).resolve(),
                tolerance=args.tolerance, softness=args.softness,
            )
        elif args.mode == "alpha":
            report = alpha_edge_audit(source)
        elif args.mode == "assets":
            report = audit_asset_manifest(source)
        else:
            report = audit_composition_manifest(source)
    except (
        OSError, ValueError, json.JSONDecodeError,
        AssetQualityError, layer_compositor.LayerError,
    ) as exc:
        print(f"ERROR: {exc}")
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
