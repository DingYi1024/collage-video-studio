# Production Protocol v5

Use this protocol for every new production. It closes planning, persistent-world,
registered-state, readiness, subtitle-delivery, quality-lifecycle, and observability surfaces.

## 1. Intake before planning

Show the three bundled versioned style cards, then record one aspect, style, and parallax choice:

```bash
python scripts/intake.py show
python scripts/intake.py choose --aspect 16:9 --style bold-editorial \
  --parallax cinematic --note "user choice" \
  --output <project>/build/intake-decision.json
```

Do not spend provider quota during intake. Compile the production scenarios after the decision.

## 2. Protect intentional stillness

Set a beat or node to `motion_policy: locked-static` when the approved directing choice is a
deliberate still composition. A locked scene does not count toward a profile animation floor.
Do not add decorative motion merely to satisfy a numerical target.

## 3. Persistent looping worlds

Use `looping-environment` only for sustained horizontal travel through an unbounded world.
Use registered depth stacks for finite reveals and `motif_field` for small repeated accents.

A complete world declares:

- horizontal direction and at least one viewport of travel;
- far and ground strips, with optional mid and near strips;
- strictly increasing absolute strip speed from far to near;
- one tracked participant plus additional screen- or world-anchored participants;
- near-layer occlusion relationships;
- before, seam, and after proof times;
- signed trajectory requirements and optional final participant order;
- independent 16:9, 9:16, and 1:1 director plans.

Each strip retains provenance, a canonical tile, render height, edge thresholds, and enough
resolved width for one viewport. Runtime repeats the tile; do not duplicate image nodes manually.

```bash
python scripts/world_motion.py composition.json \
  --output proofs/world/report.json \
  --evidence-dir proofs/world/evidence
```

Block failed RGB/alpha seams, uncovered profiles, wrong depth-speed order, insufficient
camera-compensated travel, wrong signed direction, invalid final order, or bad occlusion order.

## 4. Registered state families and repairs

Derive related identity states from one complete registered sheet. Every state declares facing
and an identity anchor; important hands, props, wheels, or contacts may add anchors. Derivation
emits full-canvas states, anchor overlays, and a drift report.

Recovery order:

1. deterministic local reprocessing;
2. masked edit using the complete original source as context;
3. complete source-family regeneration.

Never splice an independently generated state into a registered family.

```bash
python scripts/context_repair.py original.png repaired.png repair.json \
  --output proofs/repair.json
```

Pixels outside the mask and every accepted region must remain byte-equivalent.

## 5. Surface-bound quality review

Bind approval to one surface, target, report, evidence set, contact sheet, and runtime fingerprint:

```bash
python scripts/quality_lifecycle.py scaffold \
  --surface world-motion --target scene-03 \
  --report proofs/world/report.json \
  --contact-sheet proofs/world/contact.png \
  --evidence proofs/world/evidence/seam.png \
  --runtime-fingerprint sha256:... \
  --output proofs/world/scaffold.json
python scripts/quality_lifecycle.py approve proofs/world/scaffold.json \
  --reviewer "name" --note "accepted" --output proofs/world/decision.json
python scripts/quality_lifecycle.py verify \
  proofs/world/scaffold.json proofs/world/decision.json
```

Never reuse approval across another surface or target.

## 6. Readiness seal before final render

After style and composition proof pass, seal the current project, storyboard, registered assets,
pure narration, measured timing, subtitles, composition, proofs, approvals, and runtime build:

```bash
python scripts/readiness_seal.py seal <project> \
  --subtitles <project>/build/subtitles.json \
  --composition <project>/build/composition.json \
  --note "human readiness approval"
python scripts/readiness_seal.py verify <project>
```

New productions reject final rendering when the seal is missing or stale.

## 7. Encoded subtitle proof

Rendering preserves a subtitle-free visual master. Compare every encoded cue against it:

```bash
python scripts/subtitle_delivery.py <project>/final.mp4 \
  <project>/render-cache/subtitle-free-master.mp4 \
  <project>/build/subtitles.json \
  --output-dir <project>/qa/subtitle-delivery
```

This independently proves expected subtitle pixels survived final encoding.

## 8. Scene previews and metrics

```bash
python scripts/scene_preview.py composition.json \
  --start-s 4.2 --end-s 7.8 --scale 0.5 --output previews/scene-02.mp4
python scripts/production_metrics.py record <project> \
  --category provider --operation registered-sheet --duration-s 12.4 \
  --provider-calls 1 --local-derivatives 4 --avoided-calls 3
python scripts/production_metrics.py summary <project>
```

Do not conflate paid calls, local derivatives, avoided calls, and elapsed work.

## 9. Completion boundary

Do not say complete until intake, scenario, budget, storyboard, style, semantic decisions,
registered families, world proof, measured narration, style/composition proof, readiness seal,
final technical QA, encoded-subtitle QA, human creative QA, plugin projection, installed copies,
package, and runtime fingerprints are all current.
