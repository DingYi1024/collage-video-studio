# Project and backend contract

Use this reference when editing configuration, registering assets, or adding a media backend.

## Editorial v2 fields

- `semantic_contracts[]`: identity, topology, mechanism, or infographic claims with evidence.
- `editorial_timing`: intro/outro/visual-tail holds and optional measured per-beat voice seconds.
- `beats[].transition_intent`: semantic transition route.
- `beats[].proof_moments[]`: exact claim-relative evidence checks.
- composition `director_plans`: separate 16:9, 9:16, and 1:1 node overrides and safe zones.
- composition `edit_points[]`: sorted review/action points targeting existing nodes.
- composition `composition`: recursive group/image/primitive node tree.

`state.json` version 2 adds append-only `provider_events`. The older `attempts` array remains for
reader compatibility, but new lifecycle audit and recovery use `provider_events`.

## Contents

- Files and ownership
- Project fields
- Beat and shot fields
- Runtime state
- Job manifest
- Backend adapter contract

## Files and ownership

```text
project-dir/
├── project.json        creative intent; edit deliberately
├── state.json          generated artifact registry; update with studio.py
├── jobs/               reproducible JSONL job manifests
├── backend.json        optional non-secret provider route overrides
├── media/              generated/downloaded files
├── render/             temporary render files
├── .studio/history/    immutable project/state checkpoints
├── .studio/providers/  provider prediction records and prepared inputs
├── qa/                 technical report and extracted review frames
├── reports/            timestamped grounded production reports
├── exports/            portable project archives
└── final.mp4           assembled result
```

Do not store provider prediction IDs, temporary URLs, or local output paths in `project.json`.
Do not store creative decisions in `state.json`.
Do not put credentials in `backend.json`; provider adapters must read them from the environment.

## Project fields

Required top-level fields:

```json
{
  "schema_version": 1,
  "project": {
    "id": "example",
    "title": "Example",
    "mode": "topic",
    "topic": "What the film is about",
    "language": "zh",
    "duration_s": 30,
    "aspect": "16:9",
    "aspect_policy": {
      "requested": "auto",
      "reason": "auto: spatial narrative intent detected"
    },
    "fps": 30
  },
  "source": {},
  "creative": {
    "arc": "",
    "theme": null,
    "candidate_themes": []
  },
  "audio": {
    "voice": {
      "description": "",
      "speed": 1.0,
      "provider": "edge-tts",
      "voice_id": "auto",
      "rate": "+0%",
      "pitch": "-2Hz",
      "volume": "+0%",
      "profile": "conversational",
      "direction": "warm, grounded, conversational; never sing-song",
      "continuity_mode": "continuous",
      "prosody": {
        "comma_pause_s": 0.10,
        "clause_pause_s": 0.16,
        "sentence_pause_s": 0.22,
        "beat_pause_s": 0.26,
        "safety_pause_s": 0.16
      },
      "qa": {
        "min_sentence_pause_s": 0.16,
        "max_phrase_gap_s": 0.50,
        "max_unbroken_s": 5.50,
        "min_boundary_coverage": 0.75,
        "max_leading_s": 0.25,
        "max_trailing_s": 0.60,
        "max_silence_ratio": 0.25,
        "min_lufs": -23.0,
        "max_lufs": -13.0,
        "max_true_peak_db": -0.5
      }
    },
    "music_prompt": "",
    "captions": true,
    "caption_style": "clean",
    "watermark": "",
    "mix": {"voice": 1.0, "music": 0.35},
    "delivery_qa": {
      "min_lufs": -22.0,
      "max_lufs": -11.0,
      "max_true_peak_db": -0.5
    }
  },
  "motion": {
    "pipeline": "layered",
    "frame_conversion": "auto",
    "min_layers": 6,
    "min_animated_layers": 3,
    "directed_motion": true,
    "transitions": {
      "enabled": true,
      "duration_s": 0.32,
      "types": ["wipeleft", "dissolve", "slideup"]
    }
  },
  "production": {
    "profile": "balanced",
    "activity_profile": "kinetic",
    "strict_evidence": true,
    "attempt_limits": {
      "visual_source": 18,
      "generative_motion": 6,
      "voice": 8,
      "music": 3
    }
  },
  "beats": []
}
```

