# Acceptance standard

Use this reference before declaring a collage-video project complete.

## Contents

- Gate sequence
- Quantitative checks
- Technical QA
- Human visual and audio review
- Completion definition

## Gate sequence

### Gate 0 — inputs

- Mode is correct: topic, footage, or photo.
- Source files exist and remain untouched.
- Language, duration, aspect, audience, and delivery goal are explicit.
- Photo mode has an anchor policy.
- Footage mode has usable source timing and an original-audio decision.

### Gate 1 — story approval

- Story validation has zero errors.
- Opening communicates a promise within three seconds.
- Each beat advances one claim or emotional turn.
- Narration fits the target duration.
- Neighboring shots vary framing and motion.
- User approved the beat map.
- `approval story` is valid for the current story fingerprint.
- A checkpoint records the approval.

### Gate 2 — style approval

- Exactly three genuinely different visual candidates were compared on the same beat.
- Candidates differ in medium, typography, texture, composition, and motion—not only color.
- User selected one candidate.
- `creative.theme` matches the selected candidate.
- `approval style` is valid for the current style fingerprint.
- A checkpoint records the selection.

### Gate 3 — keyframes

- Every required `image:*` artifact is registered, except footage mode.
- Each frame reads at thumbnail size.
- The focal hierarchy and title zone are deliberate.
- Layering is rich enough to animate.
- Faces, products, labels, and required text match the source and exact spelling.

### Gate 4 — motion

- Every required `motion:*` artifact is registered.
- Layered projects register every required `layers:*` artifact.
- Layered projects meet `min_layers` and `min_animated_layers` for every shot.
- Directed layered shots declare one primary action, one physical cause, ordered
  anticipation/action/settle phases, and their primary layers.
- Each shot has at most one clear camera action; a locked camera is acceptable.
- Element motion uses named paper objects and one-direction actions.
- No melting, morphing, visible loop resets, unwanted 3D, or invented objects.
- Intentional evidence holds are declared; there is no other freeze, shared keyframe stop,
  cadence jump, or abrupt direction reversal.
- Transform continuity audit passes at delivery cadence; no follower jump, opacity flash, or
  declared contact drift remains.
- Every continuous traveling layer reports zero unintended interior keyframe stalls.
- Secondary motion is driven by a named parent action and stops when that action settles.
- Subjects that use articulation declare one connected root hierarchy; every selected joint stays
  connected.
- Shots that explicitly depict realistic walking declare locomotion; left/right plant intervals
  alternate, lock both axes, and pass the sampled contact-drift audit. Stylized whole-body travel
  is accepted when it does not simulate a fake gait.
- Anchors and titles remain stable.

### Gate 5 — audio

- Every required `voice:*` artifact is registered, or footage mode explicitly preserves source
  audio.
- Newly directed narration includes a registered timing manifest; legacy provider output without
  one is identified as fallback rather than silently treated as phrase-synchronized.
- Narrator identity and delivery remain consistent.
- Speech is complete and not clipped.
- Pure-voice QA passes before music is mixed: measured phrase gaps stay within 0.50 seconds,
  leading silence within 0.25 seconds, final trailing silence within 0.60 seconds, and silence
  ratio within 25 percent.
- At least 75 percent of semantic boundaries receive a pause of 0.16 seconds or more, and no
  uninterrupted voiced run exceeds 5.5 seconds.
- When timing metadata exists, detected pauses overlap their planned semantic windows and phrase
  captions follow the same timing source.
- Music is instrumental when requested and does not compete with speech.

### Gate 6 — render

- `final.mp4` exists and is non-empty.
- Video and audio streams are present.
- Canvas, duration, pixel format, and timeline match the project.
- Captions and watermark reflect project configuration.

### Gate 7 — QA and handoff

- `qa/report.json` has zero errors.
- Extracted frames cover the beginning, middle, end, and important identity/text moments.
- A human completed the visual/audio checklist.
- `approval creative-qa` matches the current final file and QA report.
- A production report exists.
- A portable archive is created when handoff is requested.

## Quantitative checks

- Ordinary shot duration: 3–6 seconds.
- Shot duration over 7 seconds: requires a specific reason.
- Timeline duration tolerance: within 2% or 0.25 seconds, whichever is larger.
- Style candidates: exactly 3 by default.
- Missing registered production artifacts: 0.
- Technical QA errors: 0.
- Unreviewed identity, label, logo, or title-critical shots: 0.

Short offline tests may use sub-second shots; production projects may not use the test exception.

## Technical QA

Run:

```bash
python scripts/qa.py <project-dir>
```

The script checks:

- render readiness;
- final file size;
- duration;
- target canvas;
- video and audio streams;
- registered pure-voice continuity, including internal and cross-clip silence;
- pixel format;
- artifact file existence;
- layer-package structure and independently animated layer counts;
- watermark configuration;
- review-frame extraction.

Warnings require review. Errors block delivery.

## Human visual and audio review

For every project verify:

- The hook works without audio.
- The selected style remains coherent while compositions still vary.
- Faces, products, labels, logos, and display text do not drift.
- Motion serves the beat and does not feel like a repeated template.
- Captions remain readable and clear of the focal subject and platform-safe areas.
- Narration is intelligible; music ducks correctly; no syllables are clipped.
- The final beat resolves the opening promise.
- The ending does not cut abruptly.

## Completion definition

Do not say “complete,” “done,” or “ready to publish” merely because `final.mp4` exists.

A project is complete only when all seven gates pass, QA contains zero errors, and human creative
review has been performed. If human review is still pending, say “technically rendered; creative
review pending.”
