#!/usr/bin/env python3
"""Prove that subtitle pixels survived final encoding by comparing a subtitle-free master."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageStat

import production_contract


class SubtitleDeliveryError(RuntimeError):
    pass


def _extract(video: Path, at_s: float, output: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{at_s:.6f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(output),
        ],
        check=True,
    )
    if not output.is_file():
        raise SubtitleDeliveryError(f"failed to extract frame at {at_s:.3f}s")


def _cue_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get(
            "cues",
            value.get("phrases", value.get("segments", [])),
        )
    if not isinstance(value, list) or not value:
        raise SubtitleDeliveryError("subtitle manifest must contain non-empty cues")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value, 1):
        start = float(item.get("start_s", item.get("from_s", 0)))
        end = float(
            item.get(
                "end_s",
                item.get("speech_end_s", item.get("pause_end_s", item.get("to_s", start))),
            )
        )
        text = str(item.get("text", "")).strip()
        if end <= start or not text:
            raise SubtitleDeliveryError(f"cue {index} has invalid timing or text")
        result.append({
            "id": str(item.get("id") or f"cue-{index:03d}"),
            "start_s": start,
            "end_s": end,
            "text": text,
        })
    return result


def prove(
    final_video: Path,
    subtitle_free_video: Path,
    subtitle_manifest: Path,
    output_dir: Path,
    *,
    min_mean_delta: float = 1.0,
    region: tuple[float, float, float, float] = (0.0, 0.62, 1.0, 1.0),
) -> dict[str, Any]:
    if not shutil.which("ffmpeg"):
        raise SubtitleDeliveryError("ffmpeg is required")
    cues = _cue_list(json.loads(subtitle_manifest.read_text(encoding="utf-8")))
    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, Any]] = []
    contact_cells: list[Image.Image] = []
    with tempfile.TemporaryDirectory(prefix="subtitle-proof-") as temporary:
        temp = Path(temporary)
        for index, cue in enumerate(cues, 1):
            at_s = (cue["start_s"] + cue["end_s"]) / 2
            final_frame = temp / f"{index:03d}-final.png"
            clean_frame = temp / f"{index:03d}-clean.png"
            _extract(final_video, at_s, final_frame)
            _extract(subtitle_free_video, at_s, clean_frame)
            final_image = Image.open(final_frame).convert("RGB")
            clean_image = Image.open(clean_frame).convert("RGB")
            if final_image.size != clean_image.size:
                raise SubtitleDeliveryError("proof videos have different frame dimensions")
            width, height = final_image.size
            left = round(region[0] * width)
            top = round(region[1] * height)
            right = round(region[2] * width)
            bottom = round(region[3] * height)
            if not (0 <= left < right <= width and 0 <= top < bottom <= height):
                raise SubtitleDeliveryError("subtitle proof region is invalid")
            final_crop = final_image.crop((left, top, right, bottom))
            clean_crop = clean_image.crop((left, top, right, bottom))
            diff = ImageChops.difference(final_crop, clean_crop)
            mean_delta = sum(ImageStat.Stat(diff).mean) / 3
            bbox = diff.getbbox()
            passed = bbox is not None and mean_delta >= min_mean_delta
            evidence = output_dir / f"{cue['id']}.png"
            sheet = Image.new(
                "RGB",
                (final_crop.width * 2, final_crop.height),
                "white",
            )
            sheet.paste(clean_crop, (0, 0))
            sheet.paste(final_crop, (final_crop.width, 0))
            brush = ImageDraw.Draw(sheet)
            brush.text((8, 8), "subtitle-free", fill="red")
            brush.text((final_crop.width + 8, 8), "encoded final", fill="red")
            sheet.save(evidence)
            contact_cells.append(sheet)
            frames.append({
                **cue,
                "at_s": round(at_s, 6),
                "region": list(region),
                "mean_pixel_delta": round(mean_delta, 6),
                "changed_bbox": list(bbox) if bbox else None,
                "evidence": str(evidence),
                "content_sha256": production_contract.file_digest(evidence),
                "passed": passed,
            })
    cell_width = max(item.width for item in contact_cells)
    cell_height = max(item.height for item in contact_cells)
    contact = Image.new(
        "RGB", (cell_width, cell_height * len(contact_cells)), "white"
    )
    for index, image in enumerate(contact_cells):
        contact.paste(image, (0, index * cell_height))
    contact_path = output_dir / "contact-sheet.png"
    contact.save(contact_path)
    issues = [
        f"{item['id']}: encoded subtitle pixels were not independently observed"
        for item in frames
        if not item["passed"]
    ]
    report = {
        "schema_version": 1,
        "final_video": str(final_video.resolve()),
        "final_sha256": production_contract.file_digest(final_video),
        "subtitle_free_video": str(subtitle_free_video.resolve()),
        "subtitle_free_sha256": production_contract.file_digest(subtitle_free_video),
        "subtitle_manifest": str(subtitle_manifest.resolve()),
        "subtitle_manifest_sha256": production_contract.file_digest(subtitle_manifest),
        "min_mean_delta": min_mean_delta,
        "frames": frames,
        "contact_sheet": str(contact_path),
        "contact_sheet_sha256": production_contract.file_digest(contact_path),
        "issues": issues,
        "passed": not issues,
    }
    report["fingerprint"] = production_contract.canonical_digest(report)
    report_path = output_dir / "proof.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("final_video", type=Path)
    parser.add_argument("subtitle_free_video", type=Path)
    parser.add_argument("subtitle_manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--min-mean-delta", type=float, default=1.0)
    args = parser.parse_args()
    try:
        report = prove(
            args.final_video.resolve(),
            args.subtitle_free_video.resolve(),
            args.subtitle_manifest.resolve(),
            args.output_dir.resolve(),
            min_mean_delta=args.min_mean_delta,
        )
        print(f"subtitle delivery: {'passed' if report['passed'] else 'failed'}")
        return 0 if report["passed"] else 1
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
        SubtitleDeliveryError,
    ) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
