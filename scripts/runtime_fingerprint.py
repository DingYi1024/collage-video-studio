#!/usr/bin/env python3
"""Create named runtime fingerprints and classify incremental proof invalidation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import production_contract


SURFACES: dict[str, tuple[str, ...]] = {
    "composition": (
        "scripts/layer_compositor.py",
        "scripts/editorial_runtime.py",
        "scripts/annotation_layout.py",
        "scripts/svg_primitives.py",
        "scripts/depth_stack.py",
        "scripts/world_motion.py",
        "scripts/generate_world_fixture.py",
        "workspace/src/remotion/CollageVideo.tsx",
        "workspace/src/remotion/Primitive.tsx",
        "workspace/src/lib/types.ts",
        "workspace/src/lib/motion.ts",
        "workspace/src/lib/manifest.ts",
        "workspace/public/world-proof.json",
        "workspace/public/world-far.png",
        "workspace/public/world-mid.png",
        "workspace/public/world-ground.png",
        "workspace/public/world-near.png",
        "workspace/public/world-9x16-props.json",
        "workspace/public/world-1x1-props.json",
    ),
    "subtitles": (
        "scripts/overlays.py",
        "scripts/render.py",
        "scripts/subtitle_delivery.py",
    ),
    "audio": (
        "scripts/audio_qa.py",
        "scripts/audio_calibration.py",
        "scripts/voice_director.py",
        "scripts/render.py",
    ),
    "provider": (
        "scripts/job_runner.py",
        "scripts/provider_lifecycle.py",
        "scripts/asset_quality.py",
        "scripts/registered_family.py",
        "scripts/context_repair.py",
    ),
    "protocol": (
        "scripts/production_protocol.py",
        "scripts/intake.py",
        "assets/style-catalog.json",
        "assets/style-cards/quiet-archive.svg",
        "assets/style-cards/bold-editorial.svg",
        "assets/style-cards/diagram-workshop.svg",
        "scripts/production_contract.py",
        "scripts/proof_system.py",
        "scripts/semantic_qa.py",
        "scripts/preview_revision.py",
        "scripts/studio.py",
        "scripts/project_ops.py",
        "scripts/readiness_seal.py",
        "scripts/production_metrics.py",
        "scripts/scene_preview.py",
        "scripts/quality_lifecycle.py",
    ),
}


class FingerprintError(RuntimeError):
    pass


def build(root: Path) -> dict[str, Any]:
    root = root.resolve()
    surfaces: dict[str, Any] = {}
    for name, relative_paths in SURFACES.items():
        files: list[dict[str, str]] = []
        for relative in relative_paths:
            path = root / relative
            if not path.is_file():
                raise FingerprintError(f"missing runtime input {relative}")
            files.append({
                "path": relative,
                "sha256": production_contract.file_digest(path),
            })
        surfaces[name] = {
            "files": files,
            "fingerprint": production_contract.canonical_digest(files),
        }
    manifest = {
        "schema_version": 1,
        "version": (root / "VERSION").read_text(encoding="utf-8").strip(),
        "surfaces": surfaces,
    }
    manifest["fingerprint"] = production_contract.canonical_digest(manifest)
    return manifest


def classify(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    old = previous.get("surfaces", {})
    new = current.get("surfaces", {})
    changed = sorted(
        name for name in set(old) | set(new)
        if old.get(name, {}).get("fingerprint")
        != new.get(name, {}).get("fingerprint")
    )
    affected: set[str] = set()
    routes = {
        "composition": {"composition", "moment", "final"},
        "subtitles": {"subtitle", "final"},
        "audio": {"audio", "moment", "final"},
        "provider": {"assets", "composition", "moment", "final"},
        "protocol": {"style", "assets", "composition", "moment", "final"},
    }
    for name in changed:
        affected.update(routes.get(name, {"final"}))
    return {
        "changed_surfaces": changed,
        "invalidated_proofs": sorted(affected),
        "composition_reusable": not bool(
            {"composition", "provider", "protocol"}.intersection(changed)
        ),
        "audio_remux_eligible": changed == ["audio"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    try:
        report = build(args.root)
        if args.compare:
            previous = json.loads(args.compare.read_text(encoding="utf-8"))
            report["change"] = classify(previous, report)
        output = args.output or args.root / "runtime-build.json"
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"runtime fingerprint: {report['fingerprint']}")
        return 0
    except (OSError, json.JSONDecodeError, FingerprintError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
