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
- [advanced-layer-primitives.md](references/advanced-layer-primitives.md) before authoring
  registered source families, pose sequences, persistent visibility, looping strips, or seeded
  motif fields;
- [editorial-composition.md](references/editorial-composition.md) before authoring recursive
  groups, editable text/data graphics, camera-coupled parallax, or responsive director plans;
- [semantic-contracts.md](references/semantic-contracts.md) before generating a named identity,
  spatial topology, mechanism explanation, or infographic;
- [quality-gates.md](references/quality-gates.md) before accepting cutouts or compiled scenes;
- [responsive-direction.md](references/responsive-direction.md) when delivering more than one
  aspect ratio;
- [provider-lifecycle.md](references/provider-lifecycle.md) before paid generation, rejection,
  recovery, superseding, or deliberate artifact reuse;
- [production-profiles.md](references/production-profiles.md) before paid generation; it defines
  draft/balanced/full-depth floors, exact attempt budgets, artifact fingerprints, and QA
  invalidation;
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
- [production-closure.md](references/production-closure.md) for the Remotion editor, exact
  narration-led frames, semantic execution, registered depth stacks, and three proof types;
- [voice-continuity.md](references/voice-continuity.md) before writing, generating, or approving
  narration;
- [delivery-qa.md](references/delivery-qa.md) before rendering or diagnosing jerky motion,
  frozen shot tails, or final-mix loudness;
- [aspect-direction.md](references/aspect-direction.md) before locking landscape or portrait;
- [project-schema.md](references/project-schema.md) when editing files or backends;
- [operations.md](references/operations.md) when resuming, recovering, or executing jobs;
- [replicate-backend.md](references/replicate-backend.md) for the bundled production backend;
- [acceptance.md](references/acceptance.md) before claiming completion.

## Gate 1 — approve the story

Fill `creative.arc`, `beats`, and `shots`.

- Make the opening understandable within three seconds.
- Give each beat one claim or emotional turn.
- Declare semantic contracts for identity, topology, mechanism, and infographic claims.
- Give every factual claim a proof moment inside the beat that presents it.
- Set `transition_intent` from reveal, compare, traverse, explain, emphasize, change-time, or
  change-place; let the compiler choose a consistent mechanism.
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

New topic and photo projects default to deterministic layered motion. Use generative
image-to-video only when the user explicitly values model-created deformation over editability
and repeatability; repeat the media stages for `motion`, `voice`, and `music`.

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
motion. For smooth delivery, all new production projects default to 30 fps. Keep
`motion.frame_conversion: "auto"` so below-target provider clips are motion-interpolated instead
of padded with duplicate frames. Use continuous curves for
interior keyframes, stagger looping objects with `phase_s`, and inspect the MP4 rather than a
low-frame-rate GIF. Use 2× oversampling when slow movement shows one-pixel stepping. Footage mode
skips `images` and `layers`; footage preserving original audio skips `voice`.

For editorial work, author one recursive composition and compile separate director plans:

```bash
python scripts/editorial_contract.py composition.json \
  --kind composition --output result/manifests
python scripts/asset_quality.py result/manifests/composition-9x16.json \
  --mode composition
```

Do not crop a landscape layout into portrait. Re-place title, subject, data, annotations, and
background papers through node overrides. Validate safe zones and editable text fit for every
aspect. Use local vector/text/chart primitives when the content must remain exact and editable.
Use `data-svg` for structured paths, curves, labels, and marks. Give annotations explicit
exclusions; the compiler must find a collision-free position across all annotations or stop.

Inspect and edit the same manifest in the real Remotion workspace:

```bash
cd workspace
npm ci
npm run dev
```

The Player must preserve recursive groups, depth, keyframes, edit points, and the selected
director plan. Validate with `npm run build` and `npm run render` before release.

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
crossfade unrelated silhouettes. Use a registered `pose_sequence` for authored subject states.
Use legacy `sprites` only for old packages or closely registered small cycles such as a blink.
Use persistent `visibility` events instead of one-frame show/hide commands. Use
`looping_strip` for genuinely repeating scenery and a seeded `motif_field` for repeatable paper
accents. Read [advanced-layer-primitives.md](references/advanced-layer-primitives.md).

Use articulation only when a close, story-critical joint action improves the shot. In that case,
build rigid parts, declare an `articulated-paper` rig, and follow
[articulated-rigs.md](references/articulated-rigs.md). Use the optional two-leg
[locomotion.md](references/locomotion.md) contract only when the shot explicitly promises
realistic visible walking; stylized whole-body paper travel does not require a gait rig.

For reproducible natural narration, set `project.language` and configure
`audio.voice.profile`, `voice_id`, `rate`, `pitch`, and `direction`. Keep `voice_id: "auto"` for
the bundled Chinese, English, Japanese, Korean, French, German, Spanish, Portuguese, or Italian
Edge voice default; require an explicit provider voice for any other language. Default new
narrated shorts to `audio.voice.continuity_mode: "continuous"` so the full performance is
generated as `voice:main`, not as fixed-length padded phrases. Then run:

```bash
python scripts/voice_director.py <project-dir> --dry-run --json
python scripts/voice_director.py <project-dir> --overwrite
```

