#!/usr/bin/env python3
"""Synchronize the distributable Codex plugin from the repository skill source."""

from __future__ import annotations

import argparse
import filecmp
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "collage-video-studio"
TARGET = PLUGIN / "skills" / "collage-video-studio"
DIRECTORIES = ("agents", "assets", "references", "scripts")
FILES = ("SKILL.md", "LICENSE", "requirements.txt", "VERSION")
REPOSITORY_ONLY = {"scripts/sync_plugin.py"}
SCREENSHOTS = {
    "poster-16x9.png": "landscape.png",
    "poster-9x16.png": "portrait.png",
    "poster-1x1.png": "square.png",
}


def sync() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copy2(ROOT / name, TARGET / name)
    for directory in DIRECTORIES:
        source = ROOT / directory
        destination = TARGET / directory
        shutil.copytree(
            source,
            destination,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
    copied_sync = TARGET / "scripts" / "sync_plugin.py"
    if copied_sync.exists():
        copied_sync.unlink()
    plugin_assets = PLUGIN / "assets"
    plugin_assets.mkdir(parents=True, exist_ok=True)
    proof_assets = ROOT / "examples" / "editorial-proof-demo" / "result"
    for source_name, target_name in SCREENSHOTS.items():
        source = proof_assets / source_name
        if not source.is_file():
            raise RuntimeError(
                f"missing plugin screenshot {source}; rebuild editorial-proof-demo"
            )
        shutil.copy2(source, plugin_assets / target_name)


def check() -> None:
    problems: list[str] = []
    for name in FILES:
        target = TARGET / name
        if not target.is_file() or not filecmp.cmp(ROOT / name, target, shallow=False):
            problems.append(name)
    for directory in DIRECTORIES:
        for source in (ROOT / directory).rglob("*"):
            if (
                not source.is_file()
                or "__pycache__" in source.parts
                or source.suffix in {".pyc", ".pyo"}
            ):
                continue
            relative = source.relative_to(ROOT)
            if relative.as_posix() in REPOSITORY_ONLY:
                continue
            target = TARGET / relative
            if not target.is_file() or not filecmp.cmp(source, target, shallow=False):
                problems.append(relative.as_posix())
    proof_assets = ROOT / "examples" / "editorial-proof-demo" / "result"
    for source_name, target_name in SCREENSHOTS.items():
        source = proof_assets / source_name
        target = PLUGIN / "assets" / target_name
        if not source.is_file() or not target.is_file() or not filecmp.cmp(
            source, target, shallow=False
        ):
            problems.append(f"plugin screenshot {target_name}")
    manifest = (
        PLUGIN / ".codex-plugin" / "plugin.json"
    ).read_text(encoding="utf-8")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if f'"version": "{version}"' not in manifest:
        problems.append("plugin version")
    if problems:
        raise RuntimeError("plugin projection is stale: " + ", ".join(problems))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
        print(f"plugin projection current: {PLUGIN}")
    else:
        sync()
        print(f"plugin synchronized: {PLUGIN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
