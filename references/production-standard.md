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
- Give a recurring subject two or more authored poses when the story requires a change of action.
- Use sprite states for wing flaps, eye blinks, hand gestures, walking cycles, page turns, and
  object assembly. Do not fake these actions by stretching one still cutout.
- Keep a stable `pivot` for pose variants so the subject does not jump when a sprite changes.

## Motion design

- Deliver at a constant 30 fps or higher.
- Use Catmull–Rom or another velocity-continuous curve through interior motion points.
- Stagger loop phases and entrance times.
- Keep at least one meaningful local motion alive throughout each shot.
- Move flying, falling, thrown, or drifting objects along a curved `motion_path`.
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
- Sprite changes preserve registration and do not flash, resize, or shift unexpectedly.
- Curved-path objects do not teleport at loop boundaries.
- Captions remain inside the safe area and match the spoken text.
- Audio has no clipped syllables, abrupt segment joins, robotic rate changes, or music masking.
- Review the full MP4 at delivery speed; contact sheets and GIFs are supporting evidence only.
