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
      "voice_id": "auto",
      "rate": "+0%",
      "profile": "conversational",
      "prosody": {
        "comma_pause_s": 0.10,
        "clause_pause_s": 0.16,
        "sentence_pause_s": 0.22,
        "beat_pause_s": 0.26,
        "safety_pause_s": 0.16
      },
      "qa": {
        "min_sentence_pause_s": 0.16,
        "max_phrase_gap_s": 0.50,
        "max_unbroken_s": 5.50,
        "min_boundary_coverage": 0.75,
        "max_leading_s": 0.25,
        "max_trailing_s": 0.60,
        "max_silence_ratio": 0.25,
        "min_lufs": -23.0,
        "max_lufs": -13.0,
        "max_true_peak_db": -0.5
      }
    }
  }
}
```

The continuous job is registered as `voice:main`. Legacy projects without
`continuity_mode` remain segmented and use `voice:<beat-id>`.

`voice_id: "auto"` resolves from `project.language` for Chinese, English, Japanese, Korean,
French, German, Spanish, Portuguese, and Italian. Set an explicit provider voice for any other
language. Use `energetic`, `conversational`, `measured`, or `dramatic` as the bounded pacing
profile.

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
- Preserve English abbreviations, acronyms, decimals, URLs, and similar non-sentence periods.
- Split a long unpunctuated phrase at balanced language-aware units and add a safety breath.
  Never leave a one-word or one-character orphan solely to satisfy a maximum length.
- Adjust copy length and punctuation first. Keep speaking rate near normal.
- Do not speed up the whole narration to hide one long sentence.
- Do not pad a short sentence to fill a fixed scene and call the result complete.
- Retiming visuals to a good performance is valid; clipping or mechanical time-stretching is not.

## Generate and inspect

```bash
python scripts/voice_director.py <project-dir> --dry-run --json
python scripts/voice_director.py <project-dir> --overwrite
python scripts/audio_qa.py <project-dir>/media/audio/main.wav
```

The dry run reports the resolved voice, pacing profile, phrase plan, estimated duration, timeline
utilization, and safety splits before synthesis. The voice director then synthesizes stable-voice
phrases, trims provider padding, concatenates controlled pauses, writes `main.wav` plus
`main.timing.json`, and registers both. The timing manifest records each phrase's measured start,
speech end, and pause window. Final QA verifies the pure voice before music is mixed and checks
that detected pauses overlap those intended semantic windows. Rendering uses the same manifest
for phrase-level captions; legacy projects without it retain beat-level captions.

A third-party speech adapter should return a structured result with
`metadata.timing_path`. The runner validates the timing file, records
`timing_status: "provided"`, and makes phrase-level QA and captions available. A legacy adapter
that returns only a path remains usable, but the runner records `timing_status: "missing"` and QA
reports the beat-caption fallback instead of pretending that semantic timing exists.

## Blocking conditions

Block delivery when any of these remain:

- internal or cross-clip speech gap over 0.50 seconds;
- fewer than 75 percent of semantic boundaries receiving a full pause of at least 0.16 seconds;
- measured pauses occurring away from their planned semantic boundaries;
- any uninterrupted voiced run over 5.50 seconds;
- leading silence over 0.25 seconds;
- final trailing silence over 0.60 seconds;
- silence over 25 percent of a narration asset;
- integrated loudness outside the configured -23 to -13 LUFS safety envelope;
- true peak above the configured -0.5 dBTP ceiling;
- clipped phrase, abrupt join, inconsistent speaker, or intelligibility failure.

These are defaults, not targets. Passing QA requires both sides of the rhythm envelope: no dead
air and no breathless run-on delivery. A deliberate dramatic pause may use a project-specific
override, but document its reason and verify it during human review.
