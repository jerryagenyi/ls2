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

---

# Replays after the playback fix (same day, ~1-2 min of the same video each)

## Run 1 — default (no catch-up)

| Metric | Value |
|---|---|
| ASR | n=5, avg 2,483 ms, max 4,104 ms |
| MT | n=20, avg 93 ms |
| E2E (utterance end→FR queued) | avg 3,672 ms |
| Playback backlog max | **30.9 s** |
| Playback waits | climbing to 33.5 s |
| Dropped | 0 |

Playback confirmed working (SPK lines throughout). Without catch-up, listener
lag grows unboundedly under continuous video speech — as predicted by the
baseline, now measured end-to-end.

## Run 2 — `--catchup` (threshold 15s)

| Metric | Value |
|---|---|
| ASR | n=6, avg 2,295 ms |
| MT | n=19, avg 103 ms |
| E2E | avg 3,527 ms |
| Playback backlog max | **12.5 s** (never crossed the 15 s threshold) |
| Playback waits | ≤ 13.0 s |
| Dropped | 9 sentences |

Catch-up mode did its job: backlog bounded (~12.5s vs 30.9s), waits capped,
and the stitcher incidentally showed good compression behavior (a fragment
carried across utterances merged into one longer MT call).

## New finding: first-translation latency in dense speech (~30 s)

Jerry observed French didn't start until ~30s into the video. Root cause:
in the current design ASR runs only on *closed* utterances, and a dense
podcast has no silence ≥0.8s — so the first utterance closes only at the
30s force-flush. The E2E metric (3.5s) measures from utterance END, which
hides this. Implication for F2's next increment: **incremental in-utterance
ASR** — transcribe the growing buffer every few seconds and emit sentences
as they complete, instead of waiting for an endpoint. This also needs a new
metric: time from speech START to first French audio.

Also pending from design 13.4 item 3: the audible "content skipped" cue that
should accompany drops (drops currently print to console only) — matters
before catch-up is ever enabled at a real event.
