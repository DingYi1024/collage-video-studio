#!/usr/bin/env python3
"""Build the three-aspect editorial protocol proof."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import asset_quality
import editorial_contract
import layer_compositor


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    here = Path(__file__).resolve().parent
    source = json.loads((here / "composition.json").read_text(encoding="utf-8"))
    variants = editorial_contract.compile_director_variants(source)
    result = here / "result"
    reports: dict[str, object] = {}
    for aspect, manifest in variants.items():
        slug = aspect.replace(":", "x")
        manifest_path = result / f"composition-{slug}.json"
        output = result / f"proof-{slug}.mp4"
        write(manifest_path, manifest)
        report = asset_quality.audit_composition_manifest(manifest_path)
        if not report["passed"]:
            raise RuntimeError(f"{aspect} composition gate failed: {report}")
        layer_compositor.render_manifest(manifest_path, output)
        reports[aspect] = {
            "manifest": manifest_path.name,
            "video": output.name,
            "layout": manifest["director"]["layout_audit"],
            "composition_gate": report,
        }
    summary = {
        "protocol": "independent editorial composition v2",
        "variants": reports,
        "passed": all(
            value["layout"]["passed"] and value["composition_gate"]["passed"]
            for value in reports.values()
        ),
    }
    write(result / "proof-report.json", summary)
    print(f"proof gallery: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
