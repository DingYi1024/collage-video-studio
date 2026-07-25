# Layered motion

Use this route when the user expects independently moving paper objects, controlled parallax,
or reusable editable animation rather than generative motion from one flattened image.

## Select the pipeline

Add this top-level object to `project.json`:

```json
{
  "motion": {
    "pipeline": "layered",
    "min_layers": 6,
    "min_animated_layers": 4,
    "transitions": {
      "duration_s": 0.32,
      "types": ["wipeleft", "dissolve", "slideup"]
    }
  }
}
```

The production order becomes:

```text
styles → images → layers → motion → voice → music → render → QA
```

`images` remains the approved composition. `layers` turns it into an editable package.
`motion` renders that package. Do not claim multi-layer motion when the pipeline is
`generative`; an image-to-video model may create local movement, but it does not provide
explicit layer ownership or deterministic transforms.

## Layer package

Each `layers:<beat>-<shot>` artifact points to a `layers.json` file beside full-canvas RGBA PNGs:

```text
media/layers/b01-s01/
├── layers.json
├── background.png
├── middle-ground.png
├── foreground.png
├── tree-canopy.png
└── heat-waves.png
```

Minimal manifest:

```json
{
  "version": 1,
  "canvas": {
    "width": 720,
    "height": 1280,
    "fps": 30,
    "duration_s": 4,
    "oversample": 2,
    "motion_blur_samples": 1,
    "shutter": 0.5
  },
  "quality": {"min_layers": 6, "min_animated_layers": 4},
  "layers": [
    {
      "id": "heat-waves",
      "path": "heat-waves.png",
      "z": 6,
      "role": "object",
      "easing": "catmull-rom",
      "loop": true,
      "phase_s": 0.18,
      "keyframes": [
        {"t": 0, "y": 100, "opacity": 0, "scale_y": 0.8},
        {"t": 0.5, "y": 35, "opacity": 0.9, "scale_y": 0.95},
        {"t": 1.2, "y": -55, "opacity": 0.7, "scale_y": 1.1},
        {"t": 1.8, "y": -135, "opacity": 0, "scale_y": 1.2}
      ]
    }
  ]
}
```

Supported keyframe properties:

- `x`, `y`;
- `scale`, `scale_x`, `scale_y`;
- `rotation`;
- `opacity`.

All transform values interpolate between keyframes. Use full-canvas transparent layers so
registration remains stable.

Supported easing values are `linear`, `smoothstep`, `smootherstep`, `ease-in`, `ease-out`,
`ease-in-out`, and `catmull-rom`. Prefer `catmull-rom` for three or more continuous motion
keyframes because it preserves velocity through interior points. Use `smoothstep` for a deliberate
start or stop, not for every layer on the same timestamps.

Set `loop: true` for persistent micro-motion. `phase_s` offsets the loop so nearby objects do not
start, reverse, or disappear together. Make the first and last transforms equal for visible loops;
an entrance-to-exit loop may reset at different transforms only when both endpoints are fully
transparent.

`oversample: 2` renders transforms on a 2× canvas and downsamples once per output frame, reducing
one-pixel stepping on slow movement. `motion_blur_samples` accepts 1–4 temporal samples, while
`shutter` controls the fraction of one frame they cover. Increase these only after a representative
shot meets the available render-time budget.

## Motion quality rules

- Deliver at 30 fps or higher unless the intended style is explicitly stop-motion.
- Give the camera one continuous action while foreground, middle, and background layers move at
  different speeds.
- Stagger loop phases and entrance times; never give most moving layers the same interior
  `smoothstep` keyframe.
- Keep at least one small motion alive between large actions: paper grain drift, foliage sway,
  heat rise, blinking light, water ripple, or floating debris.
- Use a 0.2–0.5 second transition between shots. Supported render transitions include fades,
  directional wipes/slides, smooth wipes, circles, and dissolve.
- Inspect the delivered MP4. A low-frame-rate GIF is a publishing preview, not evidence of final
  motion quality.

## Execute and validate

Generate and run the layer stage through an adapter that supports `layer_package`:

```bash
python scripts/studio.py jobs <project-dir> --stage layers
python scripts/job_runner.py <project-dir> --stage layers --adapter <adapter.py>
```

The subsequent motion jobs use `layers_to_video` and a `layer_manifest` input. A local adapter
may call:

```bash
python scripts/layer_compositor.py \
  <project-dir>/media/layers/b01-s01/layers.json \
  --output <project-dir>/media/motion/b01-s01.mp4
```

Validate a package without rendering:

```bash
python scripts/layer_compositor.py <path-to-layers.json> --validate
```

Technical QA rejects layered projects whose packages are missing, have too few layers, or have
too few independently animated layers.

The bundled Replicate adapter covers generative image/video/audio routes. It does not fabricate
editable transparent layer packs. Use a layer-aware adapter, prepared design assets, segmentation
workflow, or deterministic asset generator for the `layers` stage.
