# F2 round 1 — YouTube podcast audio through speakers (2026-09-14)

First live run of the F2 refactored pipeline. Continuous real-world speech
(American podcast/video audio played to the mic) for ~1m46s.

**Invalidated for playback conclusions:** the run had NO French audio — a
pipeline wiring bug (tts_worker wrote to a bounded `playback_q` that the
Player never read; French PCM piled up unread). Diagnosed from the log (zero
`SPK` lines, `backlog max: 0.0s` despite 32 translations), reproduced
headlessly, fixed same day (Player now owns/drains the bounded queue).
The ASR/MT numbers below remain valid — they're upstream of the break.

## Valid observations

| Metric | Value | vs. speech baseline |
|---|---|---|
| ASR (utterance→EN) | n=9, avg 2,440 ms, max 4,079 ms | much larger — expected: video speech is continuous, so utterances hit the 30s force-flush and are long; still far faster than real-time |
| MT (EN→FR) | n=32, avg 89 ms, max 248 ms | unchanged |
| E2E (utterance end→FR queued) | n=30, avg 3,654 ms | similar shape |
| Memory | 555 → 534 MB | stable |

- **Real continuous content works upstream**: 30s-force-flushed long
  utterances, hold-expiry fragments, and multi-sentence stitching all behaved.
- **Filler hallucination, live occurrence #2**: "Thank you." transcribed and
  translated at session end from silence/video-end audio — user confirmed he
  never said it. Same class as M7's "I'll see you in the next video".
  Strengthens the TODO known-phrase filter item (now with two live cases).
- ASR handled American podcast delivery well (proper nouns mostly correct:
  Hasan Piker; a few "cringe"→"crange"-class errors under fast speech).
  Accent-robustness for African English accents remains a later,
  explicitly-noted concern (model choice / fine-tuning — deferred).

## Replay needed

Re-run the same scenario after the playback fix (with and without
`--catchup`) before drawing playback/backlog conclusions from video audio.
