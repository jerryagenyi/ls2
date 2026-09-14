# Project Tracking

This is the only document that tracks state. `README.md` orients a new reader, `live-ai-interpretation-design.md` explains why/how, `prd.md` defines what the product must do. This file says what's done, what's blocked, and what's next — nothing here duplicates the reasoning in those other docs, just points at the relevant section.

Update this file as work happens. If a fact belongs here, it doesn't belong in the README, the design doc, or the PRD.

## 🚧 Blocking — needs a human

- [ ] Native French speaker reviews both MT tables (`validation/mt/mt_smoke_results.md`, `mt_smoke_partials_results.md`) — see `docs/native-speaker-review-guide.md` for what to show them and how. Blocks MT sign-off.
- [ ] Pick a Piper voice among `fr_FR-siwis-medium` / `fr_FR-tom-medium` / `fr_FR-upmc-medium` — audition with `--voice` flag on `live_loop.py`.

## ✅ Done

- [x] Design doc drafted and iterated (`live-ai-interpretation-design.md`)
- [x] PRD created (`prd.md`), features F1–F7 captured
- [x] Validation pass, English → French: ASR PASS (faster-whisper `small`, RTF 0.15), TTS speed PASS (Piper, 15–17x real-time), MT CONDITIONAL (Opus-MT, ~115ms/sentence)
- [x] MT fragment retest — caught a real hallucination ("two million" → invented "two million people" on a truncated fragment); confirmed sentence-boundary buffering as a hard requirement
- [x] Live single-pair test loop built and working end-to-end (`validation/scripts/live_loop.py`) — speak English, hear French. Deliberately turn-based; a stage smoke-test, not the product.
- [x] **Offline models** — all models load from `validation/models/` (faster-whisper tiny/base/small copied in; Marian tokenizer already local); zero HuggingFace/network access at runtime, verified with `HF_HUB_OFFLINE=1`. Note: `transformers` 5.x broke `AutoTokenizer` for Marian — scripts now use `MarianTokenizer` explicitly.
- [x] Audio-buffer efficiency fix in `live_loop.py` — VAD pass runs at most twice per silence window instead of every 0.1s tick (capped added end-of-utterance latency at silence/2).
- [x] Dependencies pinned in `requirements.txt`; UTF-8 verified explicit at every text/file boundary in the scripts.
- [x] Test plan written (`docs/test-plan.md`) — automated (unit/model-integration/soak) + manual (smoke, robustness matrix, human quality gates, LANStreamer integration).
- [x] **Manual test pass M1–M10, R4 run (2026-09-14)** — full log in `TEST-RESULT.md`, results recorded in the test plan. Net: offline confirmed by user (M10), turn-based loop healthy (M2/M3/M5), three bugs found and fixed same day: abbreviation sentence-splitting ("Dr." became its own fragment — M4), traceback on bad `--input-device` (M9), traceback on Ctrl+C during playback (M6). Open findings: ASR mishears "naira" until repeated (M4 — glossary/F5 territory), speakers-on echo loop with filler hallucination (M7 — real answer is headphones/virtual cable; filter helps), mic-loss gives silent stop not a message (M8), R1–R3 still unrun, R4 was 35min not 60 with no memory numbers.

## 🔨 In progress

- [ ] **Remaining manual tests**: R1–R3 (device robustness — worth doing with me driving, not solo) and a full-hour R4 with memory numbers. Then the two Blocking items above — everything downstream waits on them.

## 📋 Not started

