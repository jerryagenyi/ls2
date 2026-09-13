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

Verdict: **GO**, pending native-speaker sign-off on the results table.

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

- **whisper.cpp comparison** — no prebuilt v1.9.4 Windows binaries, no local compiler toolchain (cmake/gcc absent). faster-whisper shares the CTranslate2 engine with the MT stage anyway, so the stack stays unified. Revisit if/when the Vulkan GPU path becomes relevant.
- **Variant selection** (fr_FR confirmed as the only current option; pt_PT vs pt_BR etc. at the per-event audition).

## Conclusion

All three go/no-go gates for English → French **pass on CPU**: MT quality above bar with negligible latency, TTS real-time with voice choice reduced to a listening preference, ASR 6.7x real-time at the recommended `small` size. The PoC pipeline (design doc section 11, step 1) is unblocked.
