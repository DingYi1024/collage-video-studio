# Motion continuity audit

Use this audit after layer validation and before creative review. It samples the resolved transform
graph at frame cadence, including follower relationships.

## Enable it

```json
{
  "quality": {
    "motion_audit": {
      "sample_fps": 30,
      "max_speed_px_s": 2300,
      "max_rotation_deg_s": 900,
      "max_scale_per_s": 3,
      "max_opacity_per_s": 8
    }
  }
}
```

Run:

```bash
python scripts/layer_compositor.py media/layers/b01-s01/layers.json --audit
```

Keep limits strict enough to reject a one-frame jump. Raise a limit only when the physical action
requires it and the rendered frames prove continuity.

## Attach a secondary response

Use `follow` for a layer that must inherit part of another layer's transform:

```json
{
  "id": "front-wheel",
  "pivot": [219, 446],
  "motion_class": "hinged-part",
  "follow": {
    "parent": "car-body",
    "lag_s": 0,
    "inherit": {"x": 1, "y": 1}
  },
  "keyframes": [
    {"t": 0, "rotation": 0},
    {"t": 1.5, "rotation": 540, "ease": "linear"}
  ]
}
```

Inheritance weights range from 0 to 1. Translation and rotation are additive. Scale and opacity
are multiplicative around their neutral value. Keep `lag_s` small and motivated; do not use it to
manufacture ambient wobble.

Declare why the response exists:

```json
{
  "direction": {
    "secondary_responses": [
      {
        "layers": ["front-wheel", "rear-wheel"],
        "driven_by": "car-body",
        "reason": "wheels rotate only while the car translates"
      }
    ]
  }
}
```

## Lock contact

Declare a property that must stop drifting after an object lands:

```json
{
  "direction": {
    "contacts": [
      {
        "layer": "coin",
        "property": "y",
        "start_s": 2.6,
        "end_s": 4.0,
        "tolerance": 0.5
      }
    ]
  }
}
```

Use contact locks for planted feet, wheels on a road, objects resting on a table, stamps, and
settled evidence cards. The audit compares the resolved property throughout the declared range.

## Interpret results

- `speed_px_s`: translation, including inherited root motion.
- `rotation_deg_s`: angular change; fast wheels may be higher than body parts.
- `scale_per_s`: squash, stretch, or fold-rate discontinuity.
- `opacity_per_s`: flashes and one-frame appearances.
- `contact drift`: motion after a declared landing or planted interval.

A clean audit proves transform continuity, not creative quality. Still inspect the final MP4 at
delivery frame rate and review contact, weight, occlusion, and readable holds.
