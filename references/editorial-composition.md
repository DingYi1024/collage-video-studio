# Editorial composition protocol

Use this protocol when a shot must remain editable, responsive, and provably multi-layered.

## Author once, direct per frame

Author a recursive `composition` tree. A node is a `group`, `image`, or `primitive`. Groups carry
shared transforms; children follow them without precompositing. Give depth only where camera
movement should create relative parallax.

Supported editable primitives are text, rectangle, ellipse, line, bar chart, timeline,
annotation, map route, and data-driven SVG. SVG accepts structured paths (including quadratic and
cubic curves), circles, and text; it stays deterministic in both Pillow/FFmpeg and Remotion.
Text must declare a box, preferred size, and minimum size. Validation fails if the text cannot
fit at the minimum.

Annotations declare a target, label box size, preferred side, padding, and optional exclusion
rectangles. The director resolves every annotation against safe-zone exclusions and previously
placed annotations. No collision-free position is a hard failure.

Put layout differences in `director_plans`, not duplicated compositions. Each `16:9`, `9:16`, or
`1:1` plan can override node geometry and must declare title/data/subject safe zones. Compile:

```bash
python scripts/editorial_contract.py composition.json \
  --kind composition --output result/manifests
```

Validate each compiled manifest before rendering:

```bash
python scripts/asset_quality.py result/manifests/composition-9x16.json \
  --mode composition
python scripts/layer_compositor.py result/manifests/composition-9x16.json \
  --output result/portrait.mp4
```

Open the same manifest in the visual workspace:

```bash
cd workspace
npm ci
npm run dev
```

The React inspector edits the recursive JSON, the Remotion Player previews exact delivery frames,
and edit-point controls seek the unified timeline. `npm run render` is the independent Remotion
CLI execution proof.

## Motion rules

- Prefer continuous keyframes and easing over pose swaps.
- Couple camera travel to authored `depth`; do not fake depth with a whole-frame zoom.
- Let a parent group carry common drift. Add child motion only for a meaningful relative action.
- Use one readable primary action per beat; secondary motion should be slower and smaller.
- Keep final holds intentional. A shot is not complete merely because every layer moved.

The three-aspect executable example is in `examples/editorial-proof-demo`.
