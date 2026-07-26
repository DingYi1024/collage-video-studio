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
      "prosody": {
        "comma_pause_s": 0.10,
        "clause_pause_s": 0.16,
        "sentence_pause_s": 0.22,
        "beat_pause_s": 0.26
      },
      "qa": {
        "min_sentence_pause_s": 0.16,
        "max_phrase_gap_s": 0.50,
        "max_unbroken_s": 5.50,
        "min_boundary_coverage": 0.75,
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
- Treat a continuous track as one performance with designed breaths, not one uninterrupted
  utterance. Add four calibrated pauses after removing provider padding: comma 0.10 seconds,
  clause 0.16, sentence 0.22, and beat boundary 0.26. Quiet attacks and releases normally make
  the measured gaps slightly longer.
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

The voice director splits the script at semantic punctuation, synthesizes stable-voice phrases,
trims provider padding, and concatenates them with controlled pauses. It rejects narration that is
too long or leaves excessive blank time. The final project QA inspects registered pure-voice
assets before music is mixed, so background music cannot hide a broken narration track.

## Blocking conditions

Block delivery when any of these remain:

- internal or cross-clip speech gap over 0.50 seconds;
- fewer than 75 percent of semantic boundaries receiving a full pause of at least 0.16 seconds;
- any uninterrupted voiced run over 5.50 seconds;
- leading silence over 0.25 seconds;
- final trailing silence over 0.60 seconds;
- silence over 25 percent of a narration asset;
- clipped phrase, abrupt join, inconsistent speaker, or intelligibility failure.

These are defaults, not targets. Passing QA requires both sides of the rhythm envelope: no dead
air and no breathless run-on delivery. A deliberate dramatic pause may use a project-specific
override, but document its reason and verify it during human review.
