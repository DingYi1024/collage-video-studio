# Production profiles and evidence

Use this reference before starting paid generation or deciding whether an existing artifact is
still current.

## Profiles

New projects use a deterministic layered pipeline and the `balanced` profile:

```json
{
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
  }
}
```

The three profiles are:

| Profile | Minimum layers | Minimum animated | Default activity | Use |
|---|---:|---:|---|---|
| `draft` | 4 | 2 | editorial | fast structural proof |
| `balanced` | 6 | 3 | kinetic | normal polished short |
| `full-depth` | 8 | 4 | kinetic | hero scene or portfolio case |

The profile minimum is a floor, not an instruction to animate everything. A stable face,
horizon, floor, evidence card, or reference plane should remain still when motion would weaken
clarity.

`activity_profile` controls final-video cadence acceptance:

- `calm`: deliberate reading and evidence holds;
- `editorial`: regular visual changes with restrained movement;
- `kinetic`: social-short cadence with no long low-motion passage.

Exact freeze detection is separate. A video can contain no duplicate frames and still feel dead;
the activity audit catches that case.

## Exact attempt ledger

Every adapter invocation in a metered group is appended to `state.json.attempts` before the call.
Successes and failures both consume an attempt because both may have reached a provider.

Groups:

- `visual_source`: image generation, image editing, and layer-package generation;
- `generative_motion`: image-to-video and video editing;
- `voice`: speech generation;
- `music`: music generation.

Deterministic `layers_to_video` rendering does not consume a provider attempt.

When a limit is exhausted, the runner stops before another call. Raise one explicit limit only
after reviewing the ledger and provider state. Do not delete failed attempts to create hidden
budget.

## Fingerprints and invalidation

The runner fingerprints the complete canonical job object. A change to prompt, input, parameter,
seed, duration, or output contract makes the old registered artifact stale. Successful artifacts
store:

- `content_sha256`: identity of the local file;
- `job_fingerprint`: identity of the task that produced it.

QA stores one `qa_input_fingerprint` covering the project, registered artifact identities, and
final video content. `project_ops.py next` sends a project back to QA when this evidence no longer
matches, even when file timestamps happen to look current.

Legacy projects remain readable. Their artifacts without job fingerprints are accepted until
that job is rerun.

