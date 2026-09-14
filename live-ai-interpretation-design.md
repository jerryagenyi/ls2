# Live AI Interpretation — Design Notes

Status: draft for iteration. Not a spec yet — a working document to pressure-test before building a proof of concept (PoC).

## 1. What this is

An AI-based replacement for the human-interpreter side of a conference interpretation setup. One speaker's audio is transcribed using automatic speech recognition (ASR), translated into 2–5 target languages using machine translation (MT), and synthesized back into speech using text-to-speech (TTS). The result is distributed to listeners.

This picks up where [LANStreamer](https://github.com/jerryagenyi/lanstreamer) left off — see section 3 for how it works and how this project connects to it.

## 2. Scope decisions made so far

- **The PoC targets Jerry's own PC** (AMD Ryzen 7 5800X, AMD Radeon RX 6800 XT graphics card with 16GB of video memory (VRAM — the dedicated memory a graphics card, or GPU, uses to hold models and data), 64GB of system memory (RAM)). This machine is the benchmark. Deciding a general minimum spec for other team machines comes *after* the PoC shows what's actually needed, not before.
- **PoC before optimization.** First goal: prove the pipeline (capture → transcribe → translate → speak) works end to end for one language pair, as a plain script, on Jerry's machine. No latency target, no packaging, no multi-language fan-out yet.
- **Packaging comes after the PoC works**, not alongside it.
- **Fan-out is not this project's problem to solve from scratch** — reuse LANStreamer's existing approach.
- **Target hardware is known, not universal.** This runs on a machine the team owns and brings to the event, not on an unknown venue PC. Minimum system requirements will be defined and enforced, same as any other professional software.
- **First target language decided: English → French for the first event, then Spanish and Portuguese.** Regional variant (e.g. fr_FR vs. African French; pt_PT vs. pt_BR) is decided per event, during the TTS voice audition (section 6a, validation step 3).
- **The target behavior is continuous, not turn-based.** A conference speaker doesn't pause for the interpreter: the system must continuously chunk incoming audio, translate, and stream TTS output while the speaker keeps talking. (The current test loop, `validation/scripts/live_loop.py`, is deliberately turn-based — it waits for a sentence to end before translating — which is fine for smoke-testing the stages, but the PoC pipeline is a streaming-design problem, and the sentence-boundary buffering requirement in section 8 has to coexist with it.)
- **Final delivery is a single installable desktop app** — `.exe` installer on Windows, `.dmg` on macOS — with all models bundled, so a team machine needs no internet, no Python, and no manual model downloads at the venue. Docker is a development/testing tool for headless server components only (see section 11, step 5); the interpretation pipeline itself stays native because containers have no access to audio devices.
- **Listeners hear it on a web page over the event LAN** — the LANStreamer pattern, unchanged. Listeners join a plain browser page on the same WiFi/LAN the interpretation PC is connected to; no app install, nothing leaves the local network. This project's output (per-language TTS audio) feeds into that existing listener path (section 3).
- **Multi-language events: preselected set plus auto-detection.** For an event, the operator preselects the working languages (say 3) on an interface/admin dashboard. The system then listens for *any* of the selected languages via automatic language detection (Whisper detects language natively; detection runs per utterance), translates whatever is spoken into all the *other* selected languages, and automatically disables the detected speaker's language as an output — a language is never echoed back at its own speakers. A speaker switching languages mid-event is a normal case, handled by per-utterance detection.

## 3. LANStreamer — what it does and how this project plugs into it

LANStreamer is Jerry's existing Node.js application. Extracted here so this document doesn't require reading the LANStreamer repo to make sense:

- **Capture**: it uses FFmpeg (a widely-used command-line tool for capturing, converting, and streaming audio/video) to pull audio from an input device — a physical microphone, a mixer, or a virtual audio cable (software like VB-Cable that makes one program's audio output appear as a selectable input device to another program).
- **Distribution**: each captured audio source is pushed as a separate stream into an Icecast server (an open-source audio streaming server; think internet radio — it serves audio over plain HTTP, playable in any browser or media player, no app install required). Icecast has a configurable limit on how many simultaneous sources/streams it can carry.
- **Control**: a web-based admin dashboard lets an operator start/stop each stream and pick which input device feeds it.
- **Listening**: listeners join via a plain browser page over the local WiFi — this is the "no installs needed" piece that's already solved.

**How the AI pipeline plugs in:** today, each language channel's audio source is a human interpreter's microphone. Going forward, each channel's audio source becomes our TTS output for that language instead. Two ways to wire that up:

- **(a) Virtual audio cable**: route each TTS output through a virtual audio cable so it simply appears to LANStreamer as another input device — no changes to LANStreamer itself. Simplest, fastest to get working.
- **(b) Direct feed**: have each TTS service push straight into its own FFmpeg → Icecast source, bypassing LANStreamer's device-capture layer entirely. More "native," but more work and some duplicated plumbing.

Recommendation: start with (a) for the PoC and early integration; revisit (b) only if the virtual-cable approach becomes a real bottleneck.

## 4. Target architecture (post-PoC)

```
Speaker mic
   │
   ▼
Streaming ASR + per-utterance language ID (multilingual checkpoint)
   │
   ▼
   ├──► MT (lang 1) ──► TTS (lang 1) ──► virtual audio cable ──┐
   ├──► MT (lang 2) ──► TTS (lang 2) ──► virtual audio cable ──┤──► LANStreamer
   └──► MT (lang N) ──► TTS (lang N) ──► virtual audio cable ──┘   (existing)
```

ASR runs once regardless of language count, detecting the spoken language per utterance (this needs a multilingual checkpoint — e.g. `small`, not `small.en` — see section 2's multi-language scope). The detected language is excluded from the targets for that utterance; MT and TTS then run once per remaining target language. Note the consequence for MT: translation pairs are **directional** — with N preselected languages, every language needs a pair to every other, so N languages means N×(N−1) MT models (3 languages → 6 pairs, not 3).

## 5. Tech choices (to validate during the PoC)

| Stage | Candidate | Why | Open question |
|---|---|---|---|
| ASR | faster-whisper / whisper.cpp | Mature, runs locally, good accuracy/speed tradeoff | Which model size holds up on the benchmark PC? (Also: does the target language need a different ASR model — see section 6a) |
| MT | **MarianMT / Opus-MT** (Helsinki-NLP's per-language-pair models) via CTranslate2, for the current targets (French, Spanish, Portuguese). **NLLB-200 (distilled 600M)** stays as the fallback for languages Opus-MT doesn't cover well — this is where the African-language path (section 6a) lives. | Opus-MT models are trained on one specific language pair each, so they outperform a 200-language generalist like NLLB on exactly these high-resource pairs — and they run on the same CTranslate2/int8/CPU stack, so it's not a new toolchain. NLLB's actual strength (broad coverage including lower-resource African languages) is the right reason to keep it as the fallback, not the primary. | Translation quality on short/partial segments still needs real testing either way. Regional variant per pair (fr_FR vs. African French, pt_PT vs. pt_BR) confirmed per event during the TTS voice audition. |
| TTS | Piper | Fast, lightweight, low resource use | Naturalness over a multi-hour event; **coverage of the target language may be the deciding factor, not naturalness — see section 6a** |
| Glossary/hotwords | Whisper prompt-biasing + MT terminology constraints | Both mechanisms already exist in the tools above | Best workflow for building the glossary (see section 7) |

**Reference project — [llm_sts](https://github.com/Gager-Git-life/llm_sts):** this is a real-time voice conversation system (you talk, an LLM replies, you hear the reply) rather than a translator, so its model choices don't transfer directly. Two patterns from it are worth adopting anyway:

- **Modular WebSocket services**: it runs ASR, the language-model stage, and TTS as separate small servers talking over WebSocket (a protocol for persistent, two-way streaming connections — better suited to continuous audio/text than a normal one-request-one-response HTTP call), coordinated by a main orchestrator script. That's a cleaner shape for our pipeline too — each stage (ASR, MT, TTS-per-language) as its own swappable service — rather than one large script, even at PoC scale.
- **VAD-based audio segmentation**: instead of feeding the ASR model fixed-length audio chunks, it uses voice activity detection (VAD — automatically detecting when someone is actually speaking versus silence) to decide segment boundaries. This is a better approach than a fixed chunk size and should replace it in our design.

One mismatch to flag: its TTS is Edge TTS — a free cloud API from Microsoft, not a local model. That won't work for us; a conference can't depend on a venue's internet connection for every word spoken, and it breaks the "local AI models" requirement. Piper (or another local TTS) stays the right call.

### Do we need to train any models?

Short answer: no, not for the PoC, and probably not for a good while after. Two different things are getting bundled together here worth separating:

- **Training a model from scratch** — needs huge datasets and compute, not practical for a small team, and not what gets you a smaller file.
- **What actually shrinks file size** is using an already-**distilled** model (a smaller model trained to mimic a larger one — this is what "NLLB-200-distilled-600M" already is) and/or **quantization** (storing the model's numbers at lower precision — e.g., int8 instead of float32 — which shrinks both file size and memory use, usually with a small, acceptable accuracy cost). Both of these are just picking the right pretrained model and settings, not training anything.
- **Fine-tuning** (further training a pretrained model on a smaller custom dataset — e.g., feeding it conference-specific audio or terminology) is a real option later if glossary-biasing alone isn't accurate enough, but it doesn't make files smaller by itself, and it requires collecting a dataset first. Worth keeping in mind for after the PoC, not before it. **This changes if the target language is low-resource — see section 6a below, where fine-tuning stops being optional and starts being the main lever.**

llm_sts backs this up in practice — every model it uses (Vosk, the LLM APIs, Edge TTS) is off-the-shelf, nothing trained from scratch.

**A note on Jerry's AMD hardware for the PoC:** the software ecosystem for GPU-accelerated AI on AMD cards runs on ROCm (AMD's GPU compute platform — the AMD equivalent of NVIDIA's CUDA). Several of the tools above — CTranslate2 in particular — only support CUDA or CPU, not ROCm, on their GPU path. Since the PoC's whole point is to prove the pipeline works, not to prove it's fast, the pragmatic move is to **run everything on CPU first**. That sidesteps GPU/driver compatibility entirely. Once the CPU version works, whisper.cpp's Vulkan backend (Vulkan is a cross-vendor graphics/compute interface, unlike CUDA/ROCm which are vendor-specific) is worth trying for GPU acceleration on the RX 6800 XT without needing ROCm specifically.

## 6a. Nigerian and African language considerations

This section exists because the risk profile of this whole project changes completely depending on which language(s) are actually being targeted. **The first event's languages are decided — English → French first, then Spanish and Portuguese (section 2), all served by the standard pipeline. This section matters for the African-language events beyond those, where the risk profile actually changes.**

The three pipeline stages do not carry the same risk for these languages:

- **ASR is the safest stage, but only if the source (spoken) language is English.** Whisper's English recognition is mature and well-tested. If the *source* speaker will actually be speaking Yoruba, Igbo, Hausa, or another Nigerian/African language, that's a different and much harder problem — mainstream Whisper coverage for these is weak. Meta's MMS project (Massively Multilingual Speech — a single effort covering over 1,000 languages, including many African ones) is worth evaluating specifically for ASR if the source language isn't English.
- **MT is the biggest risk for low-resource target languages.** NLLB-200 does include Yoruba, Igbo, Hausa, Swahili, and others — African language coverage was one of its actual design goals — but "included" isn't the same as "good." It was built for breadth across 200 languages, not depth on any one, and the distilled-600M version we picked for speed is the weakest version quality-wise. Short, conversational segments (exactly what live interpretation produces) are its weak point. Community-focused projects like Masakhane (a pan-African NLP research collective producing models and datasets specifically for African languages) are worth checking as an alternative or supplement for whichever language ends up as the target.
- **TTS is the real gap, and it's a coverage problem, not a quality problem.** Piper's voice list is thin for Nigerian/African languages. The realistic options if the target is Yoruba/Igbo/Hausa: Meta's **MMS-TTS** (has a Yoruba model, trained on Bible recordings — usable but not studio-quality), and newer community projects like **YarnGPT** (an open-source Yoruba/Igbo/Hausa TTS model built by a Nigerian developer, hosted on Hugging Face). Both are less mature and less battle-tested than Piper's mainstream-language voices, so budget real time to listen to samples and judge if the voice quality is acceptable — don't assume it will be.
- **Orthography matters.** Yoruba in particular uses tone marks and diacritics that plain-ASCII text handling can silently mangle. The glossary tool (section 7) and any text-processing step between MT and TTS need to handle Unicode properly, not just Latin letters — worth testing early rather than discovering it mid-PoC.

**Before writing PoC pipeline code, do this validation pass first (roughly a day, mostly no code):**

1. **Pick the first language pair** (source language → target language X). This single decision determines almost everything else in this section.
2. **MT go/no-go test**: take 20–30 real sentences from an actual talk or agenda, run them through NLLB-200-distilled-600M (a Hugging Face Space or local run both work), and have a native speaker judge the output. This either kills or confirms the biggest risk in hours, with zero pipeline code written.
3. **TTS voice audit**: check Piper's and MMS-TTS's (and YarnGPT's, if the target is Yoruba/Igbo/Hausa) actual voice samples for language X. If there's no usable voice, nothing downstream in the pipeline matters — this needs to be known before building anything else.
4. **CPU ASR benchmark on Jerry's machine** (the benchmark PC): run faster-whisper (int8, tiny/base/small sizes) against whisper.cpp with VAD-based chunking, and measure the real-time factor (how long processing takes relative to the audio's actual duration). Answers the open ASR question from section 5 in an afternoon.

Only after this validation pass should the PoC pipeline (section 8, step 1) actually start.

## 6b. Validation pass results (English → French)

The validation pass described above has now been run once, for the chosen first pair (English → French), on Jerry's benchmark PC, on CPU. Full results live in the repo: `validation/validation-report.md`, `validation/mt/mt_smoke_results.md`, `validation/tts/samples/`.

- **ASR**: faster-whisper, int8, VAD-chunked. Real-time factor (RTF — how long processing takes relative to the audio's actual duration; lower is faster) came out at tiny 0.03, base 0.05, small 0.15. `small` is recommended — still ~6.7x faster than real-time, and transcripts read cleanly on manual review. **whisper.cpp comparison was not completed** — the benchmark machine is missing a C++ build toolchain needed to compile it, and it turns out there's no shortcut around that: recent whisper.cpp releases don't ship prebuilt binaries (verified — this tracks with a known CI issue in the whisper.cpp project where Windows build artifacts weren't being packaged into releases). The only path is installing a C++ build toolchain (e.g. Visual Studio Build Tools with the C++ workload) and compiling it. faster-whisper's numbers are comfortable, so this isn't a PoC blocker — but the Vulkan GPU path (see the AMD hardware note in section 5) needs a whisper.cpp build either way; the toolchain task is tracked in `TODO.md`.
- **MT**: Opus-MT (English→French, CTranslate2, int8) — ~115ms/sentence average across a 20-sentence test drawn from real talk/agenda text. Names and numbers survived correctly (e.g. "Adebayo", "Emeka Okafor", "deux millions de naira"). **Status: CONDITIONAL, not a full pass.** Two grammar/word-order issues were flagged on the clean-sentence test ("une heure précises" — an agreement error; "va maintenant ministre" — garbled word order). A follow-up test on 15 deliberately truncated/mid-sentence fragments (`validation/mt/mt_smoke_partials_results.md`) then caught something more serious: on the fragment "Our target is to raise two million", Opus-MT produced «...deux millions de personnes» — it invented "of people" and closed the sentence on its own. Most other fragments dangled faithfully (no invention), but this one is exactly the failure mode that matters most for a live event: a confidently wrong number, spoken aloud as if it were correct. **Consequence, recorded in section 8: the PoC's MT stage must buffer input to sentence boundaries before translating — this is now a requirement, not a later optimization.** The gate before trusting MT at all: a native French speaker needs to review both tables (the 20 clean sentences and the 15 fragments), not just the flagged lines.
- **TTS**: all Piper candidate voices synthesize well above real-time (15–17x), confirming TTS won't be the pipeline's bottleneck. Three Metropolitan French voices are up for audition — `fr_FR-siwis-medium` (female), `fr_FR-tom-medium` (male), `fr_FR-upmc-medium` (female) — samples in `validation/tts/samples/`. Confirmed empirically: no African French Piper voice currently exists, so regional variant stays a per-event decision (section 6a).

**What's still open before the PoC script (delivery path step 1) starts is tracked in `TODO.md`** — native-speaker sign-off on both MT tables, and the voice pick.

## 6c. Implementation notes (live loop, 2026-09)

Findings made while building and hardening `validation/scripts/live_loop.py`. Recorded here so later stages don't re-learn them; state-of-play lives in `TODO.md`.

- **All model loading is local.** Models live in `validation/models/` (faster-whisper tiny/base/small, opus-mt-en-fr with its tokenizer, piper voices); nothing touches HuggingFace at runtime — verified with `HF_HUB_OFFLINE=1`. This layout is deliberately the same one the final installer will bundle (section 11, step 5).
- **`transformers` 5.x broke `AutoTokenizer` for Marian models** (fails both online and offline, unrelated to network). All scripts use `MarianTokenizer.from_pretrained(<local dir>)` explicitly. If a future `transformers` upgrade starts working again, that's a bonus — don't revert to `AutoTokenizer` as part of an upgrade without testing. Two known startup messages and what they mean: "*PyTorch was not found*" is informational (we only use the tokenizer, never a transformers model — installing 2.5GB of torch would gain nothing); "*Recommended: pip install sacremoses*" was acted on (installed, pinned) since it improves Moses-style preprocessing and silences the warning. Long-term cleanup option, not urgent: drop `transformers` entirely and read the sentencepiece files directly — one fewer big dependency in the final installer.
- **UTF-8 must be explicit on Windows at every boundary** — console (cp1252 default; the scripts reconfigure stdout), piper stdin, every `open()`. Accented French round-trips correctly; tone-marked scripts (Yoruba — section 6a) are the next stress test and are covered by unit test U5 in `docs/test-plan.md`.
- **Dependencies are pinned** in `requirements.txt` (Python 3.13, Windows venv). Model/binary downloads for a fresh clone are *not* scripted yet — tracked in `TODO.md`.
- **VAD passes are rate-limited** (at most twice per silence window) to avoid re-copying and re-scanning the whole audio buffer every tick; the cost is at most `silence/2` extra end-of-utterance latency.
- **Abbreviation periods are not sentence boundaries** (found in test M4: "Dr." was split off and its remainder sent to MT as a headless fragment — the exact truncation failure mode section 8 guards against). The sentence splitter now skips a known abbreviation list; any future splitter (F2) inherits this rule.
- **Test pass 2026-09-14** (M1–M10, R4 — log in `TEST-RESULT.md`): offline operation user-verified (M10); turn-based loop healthy; speakers-on echo is confirmed runaway feedback with filler hallucination (M7) — headphones now, virtual-cable routing at F7, plus a known-phrase hallucination filter (TODO). ASR mishears domain words like "naira" (M4) — first real evidence for the glossary feature (F5) and section 7.

## 7. Pre-event glossary feature

Before an event, users upload documents — the agenda, written speeches, attendee/speaker name lists, and so on. The system should:

- **Automatically extract** candidate terms and names using named-entity recognition (NER — a machine learning technique that picks out names, places, and organizations from text).
- **Allow manual review and editing** — a human can correct anything the automatic extraction got wrong, add terms it missed, or remove ones that aren't useful. Automatic extraction and manual correction are both required, not either/or.
- **Persist as an editable list per event**, feeding both the ASR's prompt-biasing (nudging transcription toward the right names/jargon) and the MT stage's terminology constraints (forcing a specific source→target mapping instead of leaving it to the model).
- **Handle non-Latin/diacritic text correctly** if the target language needs it (see section 6a) — this needs testing, not assuming.

## 8. Known failure modes and where they get addressed

| Issue | Addressed at PoC stage? | Notes |
|---|---|---|
| Partial-translation jitter | Yes — now a hard requirement, not just a design preference | Only translate finalized, sentence-boundary-complete segments, never live partials. Confirmed necessary, not just prudent: the fragment retest (section 6b) caught Opus-MT inventing content ("two million" → "two million *people*") when fed a mid-sentence fragment. Trade-off to revisit at the optimization phase: waiting for a full sentence boundary adds latency, and speakers who run long compound sentences could make that wait substantial — this needs a real answer before the ≤5 second target is meaningful. |
| Jargon/name misrecognition | Yes | Glossary/hotword biasing from day one |
| TTS naturalness | Partially | A/B test voices during the PoC, pick before locking in |
| Low-resource language MT/TTS quality | Yes — via the go/no-go test in 6a | Test before building, not after |
| Network reliability at venue | No — deferred | Operational concern, needs real venue testing later |
| Antivirus/SmartScreen blocks bundled binaries (FFmpeg etc.) at install | No — deferred | Known edge case for bundled-binary installers; handled as PRD F10 (detect + plain-language allow/trust guidance, code-signing eventually). Build during packaging, not before |
| No human correction window | No — deferred | Needs a monitor/kill-switch design once live |
| Single point of failure | No — deferred | Failover/backup plan, post-PoC |

## 9. Minimum system requirements (draft target, not final)

These are starting targets to validate once the PoC shows what's actually needed on Jerry's machine — his PC is the benchmark, not the finish line:

- **GPU**: aim for at least 8GB of VRAM once real-time optimization begins (Jerry's 16GB RX 6800 XT comfortably clears this; an 8GB card is a more realistic floor for other team laptops/machines).
- **CPU fallback**: a modern quad-core-or-better CPU with AVX2 support (an instruction set extension most CPUs from the last ~8 years have, which meaningfully speeds up this kind of model math) — e.g., Ryzen 5 3600 / Intel i5-9400 or newer — as the floor for a machine with no usable GPU.
- **RAM**: 16GB as a floor.

## 10. Audio output

**Icecast, for now.** It's what LANStreamer already uses, it's proven, and introducing a different streaming server during the PoC would add risk for no benefit. One thing to flag for later: Icecast typically buffers audio for a few seconds to keep the stream stable, which will conflict with a future sub-5-second latency target. Worth revisiting (WebRTC was flagged earlier as a lower-latency alternative) once we get to the optimization phase — not a PoC concern.

## 11. Delivery path

0. **Language validation pass** (section 6a): pick the first language pair, run the MT go/no-go test, audit TTS voice coverage, benchmark ASR on Jerry's machine. No pipeline code yet. **Run once for English → French — see section 6b for results and what's still outstanding before step 1 starts.** Repeat this pass for any new target language before building its pipeline.
1. **PoC**: single language pair, plain script, Jerry's AMD PC, CPU-first (avoids ROCm compatibility issues), no packaging.
2. **Multi-language**: extend to 2–5 target languages, still on the dev machine.
3. **Glossary ingestion**: document upload → automatic extraction (NER) → manual review/edit → feed into ASR/MT.
4. **Minimum spec**: define real numbers for team machines using PoC benchmarking data.
5. **Packaging**: bundle into a distributable app for team-owned hardware — avoid bundling a Python runtime; prefer native binaries (whisper.cpp, CTranslate2, Piper) that Electron can just shell out to. **Distribution strategy decided (2026-09):** the end product is a single installable desktop app — an `.exe` installer on Windows and a `.dmg` on macOS — with all models bundled inside, so a team machine needs no internet, no Python, and no manual model downloads. **The final exe assembles both projects:** the installer bundles the ls2 interpreter (native), the LANStreamer-style web server, FFmpeg/Icecast binaries, and the models. From the user's seat it is one piece of software — install → dashboard → START STREAMING → listener URL → listeners tap a language — and this does *not* require the code to live in one repo: ls2 (engine) and LANStreamer (distribution/UI logic to harvest) stay separate codebases, assembled into one app at packaging time. Docker is used *along the way* for what it's good at, not as the final packaging: server-side, headless components (e.g. a LANStreamer/Icecast distribution container) can be dockerised for repeatable testing and deployment. The interpretation pipeline itself (mic capture, ASR, TTS playback) **cannot** usefully live in a container on the event machine — Docker on Windows/macOS gives containers no access to audio input/output devices, which is the pipeline's lifeblood — so it stays a native process and gets bundled, models included, into the Electron-style installer. Practical consequence: keep model loading on local paths (already done — `validation/models/`, no HuggingFace access at runtime) so the same layout ships inside the installer.
6. **Integration with LANStreamer**: via virtual audio cable per language channel (see section 3).
7. **Latency optimization**: only after the above works, revisit the ≤5 second end-to-end target.
8. **Live-event hardening**: network fallback, human kill-switch, failover plan.

## 12. Open questions

*Design questions only. State-of-play items (has the native review happened, which voice is picked, is the toolchain installed) live in `TODO.md`.*

- How long does waiting for a full sentence boundary actually add in practice, for speakers with long or run-on sentences — this now matters because sentence-boundary buffering is a hard requirement (section 8), not optional. **Partially answered (2026-09-14, `validation/latency/2026-09-14-continuous-speech.md`):** for a speaker talking ~1 minute with only breath pauses, per-sentence end-to-end was ~3.2s (within the eventual ≤5s target) and — the important part — the buffer stitched breath-split fragments correctly with zero hallucinated completions. But playback backlog grows ~1s per second of continuous speech (listener lag reached 15s), so the remaining question is no longer "how long is the boundary wait" but "how does F2 compress output when falling behind" — TTS speedup, disfluency stripping, recency policy.
- Which regional variant (fr_FR vs. African French; pt_PT vs. pt_BR; Spanish variant) applies for a given event — decided during the TTS voice audition, not fixed in advance.
- Exact minimum-spec numbers — pending PoC benchmarking on Jerry's machine.
- Does the virtual-audio-cable integration hold up under real use, or does it eventually need the direct-feed approach (option b in section 3)?
- What's the actual latency cost of Icecast's buffering, measured, once we get to the optimization phase?
- *(Curiosity, not a priority — parked)* **Could listeners join over the internet?** Nothing in the listener path fundamentally requires the LAN — a browser plays an HTTP audio stream either way. The real obstacles are operational: the interpretation PC would need outbound bandwidth for N language streams (uplink at venues is usually the weak side), a reachable public endpoint (relaying through a cheap VPS or tunnel, since the venue machine won't have a public IP), authentication so a conference stream isn't world-readable, and accepting that the "no venue internet dependency" guarantee applies only to generation, not distribution — if the internet is down, remote listeners are down with it. Technically very doable later (Icecast can be relayed/mounted publicly as-is); deliberately out of scope until the local event case is solid.

## 13. F2 design — continuous streaming (draft for review, 2026-09)

Status: draft. Written after the measured baseline
(`validation/latency/2026-09-14-continuous-speech.md`); nothing here is built yet.
The baseline's two load-bearing facts: (1) compute is trivially cheap — all model
work for a sentence is ~0.1s, so F2 is *not* a speed problem; (2) playback
backlog grows ~1s per second of continuous speech (measured to 22s), so F2 *is*
a compression problem. Everything below follows from those two facts.

### 13.1 The reframed latency target

The ≤5s target can't mean "speaker's mouth to listener's ear for every word,
always" — that's mathematically impossible when output audio is as long as
input speech and the speaker never pauses. Human interpreters don't meet it
either; they fall behind and compress. Proposed split:

- **Steady-state target (≤5s):** time from a sentence being *complete* to its
  French audio *starting to play*, when the system is caught up. The baseline
  shows we're already at ~2.7–3.2s for this in the turn-based loop, without
  trying.
- **Catch-up rule (new):** when playback backlog exceeds a threshold (suggest
  15s to start, tunable), the system is formally "behind" and switches from
  verbatim mode to catch-up mode until the backlog drains below the threshold.
  What catch-up mode does is 13.4. The operator sees both states on the
  dashboard (F6) — this is the AI equivalent of an interpreter's booth light.

### 13.2 Pipeline shape

Stages connected by bounded queues, each stage a thread (processes/services
only if threads prove insufficient — the llm_sts pattern from section 5 is the
shape, not necessarily the deployment unit):

```
mic callback ──► capture buffer (lock, exists today)
                    │
                    ▼
              segmenter (VAD + endpoint, ~1.2s)          [keep]
                    │  utterance audio
                    ▼
              ASR worker (faster-whisper)                 [exists, ~10ms]
                    │  EN text fragments
                    ▼
              sentence stitcher (section 8 rule + abbrevs) [exists, tested]
                    │  complete sentences (+ max_hold flush)
                    ▼
              compression policy (13.4)                   [new — F2's core]
                    │  0..n sentences per tick
                    ▼
              MT worker (Opus-MT)                          [exists, ~80ms]
                    │  FR text
                    ▼
              TTS synth worker (piper subprocess pool)     [exists, ~0.2s]
                    │  PCM + metadata
                    ▼
              playback queue (bounded!)                    [exists, unbounded today]
```

Rules:
- **Every queue is bounded.** Today's playback queue is unbounded — that's the
  mechanism behind the 22s waits. Bounding forces an explicit policy instead of
  silent accumulation.
- **ASR never blocks on anything downstream.** Capture is never the bottleneck
  (baseline: ~10ms/utterance); it must stay that way so segment decisions are
  never distorted by backpressure.
- **One serialization point:** playback. Everything upstream can parallelize;
  audio out is strictly ordered per language.
- Where today's code already does the right thing (segmenter, stitcher, MT
  call, piper invocation), F2 is a refactor into this shape, not a rewrite.
  The pytest suite (U1, I1) is the safety net for the refactor.

### 13.3 What F2 does NOT change

- Sentence-boundary buffering before MT stays a hard requirement (section 8);
  the stitcher moves, its rule doesn't. Comma/clause-level partial translation
  is rejected on the hallucination evidence, permanently.
- One language pair first. Multi-language fan-out is F3 and builds on this
  pipeline (the MT/TTS column per language is a later fork below the stitcher).

### 13.4 Compression policy (the actual new engineering)

Ordered by cost — each is independently testable, add them cheapest first:

1. **TTS speedup (trivial):** Piper `--length_scale 0.9` (10% faster speech,
   barely audible). Buys 10% of the backlog permanently. Test: M-series manual
   check that the voice still sounds natural.
2. **Disfluency stripping (cheap, local, rule-based first):** remove fillers
   and repeats before MT — "so", "you know", "kind of", "I mean", stutters,
   duplicate phrase restarts. Buys 10–20% on improvised speech (the baseline
   transcripts are full of these), *and* improves MT input quality. Rules first
   (testable with U-series tests); an ML dep cleaner only if rules visibly
   mangle meaning.
3. **Catch-up mode (the real policy):** when backlog > threshold:
   - concatenate pending backlog sentences into one MT batch (fewer, longer
     outputs — removes per-sentence padding/lead-ins, modest win), and
   - if still losing ground, **drop the oldest un-played sentences** (keep the
     newest), with a soft audible cue (brief tone) so listeners know content
     was skipped — the interpreter's "falling behind, skipping" move. Dropping
     is why playback ordering tolerates gaps.
   - Return to verbatim when backlog < threshold/2 (hysteresis, so it doesn't
     flap).
4. **Summarization instead of drop (parked):** a local LLM summarizing the
   backlog would be the ideal catch-up, but it's a new model class, new
   hardware math, and new hallucination risk in exactly the worst place.
   Explicitly out of F2 scope; revisit only if dropping proves unacceptable.

Backlog threshold and drop behavior are *tunable knobs exposed in the admin
dashboard* (F6), not constants — different events will tolerate different
lag/fidelity trade-offs.

### 13.5 ASR accuracy under delivery speed (surfaced by the read-aloud baseline)

Fast spoken delivery degraded recognition ("shuttle buses" → "short-tool
bosses") while MT stayed correct on the same sentences as clean text. Before
F2 code starts, A/B two cheap knobs on the recorded read-aloud session:
`beam_size 1 → 5` and an `initial_prompt` seeded with event vocabulary.
Glossary (F5) is the structural fix and plugs into exactly that prompt slot.

### 13.6 Build order

1. Refactor `live_loop.py` into the 13.2 shape behind the existing pytest
   suite; no behavior change (verifiable: stats match the baseline's shape).
2. Bound the playback queue + expose backlog as a metric (log line first).
3. Add 13.4 items 1–2 (length_scale, disfluency rules) with tests.
4. Add 13.4 item 3 (catch-up mode) behind a flag, default off.
5. Re-run the two baseline scenarios (improvised + read-aloud) and compare
   against `validation/latency/2026-09-14-continuous-speech.md`.
