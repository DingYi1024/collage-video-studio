#!/usr/bin/env python3
"""Run the offline acceptance test and build an installable .skill archive."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
REPOSITORY_ONLY = {
    ".gitattributes",
    ".gitignore",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "README.md",
    "SECURITY.md",
    "VERSION",
}
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
TEXT_SUFFIXES = {".md", ".py", ".json", ".jsonl", ".yaml", ".yml", ".txt"}
TEXT_NAMES = {"LICENSE", "SKILL.md", "requirements.txt"}


def should_include(path: Path) -> bool:
    rel = path.relative_to(SKILL_ROOT)
    if rel.as_posix() == "scripts/sync_plugin.py":
        return False
    if rel.parts and rel.parts[0] in {
        ".git", ".github", ".agents", ".tmp-checks", ".voice-deps", "dist",
        "examples", "plugins",
    }:
        return False
    if rel.as_posix() in REPOSITORY_ONLY:
        return False
    if any(
        part in {"__pycache__", "node_modules", "dist", "out", ".remotion"}
        for part in rel.parts
    ):
        return False
    if path.suffix in {".pyc", ".pyo"}:
        return False
    return path.is_file()


def write_reproducible_entry(archive: zipfile.ZipFile, path: Path) -> None:
    name = path.relative_to(SKILL_ROOT).as_posix()
    info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    data = path.read_bytes()
    if path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_NAMES:
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    archive.writestr(info, data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--skip-selftest", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not args.skip_selftest:
        result = subprocess.run([sys.executable, str(SKILL_ROOT / "scripts" / "selftest.py")])
        if result.returncode:
            print("ERROR: selftest failed; package was not created", file=sys.stderr)
            return result.returncode

    output = Path(args.output) if args.output else SKILL_ROOT.parent / "collage-video-studio.skill"
    if not output.is_absolute():
        output = Path.cwd() / output
    output = output.resolve()
    if output.exists() and not args.force:
        print(f"ERROR: output exists; use --force to replace it: {output}", file=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp",
                                         dir=output.parent)
    os.close(handle)
    temp = Path(temp_name)
    try:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_STORED) as archive:
            paths = [path for path in SKILL_ROOT.rglob("*") if should_include(path)]
            for path in sorted(
                paths,
                key=lambda item: item.relative_to(SKILL_ROOT).as_posix(),
            ):
                write_reproducible_entry(archive, path)
        os.replace(temp, output)
    finally:
        if temp.exists():
            temp.unlink()
    print(f"package: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