The provider-specific voice fields are optional production direction. For an offline-ready demo,
`scripts/voice_director.py` reads the narration, language, and timeline duration; resolves an
automatic multilingual voice; generates a mastered WAV; plans abbreviation-aware semantic pauses
and balanced safety splits; and rejects speech that would need clipping, excessive padding,
breathless run-on delivery, or artificial time-stretching. It stores a sibling `.timing.json`
with measured phrase and pause windows and registers that path in artifact metadata.
New projects use `continuity_mode: "continuous"` and register `voice:main`; projects without the
field retain legacy `voice:<beat-id>` artifacts.

See [voice-continuity.md](voice-continuity.md) for narration timing and pure-voice QA.

Mode-specific `source`:

- `topic`: `{}`.
- `footage`: `{"path":"...","preserve_original_audio":true}`.
- `photo`: `{"path":"...","subject":"portrait|product","anchor_policy":"..."}`.

`creative.theme` and each candidate use the six fields documented in
[visual-system.md](visual-system.md).

## Beat and shot fields

```json
{
  "id": "b01",
  "purpose": "What changes for the viewer",
  "narration": "Spoken text",
  "display_text": "SHORT TITLE",
  "feel": "emotional direction",
  "start_s": 0.0,
  "end_s": 5.0,
  "shots": [
    {
      "id": "s01",
      "duration_s": 4.5,
      "framing": "wide",
      "camera": "push",
      "scene": "visual content",
      "element_motion": "specific paper actions",
      "direction": {
        "primary_action": "one named subject performs one readable action",
        "physical_cause": "why the paper object moves",
        "motion_density": "low|medium|high"
      },
      "designed_holds": [
        {
          "start_s": 4.1,
          "end_s": 4.5,
          "reason": "hold the completed evidence for reading"
        }
      ],
      "show_display_text": true
    }
  ]
}
```

`start_s` and `end_s` are required only for `footage`. Beat IDs and shot IDs must be unique and
stable because artifact IDs derive from them.

When `motion.pipeline` is `layered` and `motion.directed_motion` is `true`, every shot requires
`direction.primary_action` and `direction.physical_cause`. The layer package expands that compact
direction into primary layer IDs, anticipation/action/settle phases, and optional designed holds.

## Runtime state

`state.json` is an artifact map:

```json
{
  "version": 1,
  "attempts": [
    {
      "group": "visual_source",
      "job_id": "image:b01-s01",
      "job_fingerprint": "sha256:...",
      "attempt_number": 1,
      "started_at": "ISO-8601 timestamp",
      "finished_at": "ISO-8601 timestamp",
      "status": "completed"
    }
  ],
  "approvals": {
    "story": {
      "approved_at": "ISO-8601 timestamp",
      "digest": "content fingerprint",
      "note": "user approved"
    }
  },
  "artifacts": {
    "image:b01-s01": {
      "path": "media/images/b01-s01.png",
      "url": null,
      "job_id": "image:b01-s01",
      "content_sha256": "sha256:...",
      "job_fingerprint": "sha256:...",
      "updated_at": "ISO-8601 timestamp"
    }
  }
}
```

Artifact prefixes:

- `style:<theme-id>`
- `image:<beat-id>-<shot-id>`
- `layers:<beat-id>-<shot-id>`
- `motion:<beat-id>-<shot-id>`
- `voice:main` for continuous narration, or legacy `voice:<beat-id>`
- `music:main`

