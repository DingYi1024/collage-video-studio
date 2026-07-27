# Registered sources and advanced layer primitives

Use these primitives for smooth editorial motion without joint simulation or per-frame
generation.

## Registered source family

Every member of a registered family occupies the complete delivery canvas. Transparent pixels
keep the subject's anchor stable across background, subject, foreground, and pose states.

Declare the members in `layers.json`:

```json
{
  "registration": {
    "members": ["background", "subject", "foreground"]
  }
}
```

The validator opens every declared PNG and rejects a size that differs from the canvas.

When a provider returns one transparent source board, crop it once into full-canvas registered
members:

```bash
python scripts/registered_sources.py board.png source-spec.json output/
```

`source-spec.json`:

```json
{
  "canvas": [1080, 1920],
  "items": [
    {
      "id": "subject-rest",
      "role": "subject",
      "source_rect": [20, 20, 480, 900],
      "place": [280, 700],
      "z": 4
    }
  ]
}
```

The command emits transparent PNGs and `registration.json` with source and member SHA-256
evidence.

## Pose sequence

Use `pose_sequence` for discrete authored states. This is the preferred whole-subject state
mechanism; legacy `sprites` remains supported for old projects and small local cycles.

```json
{
  "id": "subject",
  "path": "subject-rest.png",
  "pose_sequence": {
    "states": [
      {"id": "rest", "path": "subject-rest.png", "at_s": 0},
      {"id": "point", "path": "subject-point.png", "at_s": 1.2}
    ],
    "playback": "once",
    "transition": "cut",
    "crossfade_s": 0
  }
}
```

Playback can be `once`, `loop`, or `ping-pong`. Use `cut` for different silhouettes. A short
`crossfade` is allowed only for nearly identical registered local states.

## Persistent visibility

Visibility is state, not a one-frame command:

```json
{
  "visibility": {
    "initial": false,
    "events": [
      {"at_s": 0.2, "visible": true, "fade_s": 0.16},
      {"at_s": 3.7, "visible": false, "fade_s": 0.12}
    ]
  }
}
```

Once shown, the layer stays shown until another event. This prevents the common flash where an
object exists for one keyframe and disappears on the next.

## Looping strip

Use a repeating strip for a road, skyline, clouds, ticker, or texture band:

```json
{
  "looping_strip": {
    "axis": "x",
    "speed_px_s": -90,
    "spacing_px": 0,
    "phase_px": 20,
    "start_s": 0,
    "end_s": 4
  }
}
```

The compositor wraps copies on the delivery canvas. The source edge must be authored to tile
cleanly.

## Seeded motif field

Use one source motif for dust, stars, numbers, notes, labels, confetti, or paper fibers:

```json
{
  "motif_field": {
    "seed": 2026,
    "count": 18,
    "area": [80, 120, 920, 1480],
    "scale_range": [0.6, 1.1],
    "drift_px": [6, 14],
    "spin_deg": 5,
    "stagger_s": 0.04
  }
}
```

Each instance gets a repeatable location, size, phase, drift, and rotation. The same seed renders
the same scene on every machine.

## Selection rule

- Continuous travel: ordinary keyframes with `catmull-rom`.
- Discrete state: `pose_sequence`.
- Entrance or exit: `visibility`.
- Infinite environmental travel: `looping_strip`.
- Repeated atmosphere or editorial accents: `motif_field`.
- Story-critical close joint: optional articulated rig.

Do not use a rig when a stable whole-body cutout plus continuous keyframes communicates the same
idea more smoothly.

