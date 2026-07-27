#!/usr/bin/env python3
"""Expose versioned style cards and compile one aspect/style/parallax intake decision."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import production_contract


ASPECTS = ("16:9", "9:16", "1:1")


class IntakeError(RuntimeError):
    pass


def catalog(skill_root: Path) -> dict[str, Any]:
    path = skill_root / "assets" / "style-catalog.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    for style in value.get("styles", []):
        card = skill_root / "assets" / str(style.get("card", ""))
        if not card.is_file():
            raise IntakeError(f"missing style card: {card}")
        style["card_sha256"] = production_contract.file_digest(card)
    value["fingerprint"] = production_contract.canonical_digest(value)
    return value


def decide(
    catalog_value: dict[str, Any],
    *,
    aspect: str,
    style_id: str,
    parallax: str,
    note: str,
) -> dict[str, Any]:
    if aspect not in ASPECTS:
        raise IntakeError("aspect must be 16:9, 9:16, or 1:1")
    style = next(
        (item for item in catalog_value["styles"] if item["id"] == style_id),
        None,
    )
    if style is None:
        raise IntakeError(f"unknown style: {style_id}")
    if parallax not in catalog_value["parallax_preferences"]:
        raise IntakeError(f"unknown parallax preference: {parallax}")
    if not note.strip():
        raise IntakeError("intake decision requires a human note")
    result = {
        "schema_version": 1,
        "catalog_version": catalog_value["version"],
        "catalog_fingerprint": catalog_value["fingerprint"],
        "aspect": aspect,
        "style": style,
        "parallax": parallax,
        "note": note.strip(),
    }
    result["fingerprint"] = production_contract.canonical_digest(result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show")
    show.add_argument("--output", type=Path)
    choose = sub.add_parser("choose")
    choose.add_argument("--aspect", choices=ASPECTS, required=True)
    choose.add_argument("--style", required=True)
    choose.add_argument(
        "--parallax", choices=("none", "restrained", "cinematic"), required=True
    )
    choose.add_argument("--note", required=True)
    choose.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        skill_root = Path(__file__).resolve().parents[1]
        value = catalog(skill_root)
        if args.command == "choose":
            value = decide(
                value,
                aspect=args.aspect,
                style_id=args.style,
                parallax=args.parallax,
                note=args.note,
            )
        if getattr(args, "output", None):
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError, IntakeError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
