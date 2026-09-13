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
Streaming ASR (source language)
   │
   ▼
   ├──► MT (lang 1) ──► TTS (lang 1) ──► virtual audio cable ──┐
   ├──► MT (lang 2) ──► TTS (lang 2) ──► virtual audio cable ──┤──► LANStreamer
   └──► MT (lang N) ──► TTS (lang N) ──► virtual audio cable ──┘   (existing)
```

ASR runs once regardless of language count; MT and TTS each run once per target language (2–5 parallel chains).

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

This section exists because the risk profile of this whole project changes completely depending on which language(s) are actually being targeted. **First targets are now decided — English → French, then Spanish and Portuguese (section 2) — so the PoC itself runs on low-risk, high-resource languages.** This section applies when Nigerian/African languages become event targets: re-run the risk assessment and validation pass below for each new target language.

The three pipeline stages do not carry the same risk for these languages:

- **ASR is the safest stage, but only if the source (spoken) language is English.** Whisper's English recognition is mature and well-tested. If the *source* speaker will actually be speaking Yoruba, Igbo, Hausa, or another Nigerian/African language, that's a different and much harder problem — mainstream Whisper coverage for these is weak. Meta's MMS project (Massively Multilingual Speech — a single effort covering over 1,000 languages, including many African ones) is worth evaluating specifically for ASR if the source language isn't English.
- **MT is the biggest risk for low-resource target languages.** NLLB-200 does include Yoruba, Igbo, Hausa, Swahili, and others — African language coverage was one of its actual design goals — but "included" isn't the same as "good." It was built for breadth across 200 languages, not depth on any one, and the distilled-600M version we picked for speed is the weakest version quality-wise. Short, conversational segments (exactly what live interpretation produces) are its weak point. Community-focused projects like Masakhane (a pan-African NLP research collective producing models and datasets specifically for African languages) are worth checking as an alternative or supplement for whichever language ends up as the target.
- **TTS is the real gap, and it's a coverage problem, not a quality problem.** Piper's voice list is thin for Nigerian/African languages. The realistic options if the target is Yoruba/Igbo/Hausa: Meta's **MMS-TTS** (has a Yoruba model, trained on Bible recordings — usable but not studio-quality), and newer community projects like **YarnGPT** (an open-source Yoruba/Igbo/Hausa TTS model built by a Nigerian developer, hosted on Hugging Face). Both are less mature and less battle-tested than Piper's mainstream-language voices, so budget real time to listen to samples and judge if the voice quality is acceptable — don't assume it will be.
- **Orthography matters.** Yoruba in particular uses tone marks and diacritics that plain-ASCII text handling can silently mangle. The glossary tool (section 7) and any text-processing step between MT and TTS need to handle Unicode properly, not just Latin letters — worth testing early rather than discovering it mid-PoC.

**Before writing PoC pipeline code, do this validation pass first (roughly a day, mostly no code):**

1. **Pick the first language pair** — done: English → French (section 2). Repeat per new target language.
2. **MT go/no-go test**: take 20–30 real sentences from an actual talk or agenda, run them through the pair's MT model (MarianMT/Opus-MT for French/Spanish/Portuguese; NLLB-200-distilled-600M for lower-resource languages), and have a native speaker judge the output. This either kills or confirms the biggest risk in hours, with zero pipeline code written.
3. **TTS voice audit**: check Piper's and MMS-TTS's (and YarnGPT's, if the target is Yoruba/Igbo/Hausa) actual voice samples for language X. If there's no usable voice, nothing downstream in the pipeline matters — this needs to be known before building anything else.
4. **CPU ASR benchmark on Jerry's machine** (the benchmark PC): run faster-whisper (int8, tiny/base/small sizes) against whisper.cpp with VAD-based chunking, and measure the real-time factor (how long processing takes relative to the audio's actual duration). Answers the open ASR question from section 5 in an afternoon.

Only after this validation pass should the PoC pipeline (section 8, step 1) actually start.

## 7. Pre-event glossary feature

Before an event, users upload documents — the agenda, written speeches, attendee/speaker name lists, and so on. The system should:

- **Automatically extract** candidate terms and names using named-entity recognition (NER — a machine learning technique that picks out names, places, and organizations from text).
- **Allow manual review and editing** — a human can correct anything the automatic extraction got wrong, add terms it missed, or remove ones that aren't useful. Automatic extraction and manual correction are both required, not either/or.
- **Persist as an editable list per event**, feeding both the ASR's prompt-biasing (nudging transcription toward the right names/jargon) and the MT stage's terminology constraints (forcing a specific source→target mapping instead of leaving it to the model).
- **Handle non-Latin/diacritic text correctly** if the target language needs it (see section 6a) — this needs testing, not assuming.

## 8. Known failure modes and where they get addressed

| Issue | Addressed at PoC stage? | Notes |
|---|---|---|
| Partial-translation jitter | Yes | Only translate finalized ASR segments, not live partials |
| Jargon/name misrecognition | Yes | Glossary/hotword biasing from day one |
| TTS naturalness | Partially | A/B test voices during the PoC, pick before locking in |
| Low-resource language MT/TTS quality | Yes — via the go/no-go test in 6a | Test before building, not after |
| Network reliability at venue | No — deferred | Operational concern, needs real venue testing later |
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

0. **Language validation pass** (section 6a): pick the first language pair, run the MT go/no-go test, audit TTS voice coverage, benchmark ASR on Jerry's machine. No pipeline code yet.
1. **PoC**: single language pair, plain script, Jerry's AMD PC, CPU-first (avoids ROCm compatibility issues), no packaging.
2. **Multi-language**: extend to 2–5 target languages, still on the dev machine.
3. **Glossary ingestion**: document upload → automatic extraction (NER) → manual review/edit → feed into ASR/MT.
4. **Minimum spec**: define real numbers for team machines using PoC benchmarking data.
5. **Packaging**: bundle into a distributable app for team-owned hardware — avoid bundling a Python runtime; prefer native binaries (whisper.cpp, CTranslate2, Piper) that Electron can just shell out to.
6. **Integration with LANStreamer**: via virtual audio cable per language channel (see section 3).
7. **Latency optimization**: only after the above works, revisit the ≤5 second end-to-end target.
8. **Live-event hardening**: network fallback, human kill-switch, failover plan.

## 12. Open questions

- Which regional variant (fr_FR vs. African French; pt_PT vs. pt_BR; Spanish variant) applies for a given event — decided during the TTS voice audition, not fixed in advance.
- Exact minimum-spec numbers — pending PoC benchmarking on Jerry's machine.
- Which TTS voice/engine wins the naturalness comparison, and does the target language even have a usable voice at all?
- Does the virtual-audio-cable integration hold up under real use, or does it eventually need the direct-feed approach (option b in section 3)?
- What's the actual latency cost of Icecast's buffering, measured, once we get to the optimization phase?
