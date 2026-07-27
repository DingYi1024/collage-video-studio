# Delivery cadence and audio QA

Use this reference before rendering and whenever a video looks jerky, freezes at shot tails, or
sounds too quiet, too loud, or breathless.

## Delivery defaults

- Render production projects at a constant 30 fps or higher. New projects default to 30 fps.
- Keep `motion.frame_conversion` at `auto` unless a deliberate test requires another policy.
- Master clean narration before adding music; measure the final mixed file again.
- Declare an intentional static interval. Do not let a short source clip silently become a held
  last frame.

```json
{
  "project": {"fps": 30},
  "motion": {"frame_conversion": "auto"},
  "audio": {
    "delivery_qa": {
      "min_lufs": -22.0,
      "max_lufs": -11.0,
      "max_true_peak_db": -0.5
    }
  }
}
```

## Frame-rate conversion

`auto` and `interpolate` use motion-compensated interpolation when a source clip is below the
delivery frame rate. This avoids repeated-frame cadence, but generated intermediate frames still
require human review around hands, text, thin paper edges, occlusion, and fast direction changes.

`duplicate` only repeats source frames. It is useful for deterministic diagnostics, not normal
delivery. QA blocks a below-target source under this policy.

Source cadence is classified before render:

- unknown or below 12 fps: error;
- 12 to below 23.85 fps under interpolation: warning and mandatory visual review;
- 23.85 fps or higher under interpolation: accepted when the rendered output passes freeze and
  cadence checks;
- any below-target source under `duplicate`: error.

The final video must report the configured average frame rate and matching nominal frame rate.
This is a constant-frame-rate check, not proof that the content actually moved, so freeze
detection runs separately on every pipeline.

## Shot tails and designed holds

Every motion source should cover its shot duration. If a source intentionally ends early, declare
the held interval on the shot:

```json
{
  "duration_s": 4.5,
  "designed_holds": [
    {
      "start_s": 4.1,
      "end_s": 4.5,
      "reason": "hold the completed chart long enough to read"
    }
  ]
}
```

Each interval must stay inside the shot, end after it starts, and include a reason. A declared
hold only excuses a freeze contained by that interval. It does not excuse a freeze earlier in the
shot or a motion source that ends before the declared hold begins.

The same contract is available inside a layered `direction.designed_holds` manifest. Global
freeze detection covers layered, generative, and footage pipelines, including a freeze that
continues to end-of-file.

## Audio envelopes

Pure narration and the final mix have different checks:

- pure narration: default -23 to -13 LUFS and no peak above -0.5 dBTP, plus semantic-pause QA;
- final mixed delivery: default -22 to -11 LUFS and no peak above -0.5 dBTP.

The ranges are safety envelopes rather than mastering targets. Configure a narrower platform
target only when the delivery specification requires it. Do not normalize away clipped syllables,
bad joins, missing pauses, or music masking; those remain human-review failures.

Run:

```bash
python scripts/render.py <project-dir>
python scripts/qa.py <project-dir>
```

Delivery is blocked by a wrong final frame rate, variable nominal/average cadence, undeclared
tail freeze, unexpected whole-frame freeze of 0.12 seconds or longer, out-of-range loudness, or
excessive true peak. Warnings still require review and cannot be silently ignored.
