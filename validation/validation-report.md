# Validation Pass Report — 2026-09-13

Language pair: **English → French** (first target, per design doc section 2).
Machine: Jerry's PC (Ryzen 7 5800X, 64GB RAM, RX 6800 XT — all tests below ran **CPU-only**).
All commands run from repo root with `.venv/Scripts/python`.

## 1. MT smoke test — Opus-MT EN→FR (CTranslate2 int8, CPU)

- Model: `michaelfeil/ct2fast-opus-mt-en-fr` (~147MB on disk)
- 20 conference-style sentences (logistics, names, numbers, church register)
- **Avg latency: ~115 ms/sentence** (max 158 ms) — effectively free next to ASR
- Output table for native-speaker review: [`mt/mt_smoke_results.md`](mt/mt_smoke_results.md)

Quality notes (flagged, not blockers):

- Names/places/numbers survive cleanly: *Adebayo, Emeka Okafor, Kano, Jos, Lagos, deux millions de naira, quarante-deux pays*
- Occasional agreement/POS glitches: *«à une heure précises»*, *«va maintenant ministre»* (noun used as verb)
- Register appropriate for church/conference mix (*équipe de culte*, *dévotion*)

Verdict: **CONDITIONAL GO** — pending review of the full 20-sentence table by a native French speaker (human review, not spot-checks). Until then this reads as "no obvious blocker found," not "passed."

### 1a. Partial-fragment test (follow-up)

The smoke test above used clean, complete sentences — the live pipeline will feed VAD-chunked fragments instead (design doc section 8). A second test ([`mt/mt_smoke_partials_results.md`](mt/mt_smoke_partials_results.md)) ran 15 deliberately truncated / mid-sentence / short fragments:

- **Hallucinated completion (the real finding):** *"Our target is to raise two million"* → *«Notre objectif est de réunir deux millions **de personnes**.»* — the model invented "de personnes" and closed the sentence. On numbers/amounts this misleads listeners; the speaker's actual continuation arrives later as a *different* sentence.
- Most truncated fragments dangle faithfully (translated but left incomplete, mirroring the speaker) — acceptable.
- Mid-sentence starts often guess verb person/number correctly here, but that's luck, not a guarantee.
- One clause-cut silently dropped a trailing fragment ("from every" vanished).
- Latency unchanged (44–121 ms).

**PoC design implication:** "translate only finalized ASR segments" is not enough — VAD boundaries emit finalized *mid-sentence* segments. The MT stage needs a sentence-accumulation buffer (hold fragments until sentence-terminal punctuation or a silence threshold) so Opus-MT sees complete sentences. This goes into the PoC script as a requirement, not an optimization.

## 2. TTS voice audition — Piper French voices

Three Metropolitan French voices synthesized the same 8-sentence audition script (drawn from the actual MT smoke output, so you hear real pipeline text):

| Sample | Voice | RTF |
|---|---|---|
| `tts/samples/fr_FR-siwis-medium.wav` | siwis (female) | 0.06 |
| `tts/samples/fr_FR-tom-medium.wav` | tom (male) | 0.11 |
| `tts/samples/fr_FR-upmc-medium.wav` | upmc (female) | 0.06 |

All synth at 15–17x real-time on CPU — never the bottleneck.

**Action needed: listen and pick.** Note: all three are Metropolitan French (fr_FR); no African French Piper voice exists. If an event needs African French, that's a per-event voice audit (design doc section 6a) — possibly MMS-TTS or YarnGPT territory.

## 3. ASR benchmark — faster-whisper, CPU int8, VAD on, beam=1

90s of conference-style English (Piper-synthesized), full table in [`asr/asr_benchmark.md`](asr/asr_benchmark.md):

| Model | Load (s) | RTF | Words |
|---|---|---|---|
| tiny | 1.5 | **0.03** | 286 |
| base | 4.9 | **0.05** | 287 |
| small | 12.9 | **0.15** | 285 |

- RTF < 1.0 = faster than real-time. All three clear it by 7–30x.
- Word counts across sizes are within 2 words of each other and of the source — no degradation signal.
- Eyeball transcript from `small`: punctuation, capitalization, and content accurate (*"Good morning everyone, and a very warm welcome to this year's Leadership Summit."*).

**Recommendation: use `small`.** RTF 0.15 leaves the whole chain (ASR 0.15 + MT ~0.01 + TTS ~0.06 ≈ 0.22 combined) comfortably real-time even before any GPU path.

## Deferred

- **whisper.cpp comparison** — not done, and the cheap path doesn't exist: verified v1.9.4 ships **zero prebuilt binaries** (no release assets at all), and this box has no C++ toolchain (cmake/gcc/MSVC absent). Completing this leg requires installing Visual Studio Build Tools (C++ workload) — worth scheduling *before* the optimization phase regardless, since the planned Vulkan GPU path on the AMD card requires building whisper.cpp from source anyway. faster-whisper's numbers stand on their own meanwhile.
- **Variant selection** (fr_FR confirmed as the only current option; pt_PT vs pt_BR etc. at the per-event audition).

## Conclusion

Status by gate, stated accurately:

- **ASR: PASS** (speed, on clean synth audio; RTF 0.15 at `small`, transcript clean). Accuracy on real mic/noisy audio still untested — that's PoC work.
- **TTS: PASS on speed; voice choice pending audition** (the three samples above). No African French voice exists in Piper — per-event audit if needed.
- **MT: CONDITIONAL** — clean-sentence output looks strong and latency is negligible, but (a) no native-speaker has reviewed either table yet, and (b) the partial-fragment test found hallucinated completions on truncated input, so the PoC must buffer to sentence boundaries before MT.

Nothing here blocks starting the PoC script — but "validated" means: native-speaker sign-off on [`mt/mt_smoke_results.md`](mt/mt_smoke_results.md) + [`mt/mt_smoke_partials_results.md`](mt/mt_smoke_partials_results.md), and a voice picked from the audition samples. Both are human steps, not code.
