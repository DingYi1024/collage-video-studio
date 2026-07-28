#!/usr/bin/env python3
"""Offline contract test for the production Replicate adapter."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import replicate_backend


class FakeFileOutput:
    def __init__(self, data: bytes):
        self.data = data

    def read(self) -> bytes:
        return self.data


class FakePredictions:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.records: dict[str, SimpleNamespace] = {}
        self.fail_next = False

    @staticmethod
    def snapshot(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: FakePredictions.snapshot(item) for key, item in value.items()}
        if isinstance(value, list):
            return [FakePredictions.snapshot(item) for item in value]
        if callable(getattr(value, "read", None)):
            return {"local_file": getattr(value, "name", "<stream>")}
        return value

    def create(self, *, version: str, input: dict[str, Any]) -> SimpleNamespace:
        prediction_id = f"pred-{len(self.created) + 1}"
        self.created.append({"version": version, "input": self.snapshot(input)})
        if self.fail_next:
            self.fail_next = False
            raise ConnectionError("simulated lost response after submission")
        prediction = SimpleNamespace(
            id=prediction_id, status="starting", output=None, error=None,
            created_at="2026-01-01T00:00:00+00:00",
        )
        self.records[prediction_id] = prediction
        return prediction

    def get(self, prediction_id: str) -> SimpleNamespace:
        prediction = self.records[prediction_id]
        prediction.status = "succeeded"
        prediction.output = FakeFileOutput(f"media:{prediction_id}".encode())
        prediction.completed_at = "2026-01-01T00:00:01+00:00"
        return prediction


def write_config(root: Path) -> None:
    override = {
        "provider": "replicate",
        "poll_interval_s": 0.001,
        "timeout_s": 2,
        "verify_media": False,
    }
    (root / "backend.json").write_text(
        json.dumps(override, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def sample_jobs() -> list[dict[str, Any]]:
    return [
        {
            "id": "style:one", "kind": "image_generation", "prompt": "paper city",
            "inputs": [], "params": {"aspect": "9:16"},
            "output": {"path": "media/images/style-one.png"},
        },
        {
            "id": "image:one", "kind": "image_edit", "prompt": "paper portrait",
            "inputs": [{"role": "source", "path": "source.png"}],
            "params": {"aspect": "9:16"},
            "output": {"path": "media/images/image-one.png"},
        },
        {
            "id": "motion:one", "kind": "image_to_video", "prompt": "slow paper reveal",
            "inputs": [{"role": "keyframe", "path": "keyframe.png"}],
            "params": {"duration_s": 0.5, "aspect": "9:16"},
            "output": {"path": "media/motion/motion-one.mp4"},
        },
        {
            "id": "motion:two", "kind": "video_edit", "prompt": "paper restyle",
            "inputs": [{"role": "source", "path": "source.mp4"}],
            "params": {"duration_s": 25, "aspect": "9:16"},
            "output": {"path": "media/motion/motion-two.mp4"},
        },
        {
            "id": "voice:one", "kind": "speech", "prompt": "A short narration.",
            "inputs": [], "params": {"language": "zh", "speed": 9},
            "output": {"path": "media/audio/voice-one.wav"},
        },
        {
            "id": "music:main", "kind": "music", "prompt": "quiet paper percussion",
            "inputs": [], "params": {"duration_s": 90, "instrumental": True},
            "output": {"path": "media/audio/music-main.wav"},
        },
    ]


def assert_payloads(fake: FakePredictions) -> None:
    if len(fake.created) != 6:
        raise RuntimeError(f"expected six submissions, got {len(fake.created)}")
    inputs = [item["input"] for item in fake.created]
    if inputs[0]["aspect_ratio"] != "9:16":
        raise RuntimeError("image aspect mapping failed")
    if "local_file" not in inputs[1]["input_image"]:
        raise RuntimeError("image-edit local input mapping failed")
    if "local_file" not in inputs[2]["first_frame"] or inputs[2]["duration"] != 2:
        raise RuntimeError("image-to-video mapping or duration clamp failed")
    if "local_file" not in inputs[3]["video"] or inputs[3]["duration"] != 10:
        raise RuntimeError("video-edit mapping or duration clamp failed")
    if inputs[4]["language_boost"] != "Chinese" or inputs[4]["speed"] != 2:
        raise RuntimeError("speech language mapping or speed clamp failed")
    if inputs[5]["duration"] != 60:
        raise RuntimeError("music duration clamp failed")


def run_test(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    write_config(root)
    for name in ("source.png", "keyframe.png", "source.mp4"):
        (root / name).write_bytes(f"fixture:{name}".encode())

    fake_predictions = FakePredictions()
    fake_module = types.ModuleType("replicate")
    fake_module.__version__ = "offline-contract"
    fake_module.predictions = fake_predictions
    previous_module = sys.modules.get("replicate")
    previous_token = os.environ.get("REPLICATE_API_TOKEN")
    sys.modules["replicate"] = fake_module
    os.environ["REPLICATE_API_TOKEN"] = "contract-test-token"
    try:
        jobs = sample_jobs()
        for job in jobs:
            result = replicate_backend.execute(job, root)
            output = Path(result["path"] if isinstance(result, dict) else result)
            if not output.is_file() or output.stat().st_size <= 0:
                raise RuntimeError(f"{job['id']}: output was not written")
        assert_payloads(fake_predictions)

        before = len(fake_predictions.created)
        for job in jobs:
            replicate_backend.execute(job, root)
        if len(fake_predictions.created) != before:
            raise RuntimeError("completed jobs were submitted twice")

        uncertain = {
            "id": "style:uncertain", "kind": "image_generation",
            "prompt": "uncertain submission", "inputs": [],
            "params": {"aspect": "1:1"},
            "output": {"path": "media/images/uncertain.png"},
        }
        fake_predictions.fail_next = True
        try:
            replicate_backend.execute(uncertain, root)
            raise RuntimeError("uncertain submission did not fail closed")
        except replicate_backend.BackendError as exc:
            if "uncertain" not in str(exc):
                raise
        uncertain_count = len(fake_predictions.created)
        try:
            replicate_backend.execute(uncertain, root)
            raise RuntimeError("uncertain submission was silently retried")
        except replicate_backend.BackendError as exc:
            if "previous submission" not in str(exc):
                raise
        if len(fake_predictions.created) != uncertain_count:
            raise RuntimeError("uncertain submission created a duplicate prediction")
        replicate_backend.release_job(root, "style:uncertain", confirmed=True)
        replicate_backend.execute(uncertain, root)
        if len(fake_predictions.created) != uncertain_count + 1:
            raise RuntimeError("explicit release did not permit a new submission")

        logs = list((root / ".studio" / "providers" / "replicate").glob("*.json"))
        if len(logs) != 7:
            raise RuntimeError(f"expected seven active provider logs, got {len(logs)}")
        released = list(
            (root / ".studio" / "providers" / "replicate" / "released").glob("*.json")
        )
        if len(released) != 1:
            raise RuntimeError("uncertain submission release was not archived")
        combined = "\n".join(
            path.read_text(encoding="utf-8") for path in logs + released
        )
        if "contract-test-token" in combined:
            raise RuntimeError("API token leaked into provider logs")
    finally:
        if previous_module is None:
            sys.modules.pop("replicate", None)
        else:
            sys.modules["replicate"] = previous_module
        if previous_token is None:
            os.environ.pop("REPLICATE_API_TOKEN", None)
        else:
            os.environ["REPLICATE_API_TOKEN"] = previous_token
    print("PASS: six routes, mappings, polling, no-resubmit, uncertain-submit guard, release")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix="replicate-adapter-contract-"))
    try:
        run_test(root)
        if args.keep:
            print(f"kept: {root}")
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        print(f"artifacts retained for diagnosis: {root}", file=sys.stderr)
        return 1
    finally:
        if not args.keep and root.exists():
            shutil.rmtree(root)


if __name__ == "__main__":
    raise SystemExit(main())
