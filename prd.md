# Product Requirements Document — Live AI Conference Interpretation

> Living document: features are captured here as they surface during design, testing, and use.
> The technical *why/how* lives in `live-ai-interpretation-design.md` (the design doc); test
> evidence lives in `validation/`; current state (done / in progress / pending) lives in `TODO.md`.
> This file says WHAT the product must do — and, to keep everything in one place, ends with a
> summary of the tech it runs on (section 6).

## 1. Problem

Conference interpretation today means hiring human interpreters and mixing their audio into
per-language channels. This product replaces (or assists) the interpreter role with local AI:
speaker's speech → text → translated text → synthesized speech, running entirely on local
models — no cloud, no venue-internet dependency. Distribution to listeners is not rebuilt:
the existing LANStreamer layer already delivers per-language channels to listeners' phones
over local WiFi with no app install.

## 2. Users

- **Operator/organizer** — sets up and monitors the system for an event: selects languages, loads glossaries, starts/stops channels.
- **Listener** — opens a browser page, picks a language channel. No install, no account.
- **Speaker** — unaffected: talks normally, in any of the event's languages. No wearables, no turn-taking, no behavior change required.

## 3. Features

### F1 — Live interpretation, one language pair (PoC scope)
Speaker's audio is transcribed, translated, and spoken in one target language in near-real-time, on local hardware. First pair: English → French; then Spanish, Portuguese.

### F2 — Continuous streaming (not turn-based)
Conference speech is continuous — the speaker does not pause for the interpreter. The system must continuously chunk incoming audio, translate, and stream TTS output *while the speaker keeps talking*. Sentence-boundary buffering before MT is a hard requirement (Opus-MT hallucinates completions on truncated fragments — see design doc section 8); making buffering coexist with continuity against the latency target is a core engineering problem, tracked as an open question in the design doc.

### F3 — Multi-language auto-detection and fan-out
- Before an event, the operator preselects the event's working languages (e.g. 3) on the admin interface.
- The system listens for **any** of the preselected languages via automatic language detection, per utterance.
- Whatever is spoken is translated into **all the other** preselected languages.
- The detected speaker's language is automatically **disabled as an output** for that utterance — a language is never echoed back at its own speakers.
- Speakers switching languages mid-event is a normal case, not an edge case.

### F4 — Per-event voice (TTS) selection
Each event's target language gets an auditioned voice; regional variant (fr_FR vs African French, pt_PT vs pt_BR, ...) is a per-event decision made during voice selection, never fixed globally.

### F5 — Pre-event glossary
Upload event documents (agenda, speeches, name lists). The system auto-extracts candidate terms/names (NER), a human reviews and edits the list, and it persists per event — feeding ASR prompt-biasing and MT terminology constraints. Auto-extraction and manual review are both required. (Design doc section 7.)

### F6 — Admin dashboard
Operator-facing interface, extending today's LANStreamer dashboard: preselect event languages (F3), manage glossaries (F5), start/stop per-language channels.

### F7 — Listener distribution
Reuse LANStreamer as-is: per-language browser channels over local WiFi. Each channel's audio source becomes this system's TTS output for that language (via virtual audio cables) instead of a human interpreter's microphone.

### F8 — Single-install product (packaging)
The final product is **one installer**: download the `.exe` (Windows) or `.dmg` (macOS), install, and you have everything — admin dashboard, language/voice settings, START STREAMING, a listener URL to share, and per-language channels listeners tap in their browser. The installer bundles the ls2 interpreter (native), the LANStreamer-style web server, FFmpeg/Icecast binaries, and all models inside it. From the user's seat it is one piece of software; this does **not** require the code to live in one repo — ls2 (engine) and LANStreamer (distribution/UI logic to harvest) stay separate codebases and get assembled into one app at packaging time. No system dependencies to install by hand, no PATH setup, no internet at install time beyond the download itself.

### F9 — "Check this PC" preflight
The installer/app includes a one-click system check that verifies the machine can actually run the event before it starts: CPU/AVX2 support, RAM, free disk (models are GBs), audio input/output devices present and reachable, and a quick 10-second pipeline dry-run ("we heard you, translation works"). Green/red result per check, in plain language, with what to do about a red. Thresholds come from the real PoC benchmarking data (design doc section 9), not guesses.

### F10 — Security-software friction (edge case, build later)
Some antivirus/SmartScreen setups flag apps that bundle binaries like FFmpeg (unsigned installers, especially). When it happens the app must not just fail silently: detect what it can, and show a plain-language message telling the user to allow/trust the app so it can do what it needs to do. Longer term: code-sign the installers, which removes most of this class entirely. Not a priority until packaging (F8) — recorded so it's built for, not discovered at an event.

## 4. Non-goals (current phase)

- Multi-language fan-out before the single-pair PoC works.
- Packaging/installers — after the PoC works.
- Unknown venue hardware — runs on team-owned machines; minimum specs defined after the PoC.
- Cloud models or venue internet — hard constraint: fully local.

## 5. Quality targets (provisional)

Latency and other starting targets live in the design doc, to be validated once the PoC shows what is actually achievable. Not restated here so they can't drift out of sync.

## 6. Technical foundations

Yes, kept in the PRD on purpose: one document, and the team is technical. Requirements above say *what*; this says *what it runs on*. Decisions and reasoning: design doc. How far along it is: `TODO.md`.

| Layer | Choice |
|---|---|
| ASR | faster-whisper, int8, CPU — `small` recommended |
| Language detection | Whisper's built-in language ID, per utterance — requires a multilingual checkpoint (e.g. `small`, not `small.en`) |
| MT | Opus-MT via CTranslate2 int8 — one model per **directional** pair, so N preselected languages need N×(N−1) models (F3); French/Spanish/Portuguese covered, NLLB-200-distilled-600M fallback for uncovered languages |
| TTS | Piper, per-event voices |
| Streaming behavior | Silero VAD utterance chunking + sentence-boundary buffer before MT (hard requirement — design doc section 8) |
| Distribution | LANStreamer + Icecast; VB-Audio virtual cables to route TTS into channels |
| Packaging | Single installer (.exe/.dmg) bundling interpreter + web server + FFmpeg/Icecast + models (F8); Docker is dev/testing only, never shipped |
| Hardware (benchmark) | Ryzen 7 5800X, RX 6800 XT 16GB, 64GB RAM, Windows 11 |

Key scripts: `live-loop.cmd` (repo-root launcher for the live test loop), `validation/scripts/live_loop.py` (the loop itself), `mt_smoke.py`, `mt_smoke_partials.py`, `asr_bench.py`, `make_tts_samples.sh`.
