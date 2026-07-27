# Planted-foot locomotion

Use locomotion only when the subject has two authored leg chains and the root must travel. A
single character PNG sliding across the frame is not a walk cycle.

## Rig contract

Declare locomotion inside an `articulated-paper` rig:

```json
{
  "rigs": [
    {
      "id": "full-body-walker",
      "type": "articulated-paper",
      "root": "walker-root",
      "parts": [
        "walker-root",
        "left-thigh", "left-shin", "left-foot",
        "right-thigh", "right-shin", "right-foot"
      ],
      "locomotion": {
        "root_axis": "x",
        "feet": ["left-foot", "right-foot"],
        "min_stride_px": 220,
        "min_contact_s": 0.7,
        "max_double_support_s": 0.08,
        "max_plant_drift_px": 2
      }
    }
  ]
}
```

The validator requires:

- two distinct foot layers owned by the rig;
- at least one leg segment between each foot and the root;
- `hinged-part` feet with a connected rig-space parent chain;
- measurable root travel on the declared axis;
- alternating paired x/y plant locks for both feet;
- bounded plant drift and double-support overlap.

## Plant contacts

Lock both translation properties for every planted interval:

```json
{
  "direction": {
    "contacts": [
      {"layer": "left-foot", "property": "x", "start_s": 0, "end_s": 0.8, "tolerance": 1.5},
      {"layer": "left-foot", "property": "y", "start_s": 0, "end_s": 0.8, "tolerance": 1.5},
      {"layer": "right-foot", "property": "x", "start_s": 0.8, "end_s": 1.6, "tolerance": 1.5},
      {"layer": "right-foot", "property": "y", "start_s": 0.8, "end_s": 1.6, "tolerance": 1.5}
    ]
  }
}
```

Plant locks must alternate by foot. Short double support is allowed, but a long overlap makes the
root appear to drag both feet. A gap is allowed while both feet pass through a jump or brief
airborne action, but ordinary walking should always make weight transfer readable.

## Authoring method

For each delivery-rate frame:

1. Advance the hip/root on a velocity-continuous path.
2. Hold the planted ankle target in world space.
3. Move the swing ankle forward on a lifted arc.
4. Solve the thigh and shin angles from hip to ankle.
5. Counter-rotate the foot so its paper sole stays level near contact.
6. Swing arms opposite the legs and keep the torso motion restrained.

Use two-link inverse kinematics when possible. Dense delivery-rate keyframes are acceptable for
an authored walk cycle because they preserve foot targets exactly and remain editable.

## Audit and review

Run:

```bash
python scripts/layer_compositor.py media/layers/b01-s01/layers.json --audit
```

The audit reports `locomotion_rigs` and paired `plant_intervals`. It also samples the resolved
hierarchy at delivery cadence, so root travel, joint motion, and contact locks are measured after
inheritance.

Watch the final MP4 at normal speed and verify:

- the planted sole does not slide or hover;
- the knee bends consistently rather than flipping sides;
- hip speed does not jump at step boundaries;
- the swing foot clears the ground;
- arms oppose the legs without identical mechanical timing;
- the torso does not bob enough to look weightless;
- the subject enters and exits with enough framing room.

The deterministic reference implementation is
`examples/walk-cycle-demo/build_demo.py`.
