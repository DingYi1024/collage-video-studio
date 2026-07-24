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
    "min_animated_layers": 4
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
  "canvas": {"width": 720, "height": 1280, "fps": 24, "duration_s": 4},
  "quality": {"min_layers": 6, "min_animated_layers": 4},
  "layers": [
    {
      "id": "heat-waves",
      "path": "heat-waves.png",
      "z": 6,
      "role": "object",
      "easing": "smoothstep",
      "keyframes": [
        {"t": 0, "y": 90, "opacity": 0.2, "scale_y": 0.8},
        {"t": 4, "y": -130, "opacity": 0.4, "scale_y": 1.2}
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
