"""Copy this file into your integration package and implement execute().

The adapter owns provider authentication, submission, polling, download, and retry policy.
It must not rewrite project.json or state.json.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class BackendError(RuntimeError):
    pass


def execute(job: dict[str, Any], project_dir: Path) -> Path | dict[str, Any]:
    """Execute one manifest job and return a path or structured result.

    Required job fields:
      id, kind, prompt, inputs, params, output.path

    Suggested implementation:
      1. Resolve input paths relative to project_dir.
      2. Route on job["kind"].
      3. Submit with job["id"] as the provider idempotency key when supported.
      4. Poll with bounded exponential backoff.
      5. Download to project_dir / job["output"]["path"].
      6. Verify the file is non-empty and probe its media type/duration.
      7. Return the path. Let the caller register it only after success.

    A speech backend with phrase timing should instead return:
      {
        "path": output_path,
        "url": optional_non_secret_source_url,
        "metadata": {
          "timing_path": timing_json_path,
          "provider": "provider-name",
          "model": "model-name"
        }
      }

    Keep the timing file inside project_dir. The runner validates it, marks timing_status as
    provided, and stores a portable path. Legacy path-only speech results remain supported and
    are explicitly marked timing_status=missing.
    """
    raise BackendError(f"no backend implementation for {job['kind']} ({job['id']})")
