#!/usr/bin/env python3
"""Extract claim-centered proof frames and generate an auditable review sheet."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import production_contract


class ProofReviewError(RuntimeError):
    pass


def extract(
    video: Path,
    editorial_plan: Path,
    output_dir: Path,
) -> Path:
    if not shutil.which("ffmpeg"):
        raise ProofReviewError("ffmpeg is required")
    if not video.is_file():
        raise ProofReviewError(f"missing video: {video}")
    try:
        plan = json.loads(editorial_plan.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProofReviewError(f"cannot read editorial plan: {exc}") from exc
    moments = plan.get("compiled_proof_moments", [])
    if not isinstance(moments, list) or not moments:
        raise ProofReviewError("editorial plan has no compiled proof moments")
    output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for index, moment in enumerate(moments, 1):
        moment_id = str(moment.get("id") or f"proof-{index:02d}")
        timestamp = float(moment["at_s"])
        frame = output_dir / f"{index:02d}-{moment_id}.png"
        command = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{timestamp:.3f}", "-i", str(video),
            "-frames:v", "1", str(frame),
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode or not frame.is_file():
            raise ProofReviewError(
                f"cannot extract {moment_id}: {result.stderr.strip()}"
            )
        records.append({
            "id": moment_id,
            "beat_id": moment.get("beat_id"),
            "at_s": timestamp,
            "frame": frame.name,
            "checks": moment.get("checks", []),
            "review_status": "pending-human-review",
            "content_sha256": production_contract.file_digest(frame),
        })
    report = {
        "video": str(video),
        "video_sha256": production_contract.file_digest(video),
        "editorial_plan": str(editorial_plan),
        "proof_moments": records,
        "passed": False,
        "status": "pending-human-review",
    }
    report_path = output_dir / "proof-review.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video")
    parser.add_argument("editorial_plan")
    parser.add_argument("output_dir")
    args = parser.parse_args()
    try:
        report = extract(
            Path(args.video).resolve(),
            Path(args.editorial_plan).resolve(),
            Path(args.output_dir).resolve(),
        )
    except (OSError, ValueError, KeyError, ProofReviewError) as exc:
        print(f"ERROR: {exc}")
        return 2
    print(f"proof review: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
