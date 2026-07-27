# Operations, recovery, and backend execution

Use this reference when continuing an existing project, running provider jobs, recovering state,
creating reports, or packaging a handoff.

## Contents

- Resume routing
- Checkpoints and restore
- Running media jobs
- Failure recovery
- Reports and packages
- Input and cost safety

## Resume routing

Run:

```bash
python scripts/project_ops.py next <project-dir>
```

The command evaluates project structure, approvals, registered artifacts, final render, and QA.
Follow its single returned action. Do not invent a fixed sequence when the project is already
partially complete.

Use `studio.py status --verbose` for the full artifact gap list.

## Checkpoints and restore

Create a checkpoint after:

- story approval;
- visual-direction selection;
- a completed keyframe batch;
- a completed motion batch;
- approved audio;
- any manual correction that would be expensive to reconstruct.

```bash
python scripts/project_ops.py checkpoint <project-dir> --note "story approved"
python scripts/project_ops.py history <project-dir>
```

Checkpoints are immutable timestamped copies of `project.json` and `state.json`. Media is not
duplicated.

Approval records are content-addressed:

```bash
python scripts/studio.py approve <project-dir> --gate story --note "user approved"
python scripts/studio.py approve <project-dir> --gate style --note "user approved"
python scripts/studio.py approve <project-dir> --gate creative-qa \
  --note "human review completed"
```

Editing the associated story/style content invalidates its old approval. Regenerating the final
video or QA report invalidates the old creative-QA approval.
Creative-QA records use the final video's content digest, so copying, installing, or unpacking a
project does not invalidate approval merely because filesystem timestamps changed.

Restore only when the user asks to go back to a known state:

```bash
python scripts/project_ops.py restore <project-dir> <checkpoint-id-or-index> --yes
```

Restore first creates an automatic safety checkpoint. It does not delete media; previously
generated files can be registered again if needed.

## Running media jobs

First generate and inspect the manifest:

```bash
python scripts/studio.py jobs <project-dir> --stage images
python scripts/job_runner.py <project-dir> --stage images \
  --adapter <adapter.py> --dry-run
```

Then run:

```bash
python scripts/job_runner.py <project-dir> --stage images \
  --adapter <adapter.py> --retries 1
```

Useful controls:

- `--only id1,id2`: run selected jobs.
- `--limit N`: run a small validation batch.
- `--continue-on-error`: finish independent jobs and report failures.
- `--retries N`: bound paid retries.

The runner skips registered job IDs and writes state after every successful output. The adapter
must use provider idempotency keys when available.

Adapters may return a local path for backward compatibility, or a structured object containing
`path`, optional `url`, and bounded metadata. Speech adapters should include
`metadata.timing_path`; the runner validates it, keeps it inside the project, and records
`timing_status: "provided"`. Path-only speech results are explicitly marked `missing`.

For a manually produced voice artifact:

```bash
python scripts/studio.py register <project-dir> voice:main media/audio/main.wav \
  --timing-path media/audio/main.timing.json
```

`scripts/mock_backend.py` is only for offline integration testing. Never present its placeholder
media as a deliverable.

For the bundled real-media adapter, read
[replicate-backend.md](replicate-backend.md). It keeps content-addressed provider records, resumes
submitted predictions, downloads expiring outputs, and requires an explicit release before a
failed or expired job can be submitted again.

## Failure recovery

Diagnose at the smallest unit:

1. Run `studio.py status --verbose`.
2. Inspect the failed job line in the manifest.
3. Check input files, aspect support, duration limits, and adapter logs.
4. Correct the earliest faulty stage.
5. Rerun only the failed job ID.
6. Register the result and run `project_ops.py next`.

Do not delete successful assets or restart the whole project to fix one unit.

For creative defects:

- weak composition → reroll `image:*`;
- identity/text drift → strengthen locks and reroll `image:*` before `motion:*`;
- melting/looping → simplify camera and motion constraints, reroll `motion:*`;
- timing mismatch → inspect the voice dry-run and `.timing.json`, regenerate or edit `voice:*`,
  then rerender;
- caption or mix issue → rerender only.

## Reports and packages

Generate a grounded report from project, state, checkpoints, and QA:

```bash
python scripts/project_ops.py report <project-dir>
```

Create a portable archive:

```bash
python scripts/project_ops.py package <project-dir>
python scripts/project_ops.py package <project-dir> --without-media
```

The package excludes render scratch files, checkpoint internals, and previous exports.

## Input and cost safety

- Never modify source footage or source photos.
- Never store API keys in project files, manifests, reports, or state.
- Show aspect substitutions before generation.
- Review a manifest and run a small batch before large paid stages.
- Bound concurrency and retries in the provider adapter.
- Check the provider for an existing completed job before resubmitting.
- Treat restore as a state-changing action and require `--yes`.
- Keep watermarks empty unless the user supplies exact text.
