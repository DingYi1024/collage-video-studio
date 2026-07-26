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

If no project or usable brief exists, ask only for the idea/source, target duration, and language.
Use `--aspect auto` unless the user or target platform already fixes the frame. Show the resolved
aspect and reason in the first beat-map review.

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
  --topic "<topic>" --duration 30 --aspect auto --language zh
```

Read:

- [story-system.md](references/story-system.md) before writing beats;
- [visual-system.md](references/visual-system.md) before writing themes or prompts;
- [layered-motion.md](references/layered-motion.md) when independently moving layers or
  deterministic parallax are required;
- [directed-motion.md](references/directed-motion.md) before animating a portfolio-grade layered
  shot; it defines primary action, physical cause, three-phase timing, density, and holds;
- [motion-audit.md](references/motion-audit.md) when adding follower layers, contact locks, or
  checking transform jumps before delivery;
- [smooth-keyframes.md](references/smooth-keyframes.md) before animating people or objects when
  fluid playback matters more than anatomical realism;
- [articulated-rigs.md](references/articulated-rigs.md) when a person, animal, or mechanism needs
  connected shoulder, elbow, wing, wheel, or hinge motion;
- [locomotion.md](references/locomotion.md) before moving an articulated character root across
  the frame; it defines alternating planted feet and full-body walk-cycle review;
- [production-standard.md](references/production-standard.md) for portfolio-grade paper
  animation, authored poses, natural voice, and social-video delivery quality;
- [aspect-direction.md](references/aspect-direction.md) before locking landscape or portrait;
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
- For directed layered work, add `shot.direction.primary_action`, `physical_cause`, and
  `motion_density`. One shot gets one readable primary action.
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

When the request only needs generative image-to-video motion, repeat for `motion`, `voice`, and
`music`.

When the request requires independently moving paper objects, editable parallax, or explicit
foreground/middle/background control, set `motion.pipeline` to `layered`, then execute:

```bash
python scripts/studio.py jobs <project-dir> --stage layers
python scripts/job_runner.py <project-dir> --stage layers --adapter <layer-aware-adapter.py>
python scripts/studio.py jobs <project-dir> --stage motion
python scripts/job_runner.py <project-dir> --stage motion --adapter <layer-aware-adapter.py>
```

Read [layered-motion.md](references/layered-motion.md) for the transparent PNG and `layers.json`
contract. Do not represent a flattened keyframe with whole-frame zoom or pan as multi-layer
motion. For smooth delivery, default new layered projects to 30 fps, use continuous curves for
interior keyframes, stagger looping objects with `phase_s`, and inspect the MP4 rather than a
low-frame-rate GIF. Use 2× oversampling when slow movement shows one-pixel stepping. Footage mode
skips `images` and `layers`; footage preserving original audio skips `voice`.

For polished work, set `motion.directed_motion` to `true` and follow
[directed-motion.md](references/directed-motion.md). Do not animate every layer to satisfy a
quota. Declare the primary layers, physical cause, anticipation/action/settle phases, and any
intentional reading hold. A face, floor, horizon, or table should normally stay stable while the
evidence moves. Use per-keyframe arrival `ease` when anticipation and settling need different
timing.

Attach wheels, hinged parts, flame, clothing, and other motivated secondary responses with
`follow`; inherit only the parent properties they physically share. Declare
`direction.secondary_responses` and lock planted or landed properties with `direction.contacts`.
Run `layer_compositor.py <layers.json> --audit` before rendering. Fix speed, rotation, scale,
opacity, or contact-drift failures instead of raising limits to hide them.

Prioritize continuity over anatomical simulation. Default a moving person to one stable
whole-body cutout, or a root plus one or two useful parts, and animate it with authored
keyframes. Mark traveling layers `motion_intent: "continuous"` and use `catmull-rom` through
interior points; use arrival/settle easing only at the outside edges. Enable
`motion_audit.enforce_smooth_keyframes` and sample at delivery fps. Do not use repeated
`smoothstep` segments that stop at every interior keyframe. Read
[smooth-keyframes.md](references/smooth-keyframes.md) for the default contract.

Change a major character pose at a shot cut or behind a foreground paper occluder; never
crossfade unrelated silhouettes. Use `sprites` only for closely registered small states such as
a blink or mouth shape.

Use articulation only when a close, story-critical joint action improves the shot. In that case,
build rigid parts, declare an `articulated-paper` rig, and follow
[articulated-rigs.md](references/articulated-rigs.md). Use the optional two-leg
[locomotion.md](references/locomotion.md) contract only when the shot explicitly promises
realistic visible walking; stylized whole-body paper travel does not require a gait rig.

For a reproducible natural Mandarin demo, configure `audio.voice.voice_id`, `rate`, `pitch`, and
`direction`, then run:

```bash
python scripts/voice_director.py <project-dir> --dry-run
python scripts/voice_director.py <project-dir> --overwrite
```

The voice director masters each beat to 48 kHz mono WAV at -18 LUFS and rejects copy that exceeds
the available scene duration. Shorten the spoken copy or change scene timing; do not clip a phrase
or hide mechanical time-stretching in the final mix.

Job kinds route to backend capabilities:

- `image_generation`
- `image_edit`
- `image_to_video`
- `video_edit`
- `layer_package`
- `layers_to_video`
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

The offline test covers the production adapter's six provider routes and no-resubmit guard,
multi-layer manifest validation and rendering, manifests, all production stages, three input-mode
contracts, render, QA, approvals, checkpoints, resume routing, reports, and packaging. The
packaging command refuses to build when the self-test fails.
