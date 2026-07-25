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


def should_include(path: Path) -> bool:
    rel = path.relative_to(SKILL_ROOT)
    if rel.parts and rel.parts[0] in {
        ".git", ".github", ".tmp-checks", ".voice-deps", "dist", "examples",
    }:
        return False
    if rel.as_posix() in REPOSITORY_ONLY:
        return False
    if "__pycache__" in rel.parts:
        return False
    if path.suffix in {".pyc", ".pyo"}:
        return False
    return path.is_file()


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
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(SKILL_ROOT.rglob("*")):
                if should_include(path):
                    archive.write(path, path.relative_to(SKILL_ROOT).as_posix())
        os.replace(temp, output)
    finally:
        if temp.exists():
            temp.unlink()
    print(f"package: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
