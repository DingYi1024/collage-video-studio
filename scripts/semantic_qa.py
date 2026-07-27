#!/usr/bin/env python3
"""Automated evidence checks for identity, topology, mechanism, and infographics."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from PIL import Image

import production_contract


class SemanticQaError(RuntimeError):
    pass


def _average_hash(image: Image.Image, size: int = 16) -> list[bool]:
    grayscale = image.convert("L").resize((size, size), Image.Resampling.LANCZOS)
    pixels = list(grayscale.getdata())
    average = sum(pixels) / len(pixels)
    return [value >= average for value in pixels]


def _histogram(image: Image.Image, bins: int = 16) -> list[float]:
    rgb = image.convert("RGB").resize((128, 128), Image.Resampling.LANCZOS)
    result: list[float] = []
    total = rgb.width * rgb.height
    source = rgb.histogram()
    stride = 256 // bins
    for channel in range(3):
        channel_values = source[channel * 256:(channel + 1) * 256]
        for index in range(bins):
            result.append(
                sum(channel_values[index * stride:(index + 1) * stride]) / total
            )
    return result


def _alpha_bbox_ratio(image: Image.Image) -> tuple[float, float]:
    alpha = image.convert("RGBA").getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return 0.0, 0.0
    width = (bbox[2] - bbox[0]) / image.width
    height = (bbox[3] - bbox[1]) / image.height
    return width, height


def identity_similarity(reference: Path, candidate: Path) -> dict[str, Any]:
    first = Image.open(reference)
    second = Image.open(candidate)
    first_hash = _average_hash(first)
    second_hash = _average_hash(second)
    hash_score = 1.0 - sum(
        left != right for left, right in zip(first_hash, second_hash)
    ) / len(first_hash)
    first_histogram = _histogram(first)
    second_histogram = _histogram(second)
    histogram_score = 1.0 - min(
        1.0,
        sum(
            abs(left - right)
            for left, right in zip(first_histogram, second_histogram)
        ) / 6.0,
    )
    first_bbox = _alpha_bbox_ratio(first)
    second_bbox = _alpha_bbox_ratio(second)
    bbox_score = 1.0 - min(
        1.0,
        (
            abs(first_bbox[0] - second_bbox[0])
            + abs(first_bbox[1] - second_bbox[1])
        ) / 2.0,
    )
    score = 0.65 * hash_score + 0.25 * histogram_score + 0.10 * bbox_score
    return {
        "score": round(score, 6),
        "perceptual_hash_score": round(hash_score, 6),
        "color_histogram_score": round(histogram_score, 6),
        "alpha_bbox_score": round(bbox_score, 6),
        "reference_sha256": production_contract.file_digest(reference),
        "candidate_sha256": production_contract.file_digest(candidate),
        "note": "reference-preservation score; not biometric face recognition",
    }


def _nodes(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    def visit(node: dict[str, Any]) -> None:
        node_id = str(node.get("id", ""))
        if node_id:
            result[node_id] = node
        for child in node.get("children", []):
            if isinstance(child, dict):
                visit(child)

    composition = manifest.get("composition")
    if isinstance(composition, dict):
        visit(composition)
    for layer in manifest.get("layers", []):
        if isinstance(layer, dict) and str(layer.get("id", "")):
            # Compiled layers contain director overrides and are the actual runtime geometry.
            result[str(layer["id"])] = layer
    return result


def _box(node: dict[str, Any]) -> tuple[float, float, float, float]:
    primitive = node.get("primitive", {})
    if not isinstance(primitive, dict):
        raise SemanticQaError(f"{node.get('id')}: node has no primitive bounds")
    try:
        return (
            float(primitive.get("x", 0)),
            float(primitive.get("y", 0)),
            float(primitive["width"]),
            float(primitive["height"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SemanticQaError(
            f"{node.get('id')}: primitive needs numeric x/y/width/height"
        ) from exc


def _relative(
    first: tuple[float, float, float, float],
    relation: str,
    second: tuple[float, float, float, float],
) -> bool:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    if relation == "left-of":
        return ax + aw <= bx
    if relation == "right-of":
        return ax >= bx + bw
    if relation == "above":
        return ay + ah <= by
    if relation == "below":
        return ay >= by + bh
    if relation == "overlaps":
        return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by
    if relation == "inside":
        return ax >= bx and ay >= by and ax + aw <= bx + bw and ay + ah <= by + bh
    raise SemanticQaError(f"unsupported relative-position relation {relation!r}")


def _edit_points(manifest: dict[str, Any]) -> dict[str, float]:
    return {
        str(item["id"]): float(item["at_s"])
        for item in manifest.get("edit_points", [])
        if isinstance(item, dict) and item.get("id") is not None
    }


def run_check(
    check: dict[str, Any],
    *,
    nodes: dict[str, dict[str, Any]],
    edit_points: dict[str, float],
    root: Path,
) -> dict[str, Any]:
    kind = str(check.get("type", ""))
    if kind == "identity-similarity":
        reference = (root / str(check["reference"])).resolve()
        candidate = (root / str(check["candidate"])).resolve()
        if not reference.is_file() or not candidate.is_file():
            raise SemanticQaError("identity check references missing image evidence")
        detail = identity_similarity(reference, candidate)
        minimum = float(check.get("min_score", 0.78))
        return {
            "type": kind,
            "passed": float(detail["score"]) >= minimum,
            "minimum": minimum,
            "detail": detail,
        }
    if kind == "relative-position":
        first_id, second_id = str(check["a"]), str(check["b"])
        if first_id not in nodes or second_id not in nodes:
            raise SemanticQaError("relative-position references missing nodes")
        relation = str(check["relation"])
        first_box, second_box = _box(nodes[first_id]), _box(nodes[second_id])
        return {
            "type": kind,
            "passed": _relative(first_box, relation, second_box),
            "a": first_id,
            "b": second_id,
            "relation": relation,
            "a_box": list(first_box),
            "b_box": list(second_box),
        }
    if kind == "edit-order":
        before, after = str(check["before"]), str(check["after"])
        if before not in edit_points or after not in edit_points:
            raise SemanticQaError("edit-order references missing edit points")
        return {
            "type": kind,
            "passed": edit_points[before] < edit_points[after],
            "before": [before, edit_points[before]],
            "after": [after, edit_points[after]],
        }
    if kind == "data-values":
        node_id = str(check["node"])
        node = nodes.get(node_id)
        if node is None:
            raise SemanticQaError(f"data-values references missing node {node_id}")
        primitive = node.get("primitive", {})
        actual = [float(value) for value in primitive.get("values", [])]
        expected = [float(value) for value in check.get("values", [])]
        tolerance = float(check.get("tolerance", 0.0))
        passed = len(actual) == len(expected) and all(
            math.isclose(left, right, abs_tol=tolerance)
            for left, right in zip(actual, expected)
        )
        return {
            "type": kind,
            "passed": passed,
            "node": node_id,
            "expected": expected,
            "actual": actual,
            "tolerance": tolerance,
        }
    if kind == "text-exact":
        node_id = str(check["node"])
        node = nodes.get(node_id)
        actual = str((node or {}).get("primitive", {}).get("text", ""))
        expected = str(check.get("text", ""))
        return {
            "type": kind,
            "passed": node is not None and actual == expected,
            "node": node_id,
            "expected": expected,
            "actual": actual,
        }
    raise SemanticQaError(f"unsupported automated semantic check {kind!r}")


def audit(
    project: dict[str, Any],
    manifest: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    nodes = _nodes(manifest)
    edit_points = _edit_points(manifest)
    contracts: list[dict[str, Any]] = []
    issues: list[str] = []
    for contract in project.get("semantic_contracts", []):
        contract_id = str(contract.get("id", ""))
        checks = contract.get("automated_checks", [])
        results: list[dict[str, Any]] = []
        if not isinstance(checks, list) or not checks:
            issues.append(f"{contract_id}: no automated checks")
        else:
            for index, check in enumerate(checks, 1):
                try:
                    result = run_check(
                        check,
                        nodes=nodes,
                        edit_points=edit_points,
                        root=root,
                    )
                except (SemanticQaError, OSError, ValueError, KeyError) as exc:
                    result = {
                        "type": str(check.get("type", "")),
                        "passed": False,
                        "error": str(exc),
                    }
                results.append(result)
                if not result["passed"]:
                    issues.append(
                        f"{contract_id}.automated_checks[{index}] failed"
                    )
        contracts.append({
            "id": contract_id,
            "kind": contract.get("kind"),
            "claim": contract.get("claim"),
            "checks": results,
            "passed": bool(results) and all(item["passed"] for item in results),
        })
    return {
        "contracts": contracts,
        "issues": issues,
        "passed": bool(contracts) and not issues,
        "manifest_fingerprint": production_contract.canonical_digest(manifest),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    parser.add_argument("manifest")
    parser.add_argument("--output")
    args = parser.parse_args()
    project_path = Path(args.project).resolve()
    manifest_path = Path(args.manifest).resolve()
    try:
        project = json.loads(project_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        report = audit(project, manifest, project_path.parent)
    except (OSError, json.JSONDecodeError, SemanticQaError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2
    if args.output:
        output = Path(args.output).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
