# Latency baseline — turn-based + continuous speech (2026-09-14)

Source: live session on the benchmark PC, full log held by Jerry (session summary
below). This is the measured baseline the F2 streaming design must beat / respect.
Setup: faster-whisper small int8 CPU, Opus-MT en-fr CTranslate2 int8, Piper
fr_FR-siwis-medium, `--silence 0.8 --max-hold 5.0` (defaults).

## Session stats

| Metric | Value |
|---|---|
| ASR (utterance→EN) | n=8, avg 11 ms, max 33 ms |
| MT (EN→FR) | n=18, avg 94 ms, max 287 ms |
| E2E (utterance end→FR queued) | n=15, avg 3,232 ms, max 3,742 ms |
| Working set | 554 MB start → 528 MB end (no leak) |
| Playback wait, turn-taking speech | ~0.5–0.7 s |
| Playback wait, ~1 min continuous speech | 4.8 → 7.0 → 10.5 → **15.4 s** (growing) |

## Findings

1. **Compute is not the bottleneck.** All model work for a sentence is ~0.1 s
   (ASR ~11 ms + MT ~94 ms). F2 latency design is not a compute problem.
2. **Sentence-boundary buffering held under adversarial input.** ~1 minute of
   continuous speech with only breath pauses: VAD split mid-sentence at breaths,
   the buffer stitched fragments across utterances, and MT only ever saw
   complete sentences. Zero hallucinated completions in the whole session.
   The design-doc section 8 requirement survived its first live stress test.
3. **The real continuous-speech problem is playback backlog, now measured.**
   French audio duration ≈ English speech duration, so without pauses the
   listener's lag grows ~1 s per second spoken (SPK waits climbing to 15 s).
   Human interpreters solve this by compressing. F2 candidate mitigations:
   - Faster TTS: Piper `length_scale` < 1.0 (mild speedup, cheap to test).
   - Disfluency stripping before MT ("so I kind of like kind of" → removed) —
     shortens French output AND improves MT quality.
   - Queue cap / recency policy when badly behind (drop or summarize oldest
     un-played sentences) — the interpreter's "falling behind, summarize" move.
   - NOT: partial-sentence translation on commas — violates the section 8
     hard requirement, rejected on the hallucination evidence.
4. **Endpoint detection costs ~1.2 s** (0.8 s silence threshold + ≤0.4 s VAD
   check cadence). Acceptable for turn-taking; in continuous speech it just
   segments, adds no user-visible latency.
5. **Memory stable** over the session — the buffer-trimming changes hold.

## Implication for the ≤5 s target

Per-sentence E2E is already ~3.2 s in this turn-based loop. The target is only
threatened by continuous-speech backlog (finding 3), which no amount of faster
models can fix — it needs compression. This should be the first thing F2
prototypes.

## Second session (same day): reading written speech aloud

Same mt_smoke sentences read from the page, conference-style, no deliberate
pauses at sentence ends. Stats: ASR n=8 avg 8 ms; MT n=24 avg 80 ms; E2E avg
2,677 ms max 3,967 ms; memory 557→531 MB. Playback waits reached **22.2 s** —
worse than improvised speech, since reading flows with fewer pauses.

**Cross-check against `mt_smoke_results.md` (the important result):** the same
sentences translated *correctly* as clean text ("shuttle buses" → «Navettes»,
Pastor Emeka Okafor, Kano) but came out garbled live ("short-tool bosses",
"Legos", "pastoral mecca or comfort", "Cano"). Same MT model both times — the
degradation is entirely ASR-side under fast spoken delivery. MT sign-off
evidence is unaffected; ASR accuracy under delivery speed is the new open
front. Cheap levers to test: `beam_size>1` in the live loop (bench didn't use
1), `initial_prompt` biasing; glossary (F5) is the structural fix.

Sentence buffer again stitched a cross-utterance fragment correctly
("school project in JOS" → «...projet scolaire à JOS»).