The voice director uses language-aware punctuation, protects abbreviations and decimals, and
balances unpunctuated long sentences into safety phrases. It synthesizes one stable voice,
assembles a mastered 48 kHz mono WAV at -18 LUFS, writes a sibling `.timing.json`, registers
both in project state, and by default rewrites beat/shot durations from the measured performance.
Choose `energetic`, `conversational`, `measured`, or `dramatic`; override
individual pauses only when the named profile is insufficient. Keep natural phrase gaps near
0.15–0.30 seconds. Reject both excessive blank time and breathless delivery: at least 75% of
semantic boundaries need a pause of 0.16 seconds or more, and no uninterrupted voiced run may
exceed 5.5 seconds. Shorten or expand the copy, adjust punctuation, or change scene timing; do
not clip a phrase, pad a short sentence to fill a fixed scene, or hide mechanical time-stretching
in the final mix. When captions are enabled, render phrase-level cues from the timing manifest;
use whole-beat captions only as a legacy fallback.

Recompile an existing measured voice manifest explicitly:

```bash
python scripts/timing_compiler.py <project-dir> --apply
```

The compiler adds only `audio.voice.visual_tail_s`, allocates integer delivery frames to every
shot, writes `build/timing-proof.json`, and invalidates stale approvals. `--fixed-timeline` is a
legacy opt-out on `voice_director.py`; do not use it to hide an under-specified production.

Job kinds route to backend capabilities:

- `image_generation`
- `image_edit`
- `image_to_video`
- `video_edit`
- `layer_package`
- `layers_to_video`
- `speech`
- `music`

The runner skips registered jobs only when their job fingerprints still match, persists progress
after every successful file, and appends reserve/completed/failed events around every metered
adapter call. Review a manifest and run a small batch before a large paid stage. Never erase
failed or rejected attempts. Record recovery, superseding, and deliberate reuse as new lifecycle
events; audit with `provider_lifecycle.py audit <project-dir>/state.json`. Use `--only` to rerun the
smallest failed unit. A speech adapter
should return a structured result containing `path` and
`metadata.timing_path`; the runner validates and registers both. Legacy path-only adapters remain
compatible, but speech without timing metadata is explicitly marked `timing_status: "missing"`
and uses beat-caption fallback.

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

QA must inspect registered pure-voice artifacts before the music mix. A present final audio stream
and correct total duration do not prove narration continuity. When a timing manifest exists, QA
must verify that measured pauses occur at their intended semantic boundaries, not merely somewhere
in the recording. Treat missing breathing pauses, misplaced pauses, and excessive internal,
leading/trailing, or cross-clip silence as delivery-blocking errors.

QA must also verify the final constant frame rate, detect whole-frame freezes in every motion
pipeline, reject undeclared source-tail holds and duplicate-frame conversion below the delivery
rate, and measure final integrated loudness and true peak. A source below 23.85 fps may be
interpolated with a warning, but sources below 12 fps remain delivery-blocking. Read
[delivery-qa.md](references/delivery-qa.md) for the policy and `designed_holds` contract.
Run the independent motion-activity audit as well: exact duplicate-frame checks cannot detect a
technically changing but perceptually dead shot. The selected calm/editorial/kinetic profile sets
the allowed low-motion run and ratio. QA evidence is stale whenever project, artifact, or final
content fingerprints change.

Before final QA, require both visual quality gates:

```bash
python scripts/asset_quality.py <project-dir>/assets.json --mode assets
python scripts/asset_quality.py <project-dir>/media/layers/<shot>/layers.json \
  --mode composition
```

Use observed-border chroma cleanup when needed. Never accept a flattened asset as an editable
cutout or a compiled scene merely because each source file exists.

Inspect the extracted frames and complete the human checklist in
[acceptance.md](references/acceptance.md). A file existing is not proof of creative correctness.
Extract declared claim evidence with:

```bash
python scripts/proof_review.py <project-dir>/final.mp4 \
  <project-dir>/reports/editorial-plan.json <project-dir>/qa/proof
```

Complete every pending proof check against its semantic evidence.
Build all three evidence classes:

```bash
python scripts/proof_system.py <project-dir> --register style --approve <theme-id>
python scripts/proof_system.py <project-dir> --register composition <manifest>
python scripts/proof_system.py <project-dir> --register moment \
  <project-dir>/final.mp4 <project-dir>/reports/editorial-plan.json
```

Style proof must compare exactly three themes on the same representative beat. Composition proof
must pass automatic layer, motion, semantic, annotation, and edit-point checks. Moment proof
must remain pending until every extracted factual frame is reviewed; never auto-approve it.
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
cd workspace && npm ci && npm run build
python scripts/package_skill.py
```

The offline test covers recursive composition, three-aspect direction, editable text/data-SVG
primitives, annotation collision avoidance, semantic identity/topology/mechanism/infographic
checks, registered depth stacks, semantic transition execution, all three proof contracts,
narration-measured exact-frame compilation, append-only
provider lifecycle, observed-key cleanup, two-stage quality gates, registered source extraction,
pose sequences, persistent visibility,
looping strips, seeded motif fields, production budgets, job/QA fingerprints, multilingual
voice defaults, abbreviations, decimals, safety phrase
splits, timing-manifest QA, phrase-level caption cues, the production adapter's six provider routes
and no-resubmit guard,
multi-layer manifest validation and rendering, manifests, all production stages, three input-mode
contracts, render, QA, approvals, checkpoints, resume routing, reports, and packaging. The
packaging command refuses to build when the self-test fails.
