# Directed paper motion

Use this contract when a layered piece must feel performed and physically authored, rather than
like every layer received a generic loop.

## Start with the action sentence

Before splitting a shot into layers, write:

```json
{
  "direction": {
    "primary_action": "the proceeds envelope slides in and three coins land",
    "physical_cause": "the acquisition converts equity into cash",
    "motion_density": "medium"
  }
}
```

The action must name a subject and a verb. The cause explains why it moves. Reject descriptions
such as “subtle dynamic motion,” “make it lively,” or “everything has gentle parallax.”

Use `low` density for evidence, close-ups, and reading shots; `medium` for most narrative scenes;
reserve `high` for a brief climax. Density controls how many layers move, not how fast they move.

## Direct one action through three phases

Every directed `layers.json` contains:

```json
{
  "quality": {"directed_motion": true},
  "direction": {
    "primary_action": "one capital stack divides toward three projects",
    "physical_cause": "sale proceeds are reinvested",
    "primary_layers": ["capital-car", "capital-rocket", "capital-solar"],
    "motion_density": "medium",
    "phases": [
      {"name": "anticipation", "start_s": 0, "end_s": 0.55},
      {"name": "action", "start_s": 0.55, "end_s": 3.2},
      {"name": "settle", "start_s": 3.2, "end_s": 4}
    ],
    "designed_holds": [
      {
        "start_s": 3.6,
        "end_s": 4,
        "reason": "hold the evidence long enough to read"
      }
    ]
  }
}
```

The phases must be contiguous and cover the shot:

- **Anticipation**: a short compression, pullback, lift, pause, or visual setup that tells the eye
  where the action will happen.
- **Action**: one readable change with sufficient travel, rotation, replacement, or assembly to
  be visible at delivery speed.
- **Settle**: a small overshoot and correction, or a clean deceleration into contact.

A declared hold is intentional staging, not a failure. It must have a reason and occur after the
information has arrived. Undeclared whole-frame freezes remain QA errors.

## Use segment timing, not one easing for a whole layer

A keyframe may set the easing for the segment that arrives at that keyframe:

```json
{
  "keyframes": [
    {"t": 0, "x": -180},
    {"t": 0.55, "x": -205, "ease": "back-in"},
    {"t": 1.7, "x": 0, "ease": "back-out"},
    {"t": 2.05, "x": 0},
    {"t": 4, "x": 0}
  ]
}
```

Supported segment values are `hold`, `linear`, `smoothstep`, `smootherstep`, `ease-in`,
`ease-out`, `ease-in-out`, `back-in`, `back-out`, `back-in-out`, and `catmull-rom`.

Use:

- `back-in` for a restrained preparatory pull;
- `ease-in` for acceleration caused by gravity, thrust, or a decisive push;
- `ease-out` for friction and arrival;
- `back-out` for a paper tab, block, envelope, or stamp that slightly overshoots and seats;
- `hold` only for a deliberate stepped reveal or stop-motion state.

Do not put every layer on the same timestamps or easing.

## Respect paper physics

Before animating an object, name its contact:

- card or envelope: table surface and leading edge;
- coin or block: base plane and landing face;
- car: wheel contact line;
- person: planted foot;
- hinged part: authored pin or fold;
- rocket: pad, thrust axis, and clear lift-off direction.

Rigid paper translates and rotates. It does not breathe, liquefy, stretch, or continuously scale.
Use separate parts for a real joint. Use opacity only for an authored reveal or occlusion, not to
hide pose changes.

## Stage motion hierarchically

Use this priority:

1. primary action;
2. camera, only if it clarifies the action;
3. one secondary response;
4. atmosphere, only if the shot still needs it.

Moving everything is not richness. For `low` density, keep at least 55% of layers still. For
`medium`, keep at least 30% still. A stable face, horizon, table, or architectural plane gives the
moving subject weight.

Avoid more than two identical cycles in a normal four-second shot. Prefer an entrance, a change,
and a hold over a permanent bob or flap.

## Vary the sequence, not only the transforms

A six-shot portfolio case should normally include at least:

- one wide shot;
- one medium evidence shot;
- one close/detail shot;
- one static-camera shot;
- one restrained camera move;
- one shot without a recurring character.

Do not repeat the same composition, background crop, character scale, and motion direction in
adjacent shots. A contact sheet should reveal the story even before playback.

## Review at delivery speed

For each shot, inspect:

- the frame before anticipation;
- maximum action range;
- first contact or landing;
- overshoot;
- final settled frame.

Then watch the 30 fps MP4 at normal speed. Check that the action is visible without audio, the
subject never loses contact accidentally, and the hold feels intentional rather than stalled.
The number of animated layers is only a minimum safety check; it is not a quality score.
