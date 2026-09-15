# How the live interpretation pipeline works

Developer-facing mechanics of `validation/scripts/live_loop.py` — the F2
continuous-streaming implementation. Product context: `prd.md`; design
rationale and history: `live-ai-interpretation-design.md` (especially
sections 8 and 13); state: `TODO.md`.

> This document describes the code as built. When the pipeline changes,
> update this file in the same commit — it is the developer documentation.

## The one rule everything else serves

**Only complete sentences are ever translated.** Opus-MT invents content
when fed truncated fragments ("two million" became "two million *people*" —
measured, see validation/mt). Every mechanism below is arranged so that rule
holds even while the speaker talks continuously. The single sanctioned
exception: a fragment held past `--max-hold` (5s) is translated as-is rather
than held forever — now bounded to ~40-word pieces (see hold path).

## Stage by stage

```
mic ──► capture callback ──► segmenter (main thread, VAD)
                                   │  (audio, final?) chunks
                                   ▼
                             ASR worker
                       IncrementalASR + sentence commit
                                   │  complete EN sentences
                                   ▼
                             MT worker  (Opus-MT en→fr)
                                   │  FR text
                                   ▼
                             TTS synth worker (Piper)
                                   │  PCM
                                   ▼
                       bounded playback queue ──► Player (speakers)
```

### 1. Capture
A PortAudio callback (`sounddevice.InputStream`, 16 kHz mono) copies mic
frames into a list under a lock. The callback must never block — it does no
processing.

### 2. Segmenter (main thread)
Every ~0.4s (twice per silence window — a cost/latency cap), the buffered
audio runs through Silero VAD (`get_speech_timestamps`):
- **Endpoint:** ≥`--silence` (0.8s) trailing silence after ≥0.25s speech →
  the utterance closes and is sent as a *final* chunk.
- **Dense speech** (no pause coming): every `--partial-sec` (6s) the buffer
  is cut 0.5s before its end and sent as a *partial* chunk. This is what
  removed the old 30-second first-translation delay: translation starts
  after ~6s of unbroken speech, not after a pause that never comes.

### 3. ASR worker — `IncrementalASR` (the core of F2)
Each continuous-speech *session* accumulates audio in a buffer. On every
feed it re-transcribes **only the un-committed tail** (faster-whisper,
greedy, English-pinned for now). Then:
- The transcript is split by `complete_sentences()` — terminal punctuation
  only, with an abbreviation guard ("Dr." doesn't end a sentence) and
  stacked-punctuation handling ("Really?!").
- Complete sentences are **committed**: the audio offset advances past the
  Whisper segment that closed the last sentence (minus a 0.2s margin), and
  committed audio is dropped from the buffer — memory stays flat no matter
  how long the speaker talks.
- The unfinished **tail is deliberately re-transcribed next pass**: Whisper
  may revise its mind about the tail, but a committed sentence never changes.
- **Revision dedupe:** if Whisper re-emits sentences we just committed
  (observed live), `drop_prefix_overlap()` removes the leading repeats.
  A genuine repeat separated by other content still passes.

### 4. Stitcher / hold path
Between sessions (after a final chunk), any unpunctuated tail text becomes
`hold_pending`. If the speaker never finishes the thought, it flushes after
`--max-hold` (5s), **split into ≤40-word pieces** by `split_long_fragment()`
— without this, one dense-podcast monologue became a single ~60s TTS blob
and spiked the backlog (measured 2026-09-15).

### 5. MT worker
One Opus-MT (CTranslate2 int8) call per sentence (~90ms). Before MT, each
sentence passes `strip_disfluencies()` — a conservative filler filter
("um", "you know", "kind of"...; NOT "like"/"so"). **Catch-up Tier 1:**
when behind, up to 3 queued sentences are merged into one call.

### 6. TTS synth worker
Piper (bundled binary, `--output_raw`) per sentence, `--length-scale 0.9`
default. **Catch-up Tier 0:** while behind, length_scale drops another 0.1
(floor 0.7) — faster speech, zero content loss. PCM + its duration enter
the backlog metric.

### 7. Playback queue + Player (the serialization point)
A **bounded** queue (`--playback-queue`, 16) drained by one Player thread in
order. Bound matters: an unbounded queue is how listener lag silently grew
to 30s+ in early runs. When the queue is full, TTS blocks — backpressure,
not accumulation.

### 8. Catch-up mode (`--catchup`, default off)
The interpreter's "falling behind" move, as a ladder (design 13.7):
backlog (seconds of synthesized-but-unplayed audio) > threshold/2 (7.5s)
activates Tier 0 (speed up) and Tier 1 (merge); backlog > threshold (15s)
triggers **Tier 3: drop** the oldest un-played sentences until backlog <
threshold/2 (hysteresis). Every drop prints and logs its full text.
Tier 2 (local-LLM summarization of backlog instead of dropping) is designed
but not built — deliberately gated on Tiers 0/1 proving insufficient.

### 9. Transcript log (PRD F11 groundwork)
Every session appends `logs/transcript-<stamp>.jsonl`:
`{"t": <iso-time>, "kind": "en"|"fr"|"dropped", "text": ...}`. Kinds are
currently the one pair's names; F3 replaces them with detected-language
tags. This file is the contract the listener-page read-along view will
stream (WebSocket/SSE at the F7/F6 milestone).

## Language handling today (pre-F3)
ASR is pinned `language="en"`; MT/TTS are the single en→fr pair. A speaker
switching languages mid-sentence is **not handled**: the foreign speech is
transcribed as mangled English and the error propagates. F3's plan (design
doc 13.9): detect language per incremental chunk (every ~6s), close the
session on a switch exactly like a pause (re-transcribe the tail under the
new language, tag logs, route MT/TTS). Between-sentence switches become
clean within ~6s; a switch inside one sentence garbles the switch point
itself — a documented limit, not a hidden one.

## Instrumentation
Per-session stats (printed at exit): ASR ms per pass, MT ms per sentence,
E2E (chunk end → FR queued), drop count, playback-backlog max, working-set
memory at start/every 5 min/end. Raw evidence lives in `validation/latency/`.
