# Production Protocol v4

Use this protocol for every new production. It joins story scope, provider spend, source
topology, measured narration, runtime execution, proof, and cache invalidation into one
auditable chain.

## Three scenarios before provider spend

Compile exactly three scenarios before a quota-consuming request:

```bash
python scripts/production_protocol.py scenarios project.json \
  --output build/scenarios.json
python scripts/production_protocol.py approve build/scenarios.json balanced \
  --note "approved story depth and exact visual attempt cap" \
  --output build/scenario-decision.json
```

All options share the same semantic actions. They differ in production depth, recovery reserve,
and minimum execution promise. Each states expected calls, local derivatives, isolated calls
avoided, profile ceiling, and the narrower human-approved cap. Rejected results still consume
the cap. Deterministic derivatives, SVG, charts, and local keyframes do not.

Copy the approved cap to `production.approved_visual_attempt_cap`. Never reserve visual work
while it is absent or zero.

## Rhythmic storyboard

Every scene needs at least three contiguous rhythm phases covering normalized `0..1`, one or
more visible-change treatments, explicit semantic actions, source-package ids, and establish,
action/peak, and final proof moments. Final proof stays at or after `0.82`. Any critical sound
binds to the same proof id as its visual event.

```bash
python scripts/production_protocol.py storyboard \
  project.json build/scenarios.json build/scenario-decision.json \
  --output build/storyboard.json
```

The compiled scenario promise is an execution floor as well as a budget ceiling.

## Complete source families

Use one relationship contract:

| Relationship | Required source topology |
|---|---|
| `free` | independent cutout or editable primitive |
| `supported-subject` | complete rear support, subject, front support |
| `registered-environment` | complete upper/lower members on one canvas |
| `registered-depth-stack` | complete rear, full subject, complete front |
| `looping-environment` | seamless far/ground plus optional mid/near strips |

`bounded-relative` is legal only for a registered depth stack and requires all three aspect
reveal envelopes. Large subject motion uses a separate subject travel envelope.

```bash
python scripts/registered_family.py raw-sheet.png family-spec.json \
  media/registered/hero-family
```

The output has full-canvas derivatives, common registration, immutable source SHA, observation
metadata, and one family fingerprint. Never trim or replace one member in isolation. Recovery
order is local reprocessing, context-preserving complete-source edit, then complete-source
regeneration.

## Provider-native key observation

Preserve the untouched provider file and observe its actual plane before keying:

```bash
python scripts/asset_quality.py raw.png --mode observe-key
python scripts/asset_quality.py raw.png --mode key --output cutout.png
```

The observation binds source SHA, accepted RGB, statistics, policy fingerprint, and observation
fingerprint. The alpha gate then checks transparent RGB, spill, partial edges, crop safety, and
low-alpha rectangular residue. Machine evidence does not replace viewing silhouettes, negative
spaces, and family reconstruction.

## Append-only lifecycle

Reserve through `job_runner.py`. It enforces the approved cap. Record completed, failed, or
rejected outcomes. Recovery, superseding, and reuse are new events, never history edits. A
rejected artifact can enter derivation only through `recovery-source`; its rejected status and
consumed quota remain.

## Measured narration owns frames

Generate one continuous voice performance by default and preserve semantic pauses:

```bash
python scripts/timing_compiler.py <project-dir> --apply
```

Measured duration allocates exact scene and shot frames. Do not stretch estimates or pad flat
tails. A quiet hold is bounded, authored, and proof-bound.

If pure-voice loudness fails:

```bash
python scripts/audio_calibration.py propose project.json preflight.json \
  --output build/audio-calibration.json
```

Acceptance requires the exact source fingerprint and a human note. Source/timing changes
invalidate it. Audio-only changes may reuse a valid visual stream for remux.

## Audiovisual events and boundaries

`events` is the single visual/sound catalog. Visibility persists; emphasis is transient; holds
are bounded. Critical sound and visual action share a proof id.

Boundary intent and execution are separate. Continuity, location, time, focus, and chapter
changes route to opaque paper mechanisms. A cut is zero-duration and motivated. Proof samples
inspect before/at/after frames for opaque coverage, direction, and false semantic blends.

## Preview revision

```bash
python scripts/preview_revision.py approved.json candidate.json \
  --output-project project.json \
  --output-record reports/directing-revision.json
```

Directing-only feedback can change execution but not approved meaning, semantic contracts,
source packages, or budget. Authorized semantic revision needs an allowlist, human note, and
equivalent evidence, then invalidates all dependent proofs.

## Incremental proof and runtime identity

```bash
python scripts/runtime_fingerprint.py . --output runtime-build.json
```

Composition, subtitle, audio, provider, and protocol surfaces invalidate independently.
Subtitle-only changes preserve asset/composition evidence. Audio-only changes allow remux.
Provider/protocol/compositor changes invalidate dependent visual proof.

Style proof compares exactly three candidates on one beat. Composition proof checks the real
recursive manifest and semantic relationships. Moment proof remains human-reviewed. Every proof
is source- and runtime-fingerprinted.

## Executable Remotion workspace

The workspace must render recursive nodes, state sequences, persistent visibility, transient
emphasis, looping strips, motif fields, audiovisual events, edit points, proof moments, and
responsive plans:

```bash
cd workspace
npm ci
npm run build
npm run render
```

Inspect 16:9, 9:16, and 1:1 as separate director plans for one story. Do not crop one layout
into another or hide aspect branches in renderer code.