Use `studio.py register`; it verifies that the file exists and writes state atomically.
Jobs executed through `job_runner.py` also receive a canonical job fingerprint. Changed prompts,
inputs, parameters, or seeds invalidate the old artifact. Metered calls are recorded before the
adapter runs; see [production-profiles.md](production-profiles.md).

Use `studio.py approve` for `story`, `style`, and `creative-qa`. Approvals contain fingerprints
and become stale when their governed content changes.
New creative-QA approvals include `final_content_digest`, a SHA-256 identity that remains stable
when a project is copied or installed. Legacy `final_signature` records remain readable.

## Job manifest

Each line in `jobs/<stage>.jsonl` is independent:

```json
{
  "id": "image:b01-s01",
  "stage": "images",
  "kind": "image_generation",
  "prompt": "...",
  "inputs": [],
  "params": {"aspect": "9:16"},
  "output": {"path": "media/images/b01-s01.png"},
  "meta": {"beat_id": "b01", "shot_id": "s01"}
}
```

The manifest is the boundary between creative direction and a provider implementation.

Layered projects add:

- `layer_package`: keyframe → `media/layers/<beat-shot>/layers.json` plus RGBA PNGs;
- `layers_to_video`: `layer_manifest` → deterministic motion MP4.

See [layered-motion.md](layered-motion.md) for the manifest and transform contract.
See [advanced-layer-primitives.md](advanced-layer-primitives.md) for registered pose states,
persistent visibility, looping strips, and seeded motif fields.
See [motion-audit.md](motion-audit.md) for follower inheritance, secondary-response declarations,
contact locks, and sampled continuity limits.
See [smooth-keyframes.md](smooth-keyframes.md) for the default whole-body keyframe strategy,
`motion_intent: "continuous"`, and interior-stop auditing.
See [articulated-rigs.md](articulated-rigs.md) for connected rigid-part hierarchies, joint pivots,
and planted-root review.
See [locomotion.md](locomotion.md) for two-leg chains, root travel, alternating plant locks, and
walk-cycle acceptance.

Execute a manifest with:

```bash
python scripts/job_runner.py <project-dir> --stage <stage> \
  --adapter <adapter.py> --dry-run
python scripts/job_runner.py <project-dir> --stage <stage> \
  --adapter <adapter.py> --retries 1
```

## Backend adapter contract

An adapter must:

1. Read one job object.
2. Map `kind`, `prompt`, `inputs`, and `params` to its API or local model.
3. Wait or return a resumable provider job ID.
4. Download/copy the final media to `output.path`.
5. Return either the legacy local `Path` or a structured result object.
6. Preserve the manifest ID for retries and logs.

A structured result may contain only:

```json
{
  "path": "media/audio/main.wav",
  "url": "optional provider result URL",
  "metadata": {
    "timing_path": "media/audio/main.timing.json",
    "provider": "provider-name",
    "model": "model-name",
    "duration_s": 29.8,
    "content_sha256": "optional digest"
  }
}
```

The runner verifies that media and timing files are non-empty and stay inside the project,
normalizes their paths, marks speech timing as `provided` or `missing`, and atomically registers
the artifact. Unknown metadata keys are rejected so credentials and unreviewed provider data
cannot leak into state. Path-only adapters remain compatible.

Adapters may add provider-specific metadata to their own log, not to `project.json`. Enforce a
concurrency limit and exponential backoff. Before retrying a paid generation, check whether the
provider already completed the same manifest ID.

Adding a provider must not require edits to story, visual prompt, state, or render code.

Start a Python integration by copying `assets/backend_adapter.py` from the skill directory.
Run `scripts/selftest.py` after changing the contract or an adapter.

See [delivery-qa.md](delivery-qa.md) for frame conversion, source-duration, designed-hold, and
final audio-level contracts.

The bundled production implementation is `scripts/replicate_backend.py`; its editable non-secret
template is `assets/replicate-backend.example.json`. See
[replicate-backend.md](replicate-backend.md) for preflight, execution, recovery, and privacy
controls.
