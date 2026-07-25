# Production standard

Use this standard when the user asks for a polished paper-animation short, a portfolio case,
or quality comparable to a finished social-video production.

## Story and direction

- Build one visible story turn every 4–8 seconds.
- Give each scene a subject action, not only a camera move.
- Establish the visual promise in the first three seconds.
- End on a resolved image rather than a frozen leftover frame.
- Keep one coherent medium, palette, paper texture, edge treatment, and shadow direction.

## Layer and pose design

- Use at least six owned layers per shot across background, middle, subject, effects, and
  foreground depth planes.
- Animate at least four layers independently.
- Give a recurring subject authored poses when the story requires a change of action, but keep
  one whole-body pose stable inside each shot.
- Change a major pose at a shot cut or behind an occluding foreground paper layer. Never
  crossfade unrelated full-body silhouettes.
- Use registered sprite states for small local changes only: blinks, mouth shapes, page states,
  and true frame-by-frame cycles.
- Build articulated paper objects from rigid parts with real pivots: body plus wings, torso plus
  limbs, stem plus leaves. Do not stretch or morph one still cutout.
- A walking cycle must maintain planted-foot contact and root-speed continuity. If those assets
  do not exist, hold a stable pose instead of sliding a character across the ground.

## Motion design

- Deliver at a constant 30 fps or higher.
- Use Catmull–Rom or another velocity-continuous curve through interior motion points.
- Stagger loop phases and entrance times.
- Keep at least one meaningful local motion alive throughout each shot.
- Keep animal and character root paths short unless an authored cycle supports the travel.
- Couple wing angle, body bob, and path speed; a butterfly is not one sticker moving on a curve.
- Use one restrained camera action per shot and different parallax rates by depth plane.
- Use 2× oversampling for slow diagonal movement, rotation, and small cutout animation.
- Use temporal motion-blur samples only when fast motion still judders after timing is correct.

## Transitions

- Design transitions as part of adjacent scenes, normally 0.2–0.5 seconds.
- Prefer paper wipes, foreground occlusion, match motion, page turns, slides, and short dissolves.
- Do not hide an unrelated hard cut under a long generic fade.
- Preserve continuous cadence through the transition; do not freeze either shot at the midpoint.

## Voice and sound

- Use one natural, consistent voice identity for the full piece.
- Direct tone, age impression, pace, pitch, emotion, and pause behavior explicitly.
- Write for speech: short clauses, natural punctuation, and no forced four-second sentence length.
- Generate clean speech before timing scenes; adjust scene timing to the voice when necessary.
- Avoid default operating-system TTS in portfolio demonstrations.
- Keep narration peaks clear, use restrained music, and duck music under speech.
- Add sparse action cues only when they support visible paper movement.

## Review thresholds

- Opening remains understandable with audio muted.
- No unintended still segment lasts 0.12 seconds or more while a scene is meant to be active.
- No shared keyframe stop affects most moving layers.
- Major poses never crossfade; small sprite changes preserve registration and do not flash,
  resize, or shift unexpectedly.
- Feet do not slide, wing roots do not separate, and rigid paper parts do not bend or morph.
- Curved-path objects do not teleport at loop boundaries.
- Captions remain inside the safe area and match the spoken text.
- Audio has no clipped syllables, abrupt segment joins, robotic rate changes, or music masking.
- Review the full MP4 at delivery speed; contact sheets and GIFs are supporting evidence only.
