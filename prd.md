# Product Requirements Document — Live AI Conference Interpretation

> Living document: features are captured here as they surface during design, testing, and use.
> The technical *why/how* lives in `live-ai-interpretation-design.md` (the design doc); test
> evidence lives in `validation/`. This file says WHAT the product must do — and, to keep
> everything in one place, ends with a summary of the tech it runs on (section 7).

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

## 3. Current state (2026-09-13)

- Validation pass complete for English → French (`validation/validation-report.md`): ASR PASS, TTS speed PASS, MT CONDITIONAL pending native-speaker review.
- **Live single-pair loop works end-to-end** on the benchmark PC (`live-loop.cmd`): speak English, hear French. Deliberately turn-based (waits for sentence end before translating) — a stage smoke-test, not the product.
- Blockers to "validated": native-speaker sign-off on both MT tables; final voice pick.

## 4. Features

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

## 5. Non-goals (current phase)

- Multi-language fan-out before the single-pair PoC works.
- Packaging/installers — after the PoC works.
- Unknown venue hardware — runs on team-owned machines; minimum specs defined after the PoC.
- Cloud models or venue internet — hard constraint: fully local.

## 6. Quality targets (provisional)

Latency and other starting targets live in the design doc, to be validated once the PoC shows what is actually achievable. Not restated here so they can't drift out of sync.

## 7. Technical foundations

Yes, kept in the PRD on purpose: one document, and the team is technical. Requirements above say *what*; this says *what it runs on*. Decisions and reasoning: design doc.

| Layer | Choice | Status |
|---|---|---|
| ASR | faster-whisper, int8, CPU — `small` recommended | Validated (RTF 0.15, clean transcripts). whisper.cpp + Vulkan GPU comparison deferred — needs VS Build Tools. |
| Language detection | Whisper's built-in language ID | Planned (F3); not yet tested. |
| MT | Opus-MT via CTranslate2 int8 (French/Spanish/Portuguese); NLLB-200-distilled-600M fallback for uncovered languages | CONDITIONAL — ~115ms/sentence; native-speaker review of both test tables pending. |
| TTS | Piper, per-event voices | Speed validated (15–17x real-time); voice pick among 3 fr_FR candidates pending. |
| Streaming behavior | Silero VAD utterance chunking + sentence-boundary buffer | Proven in the test loop (`validation/scripts/live_loop.py`). |
| Distribution | LANStreamer + Icecast; VB-Audio virtual cables to route TTS into channels | Existing infrastructure, unchanged. |
| Hardware (benchmark) | Ryzen 7 5800X, RX 6800 XT 16GB, 64GB RAM, Windows 11 | PoC target machine; general min-spec later. |

Key scripts: `live-loop.cmd` (repo-root launcher for the live test loop), `validation/scripts/live_loop.py` (the loop itself), `mt_smoke.py`, `mt_smoke_partials.py`, `asr_bench.py`, `make_tts_samples.sh`.

## 8. Open dependencies

- Native French speaker reviews both MT tables (`validation/mt/mt_smoke_results.md`, `mt_smoke_partials_results.md`) — blocks MT sign-off.
- Voice pick among `fr_FR-siwis-medium` / `fr_FR-tom-medium` / `fr_FR-upmc-medium`.
- VS Build Tools install → whisper.cpp build → Vulkan GPU path (optimization phase).
- Continuous-streaming design that honors sentence-boundary buffering within the latency target.
