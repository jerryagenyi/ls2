# [Project Name] — Live AI Conference Interpretation

> Working title — repo currently named `ls2`. See naming discussion in project notes before publishing; swap this heading once decided.

An AI-based replacement for the human-interpreter side of a live conference interpretation setup: one speaker's audio is transcribed, translated into 2–5 target languages, and synthesized back into speech in real time, running entirely on local models — no cloud dependency, no reliance on venue internet.

This project handles the *interpretation* (speech → text → translated text → speech). Distribution to listeners is handled separately by [LANStreamer](https://github.com/jerryagenyi/lanstreamer), which already solves the browser-based, no-install fan-out over local WiFi.

## Status

**Pre-PoC validation pass complete.** Core model choices have been smoke-tested on CPU:

- **ASR** (faster-whisper, int8, VAD-chunked): `small` model recommended — runs at ~6.7x real-time, transcripts clean on manual review.
- **MT** (Opus-MT, English→French, CTranslate2 int8): ~115ms/sentence. Conditional pass — a handful of grammar/word-order glitches are flagged and awaiting native-speaker review before this is locked in. See `validation/mt/mt_smoke_results.md`.
- **TTS** (Piper): all candidate voices synthesize well above real-time (15–17x). Three Metropolitan French voices are up for audition — no African French Piper voice currently exists, so regional variant remains a per-event decision.

Full results: `validation/validation-report.md`.

**A live single-pair test loop now works end-to-end** on the benchmark PC: run `.\live-loop.cmd` from the repo root, speak English into a mic, hear French from the speakers. It is deliberately turn-based — it waits for a sentence to finish before translating — which is fine for testing each stage; continuous streaming is the PoC pipeline's problem.

**Not yet done:**
- Native-speaker sign-off on both MT test tables (the 20 clean sentences and the 15 fragmented-input results)
- Voice selection from the three Piper candidates
- whisper.cpp benchmark comparison (deferred — missing local C++ build toolchain)

Once the above are resolved, the first PoC pipeline (single script: mic capture → faster-whisper → Opus-MT → Piper → WAV output) is unblocked.

## Why this exists

Conference interpretation today typically means hiring human interpreters and mixing their audio into per-language channels. LANStreamer already solves getting those channels to listeners' phones over WiFi with no app install. This project asks: can the interpreter role itself be replaced (or assisted) by local AI models, cheaply and reliably enough to be worth deploying, without needing an internet connection at the venue?

## Design

The full design rationale — architecture, tech choices and why, known failure modes, minimum system requirements, and open questions — lives in [`live-ai-interpretation-design.md`](./live-ai-interpretation-design.md). Read that before making changes here; it captures a lot of decisions (and the reasoning behind them) that aren't repeated in this README.

## Repo structure

```
├── live-ai-interpretation-design.md   # full design doc — read this first
├── prd.md                             # product requirements — features captured as they emerge
├── live-loop.cmd                      # run the live mic→French test loop (from repo root)
├── validation/
│   ├── mt/                            # machine translation smoke test results
│   ├── tts/                           # TTS voice samples for audition
│   ├── scripts/                       # benchmark + test scripts (live_loop.py et al.)
│   └── validation-report.md           # summary of the pre-PoC validation pass
└── README.md
```

## Getting started

To try the current state locally (Windows, mic + speakers): run `.\live-loop.cmd` from the repo root and speak English — French comes out of the speakers. `.\live-loop.cmd --list-devices` picks a different mic/output; `--voice fr_FR-tom-medium` (or `upmc`) auditions the other voices. The full PoC pipeline (continuous streaming, multi-language) is the next milestone (see Status above).

## Related projects

- [LANStreamer](https://github.com/jerryagenyi/lanstreamer) — the distribution layer this project feeds into.
