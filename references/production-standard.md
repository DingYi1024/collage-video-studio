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
- Animate at least three layers independently, but treat this as a safety floor rather than a
  quality score. Low-density evidence shots should keep most layers still.
- Give a recurring subject authored poses when the story requires a change of action, but keep
  one whole-body pose stable inside each shot.
- Store those poses as a registered full-canvas `pose_sequence`; use persistent visibility
  events for entrances and exits so a subject cannot flash for one frame.
- Change a major pose at a shot cut or behind an occluding foreground paper layer. Never
  crossfade unrelated full-body silhouettes.
- Use registered sprite states for small local changes only: blinks, mouth shapes, page states,
  and true frame-by-frame cycles.
- Default people and recurring subjects to a stable whole-body paper cutout or a root plus one or
  two useful parts. Fluid keyframe travel is more important than simulated anatomy.
- Build articulated paper objects from rigid parts only when a visible joint action carries story
  information: body plus wings, torso plus pointing arm, stem plus leaves.
- Declare connected parts as an `articulated-paper` rig. Child joints use rig-space following,
  full translation inheritance, and zero lag so shoulder, elbow, and hinge roots cannot separate.
- Drive dependent parts with explicit follower relationships. Wheels inherit vehicle translation;
  flame inherits rocket translation; clothing may inherit a restrained, delayed subset.
- Register contact intervals for planted feet, wheels, landed coins, stamps, and resting cards.
- A shot that explicitly depicts realistic walking must maintain planted-foot contact and
  root-speed continuity. Stylized editorial travel may move one stable whole-body cutout without
  pretending to animate a gait.
- If a full-body gait rig is chosen, declare two leg chains, alternating paired x/y foot contacts,
  minimum root travel, and bounded double support.

## Motion design

- Deliver at a constant 30 fps or higher.
- Motion-interpolate provider clips below the delivery cadence; never disguise low cadence by
  duplicating frames. Treat sources below 12 fps as unusable for polished delivery.
- Mark continuous traveling layers with `motion_intent: "continuous"` and audit them at delivery
  cadence.
- Give every shot one named primary action and physical cause.
- Time the primary action as anticipation, action, and settle; a justified final reading hold is
  allowed and should be declared in the manifest.
- Use at least three distinct framing scales across a portfolio sequence. Do not repeat the same
  background crop and subject placement in adjacent shots.
- Keep at least 55% of layers still in a low-density shot and at least 30% still in a
  medium-density shot.
- Use Catmull–Rom or another velocity-continuous curve through interior motion points.
- Do not repeat smoothstep/ease-in-out on every interior keyframe; it creates a visible stop and
  restart even when every output frame exists.
- Use segment-specific anticipation and settling curves where needed.
- Stagger entrance times. Avoid more than two identical cycles in an ordinary shot.
- Use a fixed seed for repeated motifs and a looping strip only for an environment with a
  genuinely repeatable edge.
- Prefer a meaningful entrance, change, and hold over permanent idle motion.
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
- Resolve voice identity from the declared language or require an explicit provider voice; never
  let an unsupported language silently fall back to a Mandarin voice.
- Run narration preflight before synthesis. Protect abbreviations and decimals, and insert balanced
  safety phrases into unpunctuated long sentences.
- Generate a narrated short as one continuous performance by default. Preserve sentence rhythm
  across scene cuts instead of padding one phrase into every fixed-length beat.
- Keep ordinary phrase gaps around 0.15–0.30 seconds and block unexplained measured gaps above 0.50
  seconds.
- Give at least 75 percent of sentence/beat boundaries a full pause of 0.16 seconds or more.
- Keep every uninterrupted voiced run at or below 5.5 seconds.
- Avoid default operating-system TTS in portfolio demonstrations.
- Keep narration peaks clear, use restrained music, and duck music under speech.
- Keep pure narration inside its configured loudness/true-peak envelope, then measure the final
  mix independently.
- Add sparse action cues only when they support visible paper movement.

## Review thresholds

- Opening remains understandable with audio muted.
- No unintended still segment lasts 0.12 seconds or more while a scene is meant to be active;
  declared evidence holds are allowed.
- The activity-profile audit also passes; absence of exact duplicate frames alone is not enough
  when a kinetic shot spends too long in perceptually low motion.
- No shared keyframe stop affects most moving layers.
- The sampled transform graph has no speed, rotation, scale, opacity, or contact-drift violation.
- Major poses never crossfade; small sprite changes preserve registration and do not flash,
  resize, or shift unexpectedly.
- Selected rigs keep feet or joints connected; unrigged whole-body motion remains a stable
  silhouette without flashes, fake gait cycles, or morphing.
- Curved-path objects do not teleport at loop boundaries.
- Captions remain inside the safe area and match the spoken text.
- Pure-voice QA has no excessive leading, trailing, internal, or cross-clip silence.
- Pure-voice QA reports enough semantic breathing pauses and no breathless run-on segment.
- When a timing manifest is present, pure-voice QA confirms pauses at their intended semantic
  boundaries and captions change by phrase rather than displaying an entire paragraph.
- Audio has no clipped syllables, abrupt segment joins, robotic rate changes, or music masking.
- Review the full MP4 at delivery speed; contact sheets and GIFs are supporting evidence only.
- Final average and nominal frame rates match, global freeze detection passes, and the final mix
  stays inside the configured LUFS and true-peak envelope.
