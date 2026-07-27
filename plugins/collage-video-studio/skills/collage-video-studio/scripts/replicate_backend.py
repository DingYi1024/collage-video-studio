#!/usr/bin/env python3
"""Production Replicate adapter for collage-video-studio JSONL jobs.

Authentication comes only from REPLICATE_API_TOKEN. Project configuration is optional and
lives in backend.json; see assets/replicate-backend.example.json.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, BinaryIO


class BackendError(RuntimeError):
    pass


DEFAULT_CONFIG: dict[str, Any] = {
    "provider": "replicate",
    "poll_interval_s": 2,
    "timeout_s": 1800,
    "verify_media": True,
    "models": {
        "image_generation": {
            "model": "google/imagen-4-fast",
            "prompt_field": "prompt",
            "defaults": {
                "output_format": "png",
                "safety_filter_level": "block_medium_and_above",
            },
            "input_fields": {},
            "param_fields": {"aspect": "aspect_ratio"},
        },
        "image_edit": {
            "model": "black-forest-labs/flux-kontext-pro",
            "prompt_field": "prompt",
            "defaults": {
                "output_format": "png",
                "safety_tolerance": 2,
                "prompt_upsampling": False,
            },
            "input_fields": {"source": "input_image"},
            "param_fields": {"aspect": "aspect_ratio"},
        },
        "image_to_video": {
            "model": "wan-video/wan-2.7-i2v",
            "prompt_field": "prompt",
            "defaults": {
                "resolution": "720p",
                "enable_prompt_expansion": False,
                "negative_prompt": "warping, melting, text distortion, identity drift",
            },
            "input_fields": {"keyframe": "first_frame"},
            "param_fields": {"duration_s": "duration"},
            "limits": {"duration_s": [2, 15]},
        },
        "video_edit": {
            "model": "wan-video/wan-2.7-videoedit",
            "prompt_field": "prompt",
            "defaults": {"resolution": "720p", "audio_setting": "origin"},
            "input_fields": {"source": "video"},
            "param_fields": {"aspect": "aspect_ratio", "duration_s": "duration"},
            "limits": {"duration_s": [2, 10]},
        },
        "speech": {
            "model": "minimax/speech-2.8-hd",
            "prompt_field": "text",
            "defaults": {
                "voice_id": "Wise_Woman",
                "pitch": 0,
                "volume": 1,
                "emotion": "auto",
                "bitrate": 128000,
                "channel": "mono",
                "sample_rate": 32000,
                "audio_format": "wav",
                "subtitle_enable": False,
                "english_normalization": False,
            },
            "input_fields": {},
            "param_fields": {"speed": "speed", "language": "language_boost"},
            "limits": {"speed": [0.5, 2.0]},
            "value_maps": {
                "language": {
                    "zh": "Chinese",
                    "zh-CN": "Chinese",
                    "zh-TW": "Chinese",
                    "en": "English",
                    "en-US": "English",
                    "en-GB": "English",
                    "ja": "Japanese",
                    "ko": "Korean",
                    "es": "Spanish",
                    "fr": "French",
                    "de": "German",
                    "pt": "Portuguese",
                    "_default": "Automatic",
                }
            },
        },
        "music": {
            "model": (
                "meta/musicgen:"
                "671ac645ce5e552cc63a54a2bbff63fcf798043055d2dac5fc9e36a837eedcfb"
            ),
            "prompt_field": "prompt",
            "defaults": {
                "model_version": "stereo-large",
                "output_format": "wav",
                "normalization_strategy": "loudness",
                "continuation": False,
                "multi_band_diffusion": False,
            },
            "input_fields": {},
            "param_fields": {"duration_s": "duration"},
            "limits": {"duration_s": [1, 60]},
        },
    },
}

TERMINAL_SUCCESS = {"succeeded", "successful", "completed"}
TERMINAL_FAILURE = {"failed", "canceled", "cancelled", "aborted"}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def atomic_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp",
                                         dir=path.parent)
    os.close(handle)
    temp = Path(temp_name)
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config(project_dir: Path) -> dict[str, Any]:
    path = project_dir / "backend.json"
    override: dict[str, Any] = {}
    if path.exists():
        try:
            override = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise BackendError(f"invalid backend.json: {exc}") from exc
        if not isinstance(override, dict):
            raise BackendError("backend.json must contain a JSON object")
    config = deep_merge(DEFAULT_CONFIG, override)
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    if config.get("provider") != "replicate":
        raise BackendError("backend.json provider must be 'replicate'")
    models = config.get("models")
    if not isinstance(models, dict):
        raise BackendError("backend.json models must be an object")
    missing = sorted(set(DEFAULT_CONFIG["models"]) - set(models))
    if missing:
        raise BackendError(f"backend.json is missing job kinds: {', '.join(missing)}")
    for kind, route in models.items():
        if not isinstance(route, dict) or not isinstance(route.get("model"), str):
            raise BackendError(f"models.{kind}.model must be a string")
        for key in ("defaults", "input_fields", "param_fields"):
            if not isinstance(route.get(key, {}), dict):
                raise BackendError(f"models.{kind}.{key} must be an object")
    if float(config.get("poll_interval_s", 0)) <= 0:
        raise BackendError("poll_interval_s must be greater than zero")
    if float(config.get("timeout_s", 0)) <= 0:
        raise BackendError("timeout_s must be greater than zero")


def get_replicate_module() -> Any:
    try:
        import replicate  # type: ignore
    except ImportError as exc:
        raise BackendError(
            "Replicate Python SDK is missing; install it with: python -m pip install replicate"
        ) from exc
    return replicate


def ensure_output_path(project_dir: Path, raw: str) -> Path:
    path = Path(raw)
    output = path.resolve() if path.is_absolute() else (project_dir / path).resolve()
    try:
        output.relative_to(project_dir.resolve())
    except ValueError as exc:
        raise BackendError(f"output must stay inside the project directory: {output}") from exc
    return output


def resolve_input_path(project_dir: Path, raw: str) -> Path:
    path = Path(raw)
    resolved = path.resolve() if path.is_absolute() else (project_dir / path).resolve()
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise BackendError(f"input file is missing or empty: {resolved}")
    return resolved


def job_digest(job: dict[str, Any], route: dict[str, Any]) -> str:
    payload = {"job": job, "model": route.get("model"), "route": route}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def log_file(project_dir: Path, job: dict[str, Any], route: dict[str, Any]) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", str(job["id"])).strip("-") or "job"
    return (project_dir / ".studio" / "providers" / "replicate" /
            f"{safe}-{job_digest(job, route)[:12]}.json")


def get_value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def apply_value_map(route: dict[str, Any], param: str, value: Any) -> Any:
    mapping = route.get("value_maps", {}).get(param)
    if not isinstance(mapping, dict):
        return value
    return mapping.get(str(value), mapping.get("_default", value))


def apply_limit(route: dict[str, Any], param: str, value: Any) -> Any:
    bounds = route.get("limits", {}).get(param)
    if not isinstance(bounds, list) or len(bounds) != 2:
        return value
    if not isinstance(value, (int, float)):
        return value
    low, high = bounds
    limited = max(float(low), min(float(high), float(value)))
    return int(limited) if isinstance(value, int) or limited.is_integer() else limited


def trim_video(project_dir: Path, job: dict[str, Any], source: Path,
               range_s: list[Any]) -> Path:
    if len(range_s) != 2 or not all(isinstance(item, (int, float)) for item in range_s):
        raise BackendError(f"{job['id']}: range_s must contain numeric start/end values")
    start, end = float(range_s[0]), float(range_s[1])
    if start < 0 or end <= start:
        raise BackendError(f"{job['id']}: invalid source range {range_s}")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise BackendError("ffmpeg is required to trim footage inputs")
    digest = hashlib.sha256(
        f"{source}|{source.stat().st_mtime_ns}|{start}|{end}".encode()
    ).hexdigest()[:12]
    target = (project_dir / ".studio" / "providers" / "replicate" / "inputs" /
              f"{re.sub(r'[^A-Za-z0-9._-]+', '-', str(job['id']))}-{digest}.mp4")
    if target.is_file() and target.stat().st_size > 0:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp.mp4")
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start),
        "-i", str(source), "-t", str(end - start), "-c:v", "libx264",
        "-preset", "medium", "-crf", "18", "-c:a", "aac", "-movflags", "+faststart",
        str(temp),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode or not temp.is_file() or temp.stat().st_size <= 0:
        temp.unlink(missing_ok=True)
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown"
        raise BackendError(f"{job['id']}: footage trim failed: {detail}")
    os.replace(temp, target)
    return target


def prepare_inputs(job: dict[str, Any], project_dir: Path,
                   route: dict[str, Any]) -> tuple[dict[str, Any], list[BinaryIO]]:
    payload = copy.deepcopy(route.get("defaults", {}))
    prompt_field = route.get("prompt_field", "prompt")
    if prompt_field:
        payload[prompt_field] = str(job.get("prompt", ""))

    params = job.get("params", {})
    for source_name, target_name in route.get("param_fields", {}).items():
        if source_name not in params or not target_name:
            continue
        value = apply_value_map(route, source_name, params[source_name])
        payload[target_name] = apply_limit(route, source_name, value)

    handles: list[BinaryIO] = []
    input_fields = route.get("input_fields", {})
    try:
        for record in job.get("inputs", []):
            role = record.get("role")
            target_name = input_fields.get(role)
            if not target_name:
                raise BackendError(f"{job['id']}: no input mapping for role {role!r}")
            raw = str(record.get("path", ""))
            if raw.startswith(("https://", "http://", "data:")):
                value: Any = raw
            else:
                source = resolve_input_path(project_dir, raw)
                source_range = record.get("range_s")
                if source_range is None and role == "source":
                    source_range = params.get("source_range")
                if (source_range is not None and
                        source.suffix.lower() in {".mp4", ".mov", ".mkv"}):
                    source = trim_video(project_dir, job, source, source_range)
                handle = source.open("rb")
                handles.append(handle)
                value = handle
            if target_name in payload:
                existing = payload[target_name]
                payload[target_name] = existing + [value] if isinstance(existing, list) else [
                    existing, value
                ]
            else:
                payload[target_name] = value
    except Exception:
        for handle in handles:
            handle.close()
        raise
    return payload, handles


def save_log(path: Path, record: dict[str, Any], prediction: Any | None = None) -> None:
    if prediction is not None:
        for key in ("id", "status", "created_at", "started_at", "completed_at", "error"):
            value = get_value(prediction, key)
            if value is not None:
                record["prediction_id" if key == "id" else key] = value
    record["updated_at"] = utc_now()
    atomic_json(path, record)


def poll_prediction(replicate: Any, prediction: Any, record: dict[str, Any],
                    path: Path, config: dict[str, Any]) -> Any:
    deadline = time.monotonic() + float(config["timeout_s"])
    delay = float(config["poll_interval_s"])
    while True:
        status = str(get_value(prediction, "status", "")).lower()
        save_log(path, record, prediction)
        if status in TERMINAL_SUCCESS:
            return prediction
        if status in TERMINAL_FAILURE:
            detail = get_value(prediction, "error") or "provider returned no error detail"
            raise BackendError(
                f"{record['job_id']}: prediction {record.get('prediction_id')} {status}: {detail}"
            )
        if time.monotonic() >= deadline:
            raise BackendError(
                f"{record['job_id']}: polling timed out; rerun the same job to resume "
                f"prediction {record.get('prediction_id')}"
            )
        time.sleep(delay)
        prediction_id = record.get("prediction_id")
        if not prediction_id:
            raise BackendError(f"{record['job_id']}: provider response had no prediction id")
        prediction = replicate.predictions.get(prediction_id)
        delay = min(delay * 1.5, 10)


def output_candidate(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            found = output_candidate(item)
            if found is not None:
                return found
        return None
    if isinstance(value, dict):
        for key in ("url", "file", "audio", "video", "image", "output"):
            if key in value:
                found = output_candidate(value[key])
                if found is not None:
                    return found
        return None
    if callable(getattr(value, "read", None)):
        return value
    url = getattr(value, "url", None)
    if callable(url):
        url = url()
    if url:
        return str(url)
    if isinstance(value, str):
        return value
    return None


def write_candidate(candidate: Any, target: Path) -> str | None:
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp",
                                         dir=target.parent)
    os.close(handle)
    temp = Path(temp_name)
    source_url: str | None = None
    try:
        if callable(getattr(candidate, "read", None)):
            data = candidate.read()
            if not isinstance(data, (bytes, bytearray)):
                raise BackendError("provider file output did not return bytes")
            temp.write_bytes(bytes(data))
        elif isinstance(candidate, str) and candidate.startswith("data:"):
            import base64
            try:
                header, encoded = candidate.split(",", 1)
                if ";base64" not in header:
                    raise ValueError("not base64")
                temp.write_bytes(base64.b64decode(encoded, validate=True))
            except (ValueError, TypeError) as exc:
                raise BackendError("provider returned an invalid data URI") from exc
        elif isinstance(candidate, str) and candidate.startswith(("https://", "http://")):
            source_url = candidate
            request = urllib.request.Request(
                candidate, headers={"User-Agent": "collage-video-studio/1.0"}
            )
            with urllib.request.urlopen(request, timeout=120) as response, temp.open("wb") as out:
                shutil.copyfileobj(response, out, length=1024 * 1024)
        else:
            raise BackendError("provider output did not contain a downloadable media file")
        if not temp.is_file() or temp.stat().st_size <= 0:
            raise BackendError("provider output was empty")
        os.replace(temp, target)
        return source_url
    finally:
        if temp.exists():
            temp.unlink()


def verify_media(path: Path, kind: str) -> None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise BackendError("ffprobe is required to verify provider output")
    command = [
        ffprobe, "-v", "error", "-show_entries",
        "format=format_name,duration:stream=codec_type", "-of", "json", str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown"
        raise BackendError(f"{kind}: downloaded output is not valid media: {detail}")
    try:
        probe = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BackendError(f"{kind}: ffprobe returned invalid JSON") from exc
    streams = {item.get("codec_type") for item in probe.get("streams", [])}
    expected = "video" if kind in {"image_to_video", "video_edit"} else (
        "audio" if kind in {"speech", "music"} else "video"
    )
    if expected not in streams:
        raise BackendError(f"{kind}: output has no {expected} stream")


def execute(job: dict[str, Any], project_dir: Path) -> Path:
    """Execute one manifest job and return a verified local output path."""
    root = Path(project_dir).resolve()
    config = load_config(root)
    kind = str(job.get("kind", ""))
    route = config["models"].get(kind)
    if not isinstance(route, dict):
        raise BackendError(f"unsupported job kind: {kind}")
    output = ensure_output_path(root, str(job.get("output", {}).get("path", "")))
    log_path = log_file(root, job, route)
    digest = job_digest(job, route)
    record: dict[str, Any]
    if log_path.is_file():
        record = json.loads(log_path.read_text(encoding="utf-8"))
        if record.get("digest") != digest:
            raise BackendError(f"{job['id']}: provider log digest mismatch")
        if output.is_file() and output.stat().st_size > 0:
            return output
    else:
        record = {
            "version": 1,
            "provider": "replicate",
            "job_id": job["id"],
            "kind": kind,
            "model": route["model"],
            "digest": digest,
            "status": "prepared",
            "created_at": utc_now(),
        }
        save_log(log_path, record)

    token = os.environ.get("REPLICATE_API_TOKEN", "").strip()
    if not token:
        raise BackendError("REPLICATE_API_TOKEN is not set")
    replicate = get_replicate_module()

    prediction_id = record.get("prediction_id")
    if prediction_id:
        prediction = replicate.predictions.get(prediction_id)
    else:
        if record.get("status") in {"submitting", "submission_uncertain"}:
            raise BackendError(
                f"{job['id']}: a previous submission may have reached the provider before "
                "the prediction ID was saved; inspect recent provider predictions, then use "
                "the release command only if a new paid submission is intended"
            )
        payload, handles = prepare_inputs(job, root, route)
        record["status"] = "submitting"
        save_log(log_path, record)
        try:
            try:
                prediction = replicate.predictions.create(
                    version=route["model"], input=payload
                )
            except Exception as exc:
                record["status"] = "submission_uncertain"
                record["submission_error_type"] = type(exc).__name__
                save_log(log_path, record)
                raise BackendError(
                    f"{job['id']}: submission outcome is uncertain; inspect recent provider "
                    "predictions before releasing the no-resubmit guard"
                ) from exc
        finally:
            for handle in handles:
                handle.close()
        prediction_id = get_value(prediction, "id")
        if not prediction_id:
            raise BackendError(f"{job['id']}: provider response had no prediction id")
        save_log(log_path, record, prediction)

    prediction = poll_prediction(replicate, prediction, record, log_path, config)
    candidate = output_candidate(get_value(prediction, "output"))
    if candidate is None:
        raise BackendError(
            f"{job['id']}: prediction succeeded but output is unavailable; "
            "do not resubmit until the provider record is inspected"
        )
    source_url = write_candidate(candidate, output)
    if config.get("verify_media", True):
        verify_media(output, kind)
    record["status"] = "downloaded"
    record["output_path"] = output.relative_to(root).as_posix()
    if source_url:
        record["output_url"] = source_url
    save_log(log_path, record, prediction)
    return output


def cmd_doctor(project_dir: Path) -> int:
    checks: list[tuple[str, bool, str]] = []
    try:
        config = load_config(project_dir)
        source = "project override" if (project_dir / "backend.json").is_file() else "built-in"
        checks.append(("effective config", True,
                       f"{source}, {len(config['models'])} job kinds"))
    except BackendError as exc:
        checks.append(("effective config", False, str(exc)))
        config = None
    token = bool(os.environ.get("REPLICATE_API_TOKEN", "").strip())
    checks.append(("REPLICATE_API_TOKEN", token, "set" if token else "missing"))
    try:
        module = get_replicate_module()
        version = getattr(module, "__version__", "installed")
        checks.append(("replicate SDK", True, str(version)))
    except BackendError as exc:
        checks.append(("replicate SDK", False, str(exc)))
    checks.append(("ffmpeg", bool(shutil.which("ffmpeg")),
                   shutil.which("ffmpeg") or "missing"))
    checks.append(("ffprobe", bool(shutil.which("ffprobe")),
                   shutil.which("ffprobe") or "missing"))
    for name, ok, detail in checks:
        print(f"{'OK' if ok else 'MISSING':7} {name}: {detail}")
    if config:
        for kind, route in config["models"].items():
            print(f"MODEL   {kind}: {route['model']}")
    return 0 if all(item[1] for item in checks) else 2


def release_job(project_dir: Path, job_id: str, confirmed: bool) -> Path:
    if not confirmed:
        raise BackendError(
            "release archives the no-resubmit guard and permits a new paid submission; "
            "rerun with --yes after inspecting the provider prediction"
        )
    folder = project_dir / ".studio" / "providers" / "replicate"
    matches: list[Path] = []
    for path in folder.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if record.get("job_id") == job_id:
            matches.append(path)
    if not matches:
        raise BackendError(f"no active provider log found for job {job_id!r}")
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        raise BackendError(f"multiple active logs found for {job_id!r}: {names}")
    source = matches[0]
    released = folder / "released"
    released.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = released / f"{source.stem}-released-{stamp}.json"
    if target.exists():
        raise BackendError(f"release archive already exists: {target}")
    os.replace(source, target)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor", help="check configuration without submitting a job")
    doctor.add_argument("project_dir")
    show = sub.add_parser("print-config", help="print effective non-secret configuration")
    show.add_argument("project_dir")
    release = sub.add_parser(
        "release",
        help="archive one no-resubmit guard after inspecting its provider prediction",
    )
    release.add_argument("project_dir")
    release.add_argument("job_id")
    release.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    root = Path(args.project_dir).resolve()
    try:
        if args.command == "doctor":
            return cmd_doctor(root)
        if args.command == "release":
            target = release_job(root, args.job_id, args.yes)
            print(f"released: {target}")
            print("the next execution may create a new paid prediction")
            return 0
        print(json.dumps(load_config(root), ensure_ascii=False, indent=2))
        return 0
    except (BackendError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
