# Production closure

Use these gates when a project must be editable, repeatable, and evidence-backed rather than
merely exportable.

## Visual workspace

The `workspace/` directory is a real React application using Remotion Player and the same
recursive manifest consumed by the CLI renderer.

```bash
cd workspace
npm ci
npm run dev
npm run build
npm run render
```

Open a composition JSON, switch among 16:9, 9:16, and 1:1 director plans, inspect layers, edit
primitive geometry/text/depth, jump to unified edit points, and save the updated JSON. The player
must preview the directed recursive layers; do not substitute a flattened proxy.

## Exact timing

`voice_director.py` defaults to narration-led timing. It retains measured phrase pauses, masters
the actual performance without padding it to an obsolete scene duration, registers its timing
manifest, then invokes `timing_compiler.py --apply`.

The compiler maps measured speech and pauses to beats, adds only the declared
`audio.voice.visual_tail_s`, converts every beat and shot to integer delivery frames, preserves
relative shot weights, writes `build/timing-proof.json`, and clears invalidated approvals.
Use `--fixed-timeline` only for a legacy project whose locked picture duration is authoritative.

## Semantic execution

Declare `automated_checks` under each semantic contract and run:

```bash
python scripts/semantic_qa.py project.json composition.json --output semantic-proof.json
```

Supported checks are `identity-similarity` for reference preservation (not biometric
recognition), `relative-position` for topology, `edit-order` for mechanism sequence, and
`data-values`/`text-exact` for infographics. Contracts without checks remain incomplete.

## Registered depth

Build every source family on one registered full canvas, then compile:

```bash
python scripts/depth_stack.py registration.json depth-stack.json composition.json
```

Each item references a registered source id, declares depth from -1 to 1, retains its content
hash, and receives a deterministic camera-response multiplier.

## Proof types

```bash
python scripts/proof_system.py <project> --register style --approve <theme-id>
python scripts/proof_system.py <project> --register composition <manifest>
python scripts/proof_system.py <project> --register moment \
  final.mp4 reports/editorial-plan.json --review proof-decisions.json
```

Style proof requires exactly three previews of the same representative beat. Composition proof
combines layer/motion validation, semantic QA, annotation layout, and unified edit points.
Moment proof deliberately stays `pending-human-review` until every moment has an affirmative
review decision. Check freshness with `proof_system.py <project> current <kind>`.

## Chroma and alpha

Observed-key cleanup samples the actual border. Removed pixels must store transparent black, not
invisible saturated RGB. The alpha audit independently blocks transparent RGB residue and
dominant-key color on partial-alpha edges.
