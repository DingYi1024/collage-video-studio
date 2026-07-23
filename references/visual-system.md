# Visual system

Use this reference to create visual directions and generation prompts without locking every
project to one house style.

## Contents

- Theme anatomy
- Style comparison
- Image prompt grammar
- Motion prompt grammar
- Anchor protection
- Quality review

## Theme anatomy

Define a theme with six independent fields:

```json
{
  "id": "short-stable-id",
  "medium": "what the image appears physically made from",
  "palette": "named colors and contrast behavior",
  "typography": "display-lettering character and placement",
  "texture": "print, paper, edge, and surface behavior",
  "composition": "layout logic and focal hierarchy",
  "motion": "tempo, amplitude, and transition character"
}
```

Good fields are observable. “Premium” is not observable; “cream stock, black ink, narrow
serif labels, large empty margins, restrained gold foil” is.

## Style comparison

Create exactly three candidates unless the user asks for another number.

- Candidate A should be the safest fit for subject and audience.
- Candidate B should push cultural or historical specificity.
- Candidate C should test a bolder editorial interpretation.

Render the same representative beat, wording, aspect ratio, and anchor in every candidate.
Change the theme only. This makes the comparison meaningful.

## Image prompt grammar

Build prompts in this order:

1. `MEDIUM`: physical construction and illustration/photography treatment.
2. `SUBJECT`: focal subject, action, and identity locks.
3. `LAYERS`: foreground, middle, background, and paper objects.
4. `COMPOSITION`: framing, hierarchy, negative space, and title zone.
5. `COLOR + TYPE`: palette and exact display text.
6. `SURFACE`: edges, tape, grain, printing, shadows, registration.
7. `CONSTRAINTS`: aspect, flatness, legibility, and forbidden drift.

Use a finished poster as the image-stage goal. Rich, separable layers give the animation stage
objects it can move. A flat background with a subject pasted on top usually produces weak
motion.

Keep exact display text short. Use quotation marks around required spelling. Move long text to
captions or local overlays.

## Motion prompt grammar

Describe:

1. one camera move;
2. several named element actions;
3. motion amplitude;
4. material behavior;
5. preservation locks;
6. prohibited defects.

Example structure:

```text
CAMERA: one slow push, no reset.
ELEMENTS: the paper map unfolds; two route labels stamp in; the dotted path draws forward.
MATERIAL: rigid printed paper with hinge, slide, flap, and stamp motion.
LOCKS: preserve layout, title spelling, anchor identity, and flat frontal perspective.
AVOID: morphing, melting, text wobble, newly invented objects, looping.
```

Do not restate the entire still image. Tell the motion model how to animate what already exists.

## Anchor protection

For a portrait, protect facial geometry, skin details, hairline, eye line, and recognizable
features. For a product, protect silhouette, proportions, cap/button placement, label spelling,
logo geometry, and material finish.

Default strategy:

- Preserve the anchor photographically.
- Apply illustration and print texture to the environment.
- Use an illustrated paper-doll body only when needed.
- Keep halftone away from skin and small label text.
- Ask for body pose changes, not new facial expressions.

## Quality review

Reject or reroll a unit when any of these occur:

- the result looks like smooth CGI instead of physical print/cut paper;
- the focal subject is unclear at thumbnail size;
- theme attributes change between neighboring shots;
- a face, product, label, or headline drifts;
- the camera performs several conflicting moves;
- motion loops, reverses, melts, or invents major objects;
- captions cover the focal subject or interface-safe area;
- every shot uses the same composition or transition.

Prefer fixing the earliest faulty stage. Weak animation caused by an under-layered poster should
be fixed in the image, not hidden with more effects.
