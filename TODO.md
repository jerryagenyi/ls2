# Project Tracking

This is the only document that tracks state. `README.md` orients a new reader, `live-ai-interpretation-design.md` explains why/how, `prd.md` defines what the product must do. This file says what's done, what's blocked, and what's next — nothing here duplicates the reasoning in those other docs, just points at the relevant section.

Update this file as work happens. If a fact belongs here, it doesn't belong in the README, the design doc, or the PRD.

## 🚧 Blocking — needs a human

- [ ] Native French speaker reviews both MT tables (`validation/mt/mt_smoke_results.md`, `mt_smoke_partials_results.md`) — all lines, not just the flagged ones. Blocks MT sign-off.
- [ ] Pick a Piper voice among `fr_FR-siwis-medium` / `fr_FR-tom-medium` / `fr_FR-upmc-medium` — audition with `--voice` flag on `live_loop.py`.

## ✅ Done

- [x] Design doc drafted and iterated (`live-ai-interpretation-design.md`)
- [x] PRD created (`prd.md`), features F1–F7 captured
- [x] Validation pass, English → French: ASR PASS (faster-whisper `small`, RTF 0.15), TTS speed PASS (Piper, 15–17x real-time), MT CONDITIONAL (Opus-MT, ~115ms/sentence)
- [x] MT fragment retest — caught a real hallucination ("two million" → invented "two million people" on a truncated fragment); confirmed sentence-boundary buffering as a hard requirement
- [x] Live single-pair test loop built and working end-to-end (`validation/scripts/live_loop.py`) — speak English, hear French. Deliberately turn-based; a stage smoke-test, not the product.

## 🔨 In progress

- [ ] Nothing actively in progress — next step is unblocking the two items above

## 📋 Not started

- [ ] **F2 — Continuous (non-turn-based) streaming.** Chunk/translate/stream TTS while the speaker keeps talking, without breaking the sentence-boundary buffering requirement. Core open engineering problem — see design doc's open questions.
- [ ] **F3 — Multi-language auto-detection + fan-out + suppression.** Operator preselects N languages; system detects which is spoken per utterance and translates to the rest; detected language auto-disables as an output. Needs a multilingual Whisper checkpoint (not `.en`-only) and N×(N−1) directional MT pairs, not one-per-target (design doc section 4).
- [ ] **F4 — Per-event voice selection UI.** Beyond the current CLI `--voice` flag.
- [ ] **F5 — Pre-event glossary.** Document upload → NER extraction → manual review/edit → feed into ASR/MT.
- [ ] **F6 — Admin dashboard.** Language preselection, glossary management, channel start/stop.
- [ ] **F7 — LANStreamer integration.** VB-Audio CABLE-A/B are already installed on the benchmark PC; routing TTS output through them into LANStreamer channels hasn't been tested yet.
- [ ] whisper.cpp build (needs Visual Studio Build Tools, C++ workload) → unlocks Vulkan GPU path comparison against faster-whisper.
- [ ] General minimum system spec (beyond the draft 8GB VRAM / CPU-fallback targets in the design doc) — needs real benchmarking data first.
- [ ] Packaging (Electron/native-binary distributable) — deferred until the PoC pipeline itself works.
- [ ] Spanish and Portuguese validation passes (repeat the section 6a process — MT go/no-go, TTS voice audit, ASR benchmark — for each new pair).

## ⚠️ Known risks to keep an eye on

- Sentence-boundary buffering (hard requirement) vs. the ≤5s latency target vs. continuous streaming (F2) — no solution yet, just an identified tension.
- No African-language TTS voice exists for Piper — confirmed for French; will need re-checking whenever an African language pair comes up (design doc section 6a).
