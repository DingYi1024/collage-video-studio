# Articulated paper rigs

Use an articulated rig when a person, animal, vehicle attachment, or mechanical object needs
connected joint motion. A pose swap or a stack of independently animated PNGs is not a rig.

## Asset contract

- Export every rigid part as a full-canvas RGBA PNG at the final layer-package canvas size.
- Put the root pivot at the planted contact or body anchor.
- Put each child pivot exactly at the joint shared with its parent.
- Draw a small overlap or paper fastener around joints so antialiasing never opens a visible gap.
- Keep the root stable unless the shot has an authored locomotion cycle.
- Use one chain per connected limb; do not crossfade whole-body alternatives inside the shot.

For a standing character that points, a practical split is:

```text
torso/root at planted feet
└── upper arm at shoulder
    └── forearm at elbow
```

The torso may include the head and planted legs when they do not need independent articulation.
This produces readable subject motion without inventing a walk cycle.

## Manifest contract

Declare the connected component:

```json
{
  "rigs": [
    {
      "id": "founder-arm-rig",
      "type": "articulated-paper",
      "root": "founder-torso",
      "parts": ["founder-torso", "founder-upper-arm", "founder-forearm"]
    }
  ]
}
```

Every non-root part must rig-follow another part and resolve back to the declared root. The
validator rejects missing roots, disconnected parts, and cycles.

A child joint uses `follow.space: "rig"`:

```json
{
  "id": "founder-forearm",
  "path": "founder-forearm.png",
  "motion_class": "hinged-part",
  "pivot": [475, 345],
  "follow": {
    "parent": "founder-upper-arm",
    "space": "rig",
    "lag_s": 0,
    "inherit": {"x": 1, "y": 1, "rotation": 1}
  },
  "keyframes": [
    {"t": 0, "rotation": 8},
    {"t": 0.55, "rotation": -12, "ease": "back-in"},
    {"t": 2.3, "rotation": 20, "ease": "back-out"},
    {"t": 3.2, "rotation": 14, "ease": "ease-out"},
    {"t": 4, "rotation": 14}
  ]
}
```

Rig space carries the child pivot around the resolved parent pivot after parent translation,
rotation, and scale. Joint translation inheritance must be complete (`x: 1`, `y: 1`) and
`lag_s` must be zero; delayed joints visually detach.

Use ordinary world-space `follow` for wheels, flame, loose clothing, and other responses that
only need additive transform inheritance. Use rig space only for physically connected parts.

## Timing and contact

- Use anticipation, action, and settle keyframes on the limb rather than constant oscillation.
- Rotate the upper arm first and let the forearm clarify the gesture; avoid identical angles and
  timestamps on every joint.
- Lock the planted root in both `x` and `y` for the full planted interval.
- Keep joint rotation within the believable paper construction range.
- If the root travels, provide an authored planted-foot cycle. Otherwise the character slides.

Example root contacts:

```json
{
  "direction": {
    "contacts": [
      {"layer": "founder-torso", "property": "x", "start_s": 0, "end_s": 4, "tolerance": 0},
      {"layer": "founder-torso", "property": "y", "start_s": 0, "end_s": 4, "tolerance": 0}
    ]
  }
}
```

## Review

Run the frame-cadence audit before rendering:

```bash
python scripts/layer_compositor.py media/layers/b04-s01/layers.json --audit
```

Then inspect at least five consecutive delivery-rate frames covering anticipation, peak action,
overshoot, and settle. Check that:

- shoulder and elbow remain connected;
- the planted root does not drift;
- no limb flashes or appears twice;
- rigid paper parts rotate instead of bending;
- occlusion order stays credible;
- the gesture reads with audio muted.

The audit proves transform continuity and rig connectivity. It does not prove that the pose,
joint placement, or acting choice looks natural.
