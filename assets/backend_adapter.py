"""Copy this file into your integration package and implement execute().

The adapter owns provider authentication, submission, polling, download, and retry policy.
It must not rewrite project.json or state.json.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class BackendError(RuntimeError):
    pass


def execute(job: dict[str, Any], project_dir: Path) -> Path:
    """Execute one manifest job and return a verified local output path.

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
    """
    raise BackendError(f"no backend implementation for {job['kind']} ({job['id']})")
