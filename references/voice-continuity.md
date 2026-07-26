# Voice continuity

Use this before generating narration and before approving final audio.

## Default production mode

Set `audio.voice.continuity_mode` to `continuous` for new narrated shorts. Generate the full
narration as one performance so sentence rhythm survives scene boundaries:

```json
{
  "audio": {
    "voice": {
      "continuity_mode": "continuous",
      "rate": "-2%",
      "qa": {
        "max_phrase_gap_s": 0.35,
        "max_leading_s": 0.25,
        "max_trailing_s": 0.60,
        "max_silence_ratio": 0.25
      }
    }
  }
}
```

The continuous job is registered as `voice:main`. Legacy projects without
`continuity_mode` remain segmented and use `voice:<beat-id>`.

## Write to the timeline

- Write the full narration before fixing scene boundaries.
- Use normal punctuation and short spoken clauses.
- Budget Mandarin at roughly 3.5–4.5 characters per second and English at 2–2.7 words per
  second, then replace the estimate with measured speech duration.
- Keep natural sentence gaps around 0.15–0.30 seconds.
- Adjust copy length and punctuation first. Keep speaking rate near normal.
- Do not speed up the whole narration to hide one long sentence.
- Do not pad a short sentence to fill a fixed scene and call the result complete.
- Retiming visuals to a good performance is valid; clipping or mechanical time-stretching is not.

## Generate and inspect

```bash
python scripts/voice_director.py <project-dir> --dry-run
python scripts/voice_director.py <project-dir> --overwrite
python scripts/audio_qa.py <project-dir>/source-media/audio/main.wav
```

The voice director rejects narration that is too long or leaves excessive blank time. The final
project QA inspects registered pure-voice assets before music is mixed, so background music cannot
hide a broken narration track.

## Blocking conditions

Block delivery when any of these remain:

- internal or cross-clip speech gap over 0.35 seconds;
- leading silence over 0.25 seconds;
- final trailing silence over 0.60 seconds;
- silence over 25 percent of a narration asset;
- clipped phrase, abrupt join, inconsistent speaker, or intelligibility failure.

These are defaults, not targets. A deliberate dramatic pause may use a project-specific override,
but document its reason and verify it during human review.
