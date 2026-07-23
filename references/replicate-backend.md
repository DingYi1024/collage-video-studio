# Replicate production backend

Use this reference when the project should generate real media with the bundled production
adapter. The generic adapter contract remains available for other services.

## What it covers

The bundled route handles every manifest kind:

| Job kind | Default model | Main mapped fields |
|---|---|---|
| `image_generation` | `google/imagen-4-fast` | prompt, aspect |
| `image_edit` | `black-forest-labs/flux-kontext-pro` | prompt, source image, aspect |
| `image_to_video` | `wan-video/wan-2.7-i2v` | prompt, first frame, duration |
| `video_edit` | `wan-video/wan-2.7-videoedit` | prompt, source clip, aspect, duration |
| `speech` | `minimax/speech-2.8-hd` | narration, language hint, speed |
| `music` | `meta/musicgen` | music brief, duration |

Provider models and their input schemas change independently of this Skill. Treat the included
map as a tested starting configuration, then check the current model schema before a paid batch.

## Install and authenticate

Install the provider's Python SDK into the same Python environment used to run the Skill:

```bash
python -m pip install -r requirements.txt
```

Create an API token in the provider account and expose it only through the environment:

```bash
export REPLICATE_API_TOKEN="<token>"
```

PowerShell:

```powershell
$env:REPLICATE_API_TOKEN = "<token>"
```

Never put the token in `backend.json`, a manifest, source control, a report, or `state.json`.

## Freeze or customize the route

The adapter works with built-in defaults. To make a project's route explicit, copy the template
from the Skill directory:

```bash
cp assets/replicate-backend.example.json <project-dir>/backend.json
```

PowerShell:

```powershell
Copy-Item assets/replicate-backend.example.json <project-dir>/backend.json
```

`backend.json` can override:

- `models.<job-kind>.model`;
- fixed `defaults` sent to the model;
- `input_fields` that map manifest roles to model inputs;
- `param_fields` that map neutral job parameters;
- `limits` and `value_maps`;
- polling interval, timeout, and media verification.

Do not disable `verify_media` in production.

## Preflight without spending

Run:

```bash
python scripts/replicate_backend.py doctor <project-dir>
python scripts/replicate_backend.py print-config <project-dir>
python scripts/job_runner.py <project-dir> --stage images \
  --adapter scripts/replicate_backend.py --dry-run
```

`doctor` checks configuration, the token's presence, the SDK, FFmpeg, and FFprobe. It does not
make an API call or submit a prediction. `print-config` never prints the token.

Before a paid stage:

1. Inspect the effective models and manifest.
2. Confirm current provider pricing and model schemas.
3. Run one job with `--limit 1`.
4. Inspect the result before running the remaining batch.

## Execute

```bash
python scripts/job_runner.py <project-dir> --stage images \
  --adapter scripts/replicate_backend.py --limit 1 --retries 0
```

Repeat without `--limit` only after the small result passes review.

The adapter stores non-secret execution records under:

```text
.studio/providers/replicate/
```

Each record is content-addressed by the job and route. Once a prediction ID exists, rerunning the
same job resumes polling instead of submitting again. If the connection fails before the adapter
can save a prediction ID, it records `submission_uncertain` and refuses an automatic retry. Once
the local output exists, it is reused. Source footage ranges are copied into temporary trimmed
inputs; the original source is untouched.

## Failure and deliberate resubmission

If a prediction fails or its hosted output expires:

1. Read the job's provider log and inspect recent predictions in the provider account, especially
   when the status is `submission_uncertain`.
2. Correct the input, route, or account problem.
3. If a genuinely new paid submission is intended, archive the no-resubmit guard explicitly:

```bash
python scripts/replicate_backend.py release <project-dir> "<job-id>" --yes
```

The command moves the log to a `released/` audit folder. It does not delete media or state.
The next job execution may submit and charge again.

Do not release a job merely because polling timed out. Rerun the same job first; it will resume
the existing prediction.

## Privacy and retention

Local source files are uploaded by the provider SDK. Review the selected model's data policy
before using private portraits, client footage, or unreleased products. Downloaded results are
saved immediately because hosted output URLs can expire.
