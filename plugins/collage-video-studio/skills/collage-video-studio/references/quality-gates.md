# Two-stage visual quality gates

Run asset QA before composition QA. They answer different questions.

## Asset gate

Audit every cutout before it enters a shot. Required-alpha assets must have transparent,
opaque, and partial-alpha pixels, and should not touch the source canvas edge.

```bash
python scripts/asset_quality.py assets.json --mode assets
```

For a chroma-backed asset, measure the actual border colour instead of assuming ideal green:

```bash
python scripts/asset_quality.py keyed.png --mode key \
  --output cleaned.png --tolerance 42 --softness 24
```

This observes the border key plane, creates a soft alpha edge, and despills edge colour.

## Composition gate

After assets pass, validate the compiled scene:

```bash
python scripts/asset_quality.py layers.json --mode composition
```

This checks layer schema, source registration, editable text fit, minimum depth/activity,
follower contracts, and sampled motion continuity. Only after both gates pass should final
technical QA inspect duration, audio, freezes, activity, and delivery encoding.