- [x] **Pytest scaffolding built and green (2026-09-14)**: `tests/` with U1 (sentence splitting incl. the M4 "Dr." abbreviation regression and stacked punctuation), U2 (voice metadata fallback), U4 (tokenizer round-trip), U5 (Unicode/tone-mark invariants), I1 (MT canonical + the "two million" hallucination regression + latency ceiling), I2 (piper PCM), I3 (offline tokenizer load with HF_HUB_OFFLINE=1), I4 (clean exit on missing models), I5 (ASR determinism). Run: `pytest` (unit, ~2s, models not needed) / `pytest -m models` (~32s, needs validation/models/). Config in `pytest.ini`; pytest added to `requirements.txt`. P1/P2 (soak/latency instrumentation) still to build.
- [ ] **Robustness of the live loop** (test-plan §2.2, LANStreamer lesson — devices are the #1 field failure): handle mic unplugged mid-session, wrong/nonexistent `--input-device` names, Bluetooth headset profile switches, output sample-rate mismatches — currently these are unhandled PortAudio errors or hangs. Run M8–M10/R1–R3 first to record actual behaviour.
- [ ] **Docker boundary** (design doc §11 step 5): dockerise LANStreamer/Icecast distribution for repeatable testing only; keep the interpretation pipeline native (containers get no audio-device access on Windows/macOS). Final packaging = Electron-style installer (.exe/.dmg) with all models bundled — layout already compatible (local model paths).
- [ ] **Model setup doc/script**: document exact download sources + expected layout for `validation/models/` and `validation/bin/` so a fresh clone can reproduce the environment (`requirements.txt` exists; model fetch doesn't).
- [ ] **F2 — Continuous streaming.** Design section 13; incremental in-utterance ASR, catch-up Tiers 0/1, and transcript logging (F11 groundwork, `logs/transcript-*.jsonl`) all **built (2026-09-15), 36 tests green**. Remaining: YouTube replay to verify first-French lag dropped from ~30s to ~9s and see whether Tiers 0/1 cut the drop count before deciding if Tier 2 (LLM summarize) is needed at all; audible drop cue before any real event; F2 closes on that evidence.
- [ ] **F3 — Multi-language auto-detection + fan-out + suppression.** Operator preselects N languages; system detects which is spoken per utterance and translates to the rest; detected language auto-disables as an output. Needs a multilingual Whisper checkpoint (not `.en`-only) and N×(N−1) directional MT pairs, not one-per-target (design doc section 4).
- [ ] **F4 — Per-event voice selection UI.** Beyond the current CLI `--voice` flag.
- [x] **F8 — Single-install product (packaging) defined** (PRD): one installer bundles interpreter + LANStreamer-style web server + FFmpeg/Icecast binaries + models; separate repos, assembled at packaging time. Implementation itself is post-PoC.
- [ ] **F9 — "Check this PC" preflight** (PRD): one-click system check (CPU/AVX2, RAM, disk, audio devices, 10s pipeline dry-run) with plain-language green/red results. Depends on real benchmark data from the PoC for thresholds — not before.
- [ ] **F10 — Security-software friction** (PRD edge case): detect AV/SmartScreen blocking, show allow/trust guidance; code-signing as the eventual fix. Build during packaging (F8), not before.
- [ ] **F5 — Pre-event glossary.** Document upload → NER extraction → manual review/edit → feed into ASR/MT.
- [ ] **F6 — Admin dashboard.** Language preselection, glossary management, channel start/stop.
- [ ] **F7 — LANStreamer integration.** VB-Audio CABLE-A/B are already installed on the benchmark PC; routing TTS output through them into LANStreamer channels hasn't been tested yet (test-plan §2.4 X1–X3 cover it).
- [x] **Soak/latency instrumentation built (P2/P1, 2026-09-14)**: `live_loop.py` now logs per-utterance ASR/MT/end-to-end timings, per-sentence playback wait + audio duration (`SPK [...]`), working-set memory at start/every 5min/end, and a session summary on exit. **Baseline captured the same day** — including a ~1-minute continuous-speech stress run: `validation/latency/2026-09-14-continuous-speech.md`. Headlines: compute ~0.1s/sentence (not the bottleneck); sentence-boundary buffering held with zero hallucinations under continuous speech; the measured F2 problem is playback backlog (lag grows ~1s per second of continuous speech, SPK waits to 15s) — F2 must compress (TTS speedup, disfluency stripping, recency policy), not just speed up models.
- [ ] whisper.cpp build (needs Visual Studio Build Tools, C++ workload) → unlocks Vulkan GPU path comparison against faster-whisper.
- [ ] General minimum system spec (beyond the draft 8GB VRAM / CPU-fallback targets in the design doc) — needs real benchmarking data first.
- [ ] Packaging (Electron/native-binary distributable) — deferred until the PoC pipeline itself works.
- [ ] **Drop `transformers` dependency** — talk to the opus-mt tokenizer's sentencepiece files (`source.spm`/`target.spm`/`shared_vocabulary.txt`) directly instead of MarianTokenizer. Kills the "PyTorch not found"/sacremoses messages and removes a big dependency from the final installer (design doc 6c). Do it when MT stage is next touched; verify translations unchanged via the I1 tests.
- [ ] **Whisper filler-hallucination filter.** Whisper (any variant, local or cloud) occasionally returns filler text on near-silent audio instead of empty — two live cases now: M7 ("I'll see you in the next video" from speaker echo) and the YouTube run ("Thank you." from video-end silence, user confirmed unsaid; `validation/latency/2026-09-14-youtube-run.md`). The public repo scan (kunwardhruv/Realtime-Voice-Translator) documents the same class with a known-phrase filter as the fix. Cheap, tech-agnostic second line of defense alongside VAD, before transcript text reaches the sentence buffer. (Also from that repo, independent confirmation that fixed-window audio chunking fails exactly the way our validation predicted — vindicates the VAD design.)
- [ ] Spanish and Portuguese validation passes (repeat the section 6a process — MT go/no-go, TTS voice audit, ASR benchmark — for each new pair).

## ⚠️ Known risks to keep an eye on

- Sentence-boundary buffering (hard requirement) vs. the ≤5s latency target vs. continuous streaming (F2) — no solution yet, just an identified tension.
- No African-language TTS voice exists for Piper — confirmed for French; will need re-checking whenever an African language pair comes up (design doc section 6a).
