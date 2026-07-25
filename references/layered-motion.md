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
    "min_animated_layers": 3,
    "directed_motion": true,
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
  "quality": {
    "min_layers": 6,
    "min_animated_layers": 3,
    "directed_motion": true
  },
  "direction": {
    "primary_action": "heat strips rise and settle behind the evidence card",
    "physical_cause": "stored heat leaves the road surface",
    "primary_layers": ["heat-waves"],
    "motion_density": "low",
    "phases": [
      {"name": "anticipation", "start_s": 0, "end_s": 0.5},
      {"name": "action", "start_s": 0.5, "end_s": 3.2},
      {"name": "settle", "start_s": 3.2, "end_s": 4}
    ]
  },
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

## Authored states and major poses

Use `sprites` for small, closely registered states such as blinks, mouth shapes, page states, or a
true frame-by-frame cycle. Keep every sprite on the same full canvas and give the layer a stable
canvas-space `pivot`:

```json
{
  "id": "paper-eye",
  "path": "eye-open.png",
  "pivot": [420, 360],
  "sprites": [
    {"t": 0, "path": "eye-open.png"},
    {"t": 0.12, "path": "eye-half.png"},
    {"t": 0.18, "path": "eye-closed.png"}
  ],
  "sprite_loop": true,
  "sprite_duration_s": 3.6,
  "sprite_phase_s": 0.04,
  "sprite_transition": "cut",
  "sprite_crossfade_s": 0,
  "keyframes": [
    {"t": 0, "scale": 1},
    {"t": 4, "scale": 1}
  ]
}
```

Set `motion_class: major-pose` for whole-body alternatives. The validator rejects crossfades on
that class because blended silhouettes create double faces, extra limbs, and flashes. Change a
major pose at a shot cut or while an authored foreground layer fully occludes the subject.

Use a zero crossfade for hand-cut stop motion. A short crossfade is reserved for nearly identical
registered local states, never unrelated poses.
For generated chroma-key model sheets, remove the key first and split the RGBA sheet with
`scripts/sprite_sheet.py`; it trims each cell while keeping transparent padding for clean
rotation and scaling.

## Rigid paper rigs

Articulated subjects must use separately owned rigid layers. For a butterfly:

```json
{
  "rigs": [{
    "id": "butterfly",
    "type": "hinged-paper",
    "parts": ["left-wing", "right-wing", "body"],
    "pivot": [720, 210]
  }],
  "layers": [
    {
      "id": "left-wing",
      "motion_class": "hinged-part",
      "pivot": [720, 210],
      "keyframes": [
        {"t": 0, "rotation": -10},
        {"t": 0.45, "rotation": 42},
        {"t": 0.9, "rotation": -10}
      ]
    },
    {
      "id": "right-wing",
      "motion_class": "hinged-part",
      "pivot": [720, 210],
      "keyframes": [
        {"t": 0, "rotation": 10},
        {"t": 0.45, "rotation": -42},
        {"t": 0.9, "rotation": 10}
      ]
    }
  ]
}
```

The body, both wings, and their shadows must share the same root translation. The wings may rotate
only around the wing roots. Keep travel short and couple body bob to the wing phase. For a person,
use one stable pose per shot unless an authored limb rig or planted-foot walk cycle exists.

## Curved motion paths and pivots

Add a cubic Bézier offset path for flying, falling, floating, or thrown paper objects. The example
below is intentionally short; long paths need an authored locomotion cycle:

```json
{
  "motion_path": {
    "start_s": 0,
    "end_s": 4,
    "points": [[-18, 6], [-5, -12], [8, -10], [20, -2]],
    "easing": "ease-in-out",
    "orient_to_path": true,
    "rotation_offset": 0
  }
}
```

Path points are offsets from the layer's authored position. Set `loop`, `phase_s`, and matching
endpoints only for a genuinely seamless route.

`pivot: [canvas_x, canvas_y]` rotates and scales around a stable point in the full source canvas.
Use it for feet, hinges, stems, necks, and shared pose registration. `anchor: [x_ratio, y_ratio]`
is a crop-relative fallback; prefer `pivot` when a layer has multiple sprite files.

For dependent motion, add `follow.parent`, optional `lag_s`, and an `inherit` weight map. Use this
for wheels following a vehicle, a flame following a rocket, or a restrained clothing response.
Read [motion-audit.md](motion-audit.md) for the contract, limits, and contact locks.

Optional `motion_class` values are `camera`, `atmosphere`, `rigid-body`, `hinged-part`,
`major-pose`, and `effect`. A `hinged-part` requires `pivot`. A `rigid-body` should not change
`scale_x` or `scale_y` by more than 8 percent.

Supported easing values are `linear`, `smoothstep`, `smootherstep`, `ease-in`, `ease-out`,
`ease-in-out`, `back-in`, `back-out`, `back-in-out`, `hold`, and `catmull-rom`. A keyframe can
set `ease` for the segment that arrives there. Prefer `catmull-rom` for three or more continuous motion
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
- Write one primary action and its physical cause before authoring transforms.
- Divide the shot into anticipation, action, and settle. Declare intentional reading holds.
- Keep stable reference planes. Moving every layer creates weightless toy motion.
- Give the camera one continuous action only when it clarifies the subject action; a locked camera
  is valid.
- Stagger entrance times; never give most moving layers the same interior keyframe.
- Avoid endless ambient loops. Prefer one entrance, one change, and a settled result.
- Use a 0.2–0.5 second transition between shots. Supported render transitions include fades,
  directional wipes/slides, smooth wipes, circles, and dissolve.
- Inspect the delivered MP4. A low-frame-rate GIF is a publishing preview, not evidence of final
  motion quality.
- Inspect wing roots, feet, hands, and face contours frame-by-frame. Those contact points reveal
  sliding and pose flashes before a contact sheet does.

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

Technical QA rejects layered projects whose packages are missing, have too few layers, have too
few independently animated layers, or violate a requested directed-motion contract. It also warns
when animation density is excessive or most motion is sub-visible jitter. Read
[directed-motion.md](directed-motion.md) for the full directing contract.

The bundled Replicate adapter covers generative image/video/audio routes. It does not fabricate
editable transparent layer packs. Use a layer-aware adapter, prepared design assets, segmentation
workflow, or deterministic asset generator for the `layers` stage.
