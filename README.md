# [Project Name] — Live AI Conference Interpretation

> Working title — repo currently named `ls2`. See naming discussion in project notes before publishing; swap this heading once decided.

An AI-based replacement for the human-interpreter side of a live conference interpretation setup: one speaker's audio is transcribed, translated into 2–5 target languages, and synthesized back into speech in real time, running entirely on local models — no cloud dependency, no reliance on venue internet.

This project handles the *interpretation* (speech → text → translated text → speech). Distribution to listeners is handled separately by [LANStreamer](https://github.com/jerryagenyi/lanstreamer), which already solves the browser-based, no-install fan-out over local WiFi.

## Status

Tracked in [`TODO.md`](./TODO.md) — what's done, what's blocked, what's next. Validation evidence lives in [`validation/validation-report.md`](./validation/validation-report.md).

## Why this exists

Conference interpretation today typically means hiring human interpreters and mixing their audio into per-language channels. LANStreamer already solves getting those channels to listeners' phones over WiFi with no app install. This project asks: can the interpreter role itself be replaced (or assisted) by local AI models, cheaply and reliably enough to be worth deploying, without needing an internet connection at the venue?

## Design

The full design rationale — architecture, tech choices and why, known failure modes, minimum system requirements, and open questions — lives in [`live-ai-interpretation-design.md`](./live-ai-interpretation-design.md). Read that before making changes here; it captures a lot of decisions (and the reasoning behind them) that aren't repeated in this README.

## Repo structure

```
├── live-ai-interpretation-design.md   # full design doc — read this first
├── prd.md                             # product requirements — features captured as they emerge
├── TODO.md                            # tracking — done / in progress / blocked / next
├── live-loop.cmd                      # run the live mic→French test loop (from repo root)
├── requirements.txt                   # pinned Python deps for the venv
├── docs/
│   ├── test-plan.md                   # automated + manual test plan
│   ├── HOW-IT-WORKS.md                # developer mechanics of the pipeline
│   └── journal/                       # dated engineering log — what changed and why
├── validation/
│   ├── mt/                            # machine translation smoke test results
│   ├── tts/                           # TTS voice samples for audition
│   ├── models/                        # local model copies (gitignored) — no HuggingFace at runtime
│   ├── scripts/                       # benchmark + test scripts (live_loop.py et al.)
│   └── validation-report.md           # summary of the pre-PoC validation pass
└── README.md
```

## Getting started

To try the current state locally (Windows, mic + speakers): run `.\live-loop.cmd` from the repo root and speak English — French comes out of the speakers. All models load from `validation/models/` (local copies — no internet/HuggingFace access at runtime); Python dependencies are pinned in `requirements.txt`. `.\live-loop.cmd --list-devices` picks a different mic/output; `--voice fr_FR-tom-medium` (or `upmc`) auditions the other voices. Testing what to do next is in [`docs/test-plan.md`](./docs/test-plan.md). The full PoC pipeline (continuous streaming, multi-language) is the next milestone (see `TODO.md`).

## Related projects

- [LANStreamer](https://github.com/jerryagenyi/lanstreamer) — the distribution layer this project feeds into.
