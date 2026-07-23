---
name: collage-video-studio
description: Create, resume, audit, recover, package, and extend editable editorial paper-collage video projects from a topic, talking-head recording, or portrait/product photo. Use for collage explainers, scrapbook motion pieces, cut-paper ads, zine-style shorts, narrated visual essays, photo-anchored promos, footage restyling, continuing an existing project, rerunning failed shots, connecting a media backend, technical QA, or producing a handoff package.
---

# Collage Video Studio

Direct a production as a resumable project. Keep creative intent in `project.json`, generated
results in `state.json`, provider execution behind JSONL manifests, and derived output in
`media/`, `qa/`, `reports/`, and `exports/`.

## Route the request

Read the conversation and inspect any supplied project directory before asking for information
the user already provided.

| User intent | Action |
|---|---|
| Start, make, create | Initialize and draft the story |
| Continue, resume, what next | Run `project_ops.py next` and execute its single action |
| Status, blocked, failed | Run `studio.py status --verbose`, then diagnose the smallest unit |
| Save, checkpoint | Create an immutable project/state checkpoint |
| Go back, restore | List checkpoints; restore only the user-selected one |
| Audit, check, ready to publish | Run technical QA, then human creative review |
| Report, package, handoff | Generate a grounded report and portable archive |
| Add or change provider | Read the backend contract and implement an adapter |

If no project or usable brief exists, ask only for the idea/source, target duration, aspect, and
language. Infer reasonable defaults for the rest and show them in the first beat-map review.

## Select the input mode

- `topic`: create narration and visuals from an idea.
- `footage`: restyle an existing performance video while retaining timing and original audio.
- `photo`: anchor one real portrait or product photo into generated scenes.

Never alter the original photo or footage.

## Initialize

Locate this skill directory, then run:

```bash
python scripts/studio.py doctor
python scripts/studio.py init <project-dir> --mode topic \
  --topic "<topic>" --duration 30 --aspect 9:16 --language zh
```

Read:

- [story-system.md](references/story-system.md) before writing beats;
- [visual-system.md](references/visual-system.md) before writing themes or prompts;
- [project-schema.md](references/project-schema.md) when editing files or backends;
- [operations.md](references/operations.md) when resuming, recovering, or executing jobs;
- [replicate-backend.md](references/replicate-backend.md) for the bundled production backend;
- [acceptance.md](references/acceptance.md) before claiming completion.

## Gate 1 — approve the story

Fill `creative.arc`, `beats`, and `shots`.

- Make the opening understandable within three seconds.
- Give each beat one claim or emotional turn.
- Prefer context plus detail: two varied shots per narrated beat.
- Keep ordinary production shots between 3 and 6 seconds.
- Write concrete `element_motion`; do not use “make it dynamic.”
- For footage, set beat `start_s` and `end_s`.
- For a photo, define `source.anchor_policy`.

Run:

```bash
python scripts/studio.py validate <project-dir> --stage story
```

Show the beat map to the user. Do not generate media before approval. After approval:

```bash
python scripts/studio.py approve <project-dir> --gate story --note "user approved"
python scripts/project_ops.py checkpoint <project-dir> --note "story approved"
```

## Gate 2 — approve the visual direction

Create exactly three candidates under `creative.candidate_themes`. Make them differ in medium,
palette, typography, texture, composition, and motion character.

```bash
python scripts/studio.py jobs <project-dir> --stage styles
```

Execute every preview on the same representative beat and register each result. Show all three
together. After the user chooses:

```bash
python scripts/studio.py choose-theme <project-dir> <theme-id>
python scripts/studio.py approve <project-dir> --gate style --note "user approved"
python scripts/project_ops.py checkpoint <project-dir> --note "visual direction approved"
```

Never silently substitute an unsupported aspect ratio.

## Produce media

For each stage:

```bash
python scripts/studio.py jobs <project-dir> --stage images
python scripts/job_runner.py <project-dir> --stage images \
  --adapter <adapter.py> --dry-run
python scripts/job_runner.py <project-dir> --stage images \
  --adapter <adapter.py> --retries 1
```

Repeat for `motion`, `voice`, and `music`. Footage mode skips `images`; footage preserving
original audio skips `voice`.

Job kinds route to backend capabilities:

- `image_generation`
- `image_edit`
- `image_to_video`
- `video_edit`
- `speech`
- `music`

The runner skips registered jobs and persists progress after every successful file. Review a
manifest and run a small batch before a large paid stage. Use `--only` to rerun the smallest
failed unit.

`scripts/mock_backend.py` is test-only. Never use its placeholder media in a deliverable.

For real media, the Skill includes `scripts/replicate_backend.py`. Read
[replicate-backend.md](references/replicate-backend.md), install its SDK, keep the token in
`REPLICATE_API_TOKEN`, run its `doctor` command, and test one paid job before a batch. Its local
provider records resume existing predictions and block silent duplicate submission.

## Resume and recover

Run:

```bash
python scripts/project_ops.py next <project-dir>
python scripts/studio.py status <project-dir> --verbose
```

Follow the returned current action instead of restarting.

Create checkpoints after expensive or approved milestones. Before reverting:

```bash
python scripts/project_ops.py history <project-dir>
python scripts/project_ops.py restore <project-dir> <id-or-index> --yes
```

Restore creates a safety checkpoint first and does not delete media.

## Render, QA, and hand off

```bash
python scripts/render.py <project-dir>
python scripts/qa.py <project-dir>
```

Inspect the extracted frames and complete the human checklist in
[acceptance.md](references/acceptance.md). A file existing is not proof of creative correctness.
After the user or responsible reviewer accepts the visual and audio result:

```bash
python scripts/studio.py approve <project-dir> --gate creative-qa \
  --note "human visual and audio review completed"
```

Then generate grounded deliverables:

```bash
python scripts/project_ops.py report <project-dir>
python scripts/project_ops.py package <project-dir>
```

Say “complete” only after all acceptance gates pass. Otherwise report the exact current gate,
what passed, what remains, and the next executable action.

## Preserve identity, text, and user control

- Treat faces, product geometry, labels, logos, and user footage as locked evidence.
- Apply paper texture to the environment unless transformation of the anchor is authorized.
- Put large display text in the image or local overlay stage; motion should preserve it.
- Reattach original audio for footage mode.
- Default to no watermark.
- Keep API keys out of project files, manifests, reports, and state.
- Bound retries and provider concurrency; avoid duplicate paid submissions.

## Validate the Skill itself

After modifying this Skill or an adapter, run:

```bash
python scripts/selftest.py
python scripts/package_skill.py
```

The offline test covers the production adapter's six job routes and no-resubmit guard, manifests,
all production stages, three input-mode contracts, render, QA, approvals, checkpoints, resume
routing, reports, and packaging. The packaging command refuses to build when the self-test fails.
