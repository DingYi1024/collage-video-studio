# Smooth keyframe motion

Use this as the default motion strategy when fluid playback matters more than anatomically
accurate articulation.

## Priority

Judge motion in this order:

1. no flash, teleport, freeze, or cadence break;
2. one readable subject action;
3. clean easing and stable registration;
4. physical detail only when it improves the shot.

Do not add a joint rig merely because the subject is a person. A whole-body paper cutout moving
on a well-authored path is preferable to a technically correct rig that feels mechanical.

## Default character treatment

- Keep one stable character silhouette inside a shot.
- Use one whole-body layer, or at most a root plus one or two independently useful parts.
- Move the character root with translation, slight rotation, and restrained scale.
- Add a small vertical arc only when it supports the action.
- Change a major pose at a cut or behind an occluder. Never swap or crossfade unrelated
  silhouettes during visible travel.
- Use an articulated rig only for a close, story-critical action such as pointing, opening,
  flapping, or manipulating an object.

Stylized sliding is valid editorial paper motion. It does not need alternating feet when the shot
does not claim to show realistic walking. Keep the ground plane stable and avoid fake foot cycles.

## Author continuous motion

For a layer that travels through three or more points, set:

```json
{
  "motion_intent": "continuous",
  "easing": "catmull-rom",
  "keyframes": [
    {"t": 0.35, "x": -180, "y": 18},
    {"t": 1.25, "x": -40, "y": 0},
    {"t": 2.25, "x": 120, "y": -8},
    {"t": 3.15, "x": 210, "y": 0}
  ]
}
```

`smoothstep`, `smootherstep`, and `ease-in-out` deliberately reduce velocity to zero at both ends
of a segment. They are good for one entrance or one final settle, but produce visible stop-start
motion when repeated at every interior keyframe. Use `catmull-rom` across interior travel points,
or matched `linear` segments when constant speed is intentional.

Use per-keyframe easing only at the outside edges of the action:

- entrance: `ease-out`;
- continuous middle: `catmull-rom`;
- final settle: `ease-in-out` or `smootherstep`;
- reading hold: explicit `designed_holds`, never accidental duplicate motion keys.

Do not align most moving layers to the same interior timestamps. Offset secondary arrivals by
0.08–0.25 seconds.

## Delivery defaults

- Render constant 30 fps; use 60 fps only when the target and render budget justify it.
- Sample continuity at the delivery fps.
- Use 2× spatial oversampling for slow diagonal movement, rotation, or small textural edges.
- Use two temporal motion-blur samples for fast travel only after the timing curve is correct.
- Review the MP4 at normal speed and again frame-by-frame. Do not judge smoothness from a GIF,
  browser thumbnail, or an overloaded preview player.

## Audit

Enable the smooth-keyframe guard:

```json
{
  "quality": {
    "motion_audit": {
      "sample_fps": 30,
      "enforce_smooth_keyframes": true,
      "max_interior_stalls": 0
    }
  }
}
```

Run:

```bash
python scripts/layer_compositor.py media/layers/b01-s01/layers.json --audit
```

The audit rejects a `motion_intent: "continuous"` layer when a monotonic interior travel point
uses a stop-start curve. Fix the curve; do not raise `max_interior_stalls`.
