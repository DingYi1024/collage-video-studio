# Story system

Use this reference to turn a topic or source recording into a compact beat map.

## Contents

- Choosing an arc
- Timing and beat count
- Writing the opening
- Designing shots
- Mode-specific rules
- Story review

## Choosing an arc

Choose one skeleton and adapt it to the subject.

| Arc | Best for | Beat movement |
|---|---|---|
| transformation | before/after stories | old state → friction → change → new state |
| timeline | history and evolution | origin → turning points → present consequence |
| problem-solution | products and campaigns | pain → cost → mechanism → proof → action |
| question-answer | explainers | puzzle → wrong intuition → evidence → answer |
| hidden-system | infrastructure and business | visible event → hidden layers → leverage point |
| countdown | lists and comparisons | promise → ranked discoveries → strongest payoff |
| rise-fall-return | people, brands, movements | ascent → rupture → adaptation or legacy |
| field-guide | travel, culture, practical topics | orientation → rules → examples → takeaway |
| myth-correction | misconceptions | familiar claim → contradiction → explanation → replacement |
| case-study | demonstrations and results | situation → choice → execution → measurable outcome |

Write the selected identifier to `creative.arc`. Combine arcs only when the duration supports
it; a short should feel like one clean movement.

## Timing and beat count

Treat duration as a budget:

- 15 seconds: 3–4 beats, 4–6 shots.
- 30 seconds: 5–7 beats, 8–12 shots.
- 60 seconds: 7–10 beats, 12–18 shots.
- Longer pieces: create chapters, then apply these rules inside each chapter.

Estimate spoken Mandarin at roughly 3.5–4.5 characters per second and English at roughly
2–2.7 words per second. Generate voice early enough to replace estimates with real durations.

Write and generate one continuous narration performance by default. Let visuals follow the
measured voice timeline. Do not force one short sentence into every fixed six-second beat or
accelerate the entire performance to solve one long sentence. Keep ordinary sentence gaps around
0.15–0.30 seconds.

Each beat should contain one idea. If a beat needs “and then,” consider splitting it.

## Writing the opening

The first three seconds must provide at least two of:

- a concrete visual surprise;
- a consequential claim;
- a specific question;
- a visible contrast;
- a promise of what the viewer will understand.

Avoid throat-clearing, greetings, generic scene-setting, and claims that depend on context not
yet shown.

## Designing shots

Use two independent axes:

1. Framing: `establishing`, `wide`, `medium`, `close`, `detail`.
2. Motion: `static`, `push`, `pull`, `pan`, `tilt`, `parallax`, or a specific custom move.

Motion belongs to the story. Use `static` for weight, `push` for discovery, `pull` for context,
`pan` for comparison, `tilt` for scale, and `parallax` for layered material.

Write `element_motion` separately. Name concrete paper elements and one-direction actions:
“receipts slide into a stack; the red arrow unfolds; two labels stamp into place.” Avoid vague
instructions such as “make it dynamic.”

Use one hero motion only on selected emphasis beats. Repeating the same flying object or snap
zoom makes the film feel templated.

## Mode-specific rules

### Topic

Write narration first, then design visuals that add evidence or metaphor rather than merely
illustrating every noun.

### Footage

Segment at completed thoughts, pauses, or gesture changes. Keep segments within the chosen
video-edit model’s duration limit. Preserve `start_s`, `end_s`, and the original audio.
Describe environmental transformation without asking the model to reconstruct the speaker.

### Photo

Use the photo as an identity/product anchor. Put expression and pose changes on an illustrated
body or surrounding elements unless the user permits face transformation. Keep wardrobe,
product proportions, label spelling, and dominant colors explicit in `source.anchor_policy`.

## Story review

Before approval, verify:

- The film can be summarized in one sentence.
- Every beat advances that sentence.
- The hook works without audio.
- Neighboring shots do not repeat the same framing and motion.
- The final beat resolves the opening promise.
- The narration fits the duration budget.
- Claims that need factual support are identified before production.
