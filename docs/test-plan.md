# Test Plan

Covers the current state (validation scripts + `live_loop.py`) and the upcoming PoC pipeline (F2 continuous streaming, F3 multi-language). Manual test sections marked **[M]** require a human at the benchmark PC with mic + speakers; automated sections **[A]** run without audio hardware where possible.

Guiding rule borrowed from LANStreamer's robustness plan: every failure mode gets *how do you test for it* before *how do you mitigate it*. Test the boundaries (devices, model files, encodings), not just the happy path.

---

## 1. Automated tests [A]

No test infrastructure exists yet. Introduce `pytest` in the repo-root venv, tests under `tests/`. Pure-logic tests first (no models, no audio — fast, CI-able even on machines without the models); model-dependent tests behind a skip flag.

> **Status 2026-09-14:** built and green. `pytest` runs the unit suite (~2s, no models needed); `pytest -m models` adds the model-integration suite (~32s, needs `validation/models/` + piper binary). Config in `pytest.ini`; U3 (buffer state machine) and P1/P2 (soak/latency instrumentation) await F2 / a dedicated pass.

### 1.1 Unit — pure logic (build immediately)

| ID | Target | Test |
|---|---|---|
| U1 | `complete_sentences()` in `live_loop.py` | Terminal punct `.`, `!`, `?` each split; empty/whitespace input; no-punctuation text returns zero sentences and full tail; consecutive punctuation (`"Really?!"`); leading/trailing whitespace stripped. **First: extract the function into an importable module (`validation/scripts/` is fine) so tests don't import sounddevice/ctranslate2 at module load — currently `import live_loop` pulls heavy deps only inside functions, keep it that way.** |
| U2 | `voice_sample_rate()` | Missing `.onnx.json` → falls back to 22050; well-formed JSON → correct rate; malformed JSON → 22050 (no crash). |
| U3 | Sentence-boundary buffer state machine (when F2 lands) | Fragment carried across utterances correctly; `max_hold` expiry flushes exactly once; `pending_since` reset on flush; interleaved long/short sentences. |
| U4 | `translate()` token round-trip | Tokenizer encode → convert → translate-mock → decode preserves special-token stripping. Mock the `Translator` (ctranslate2 can't be installed everywhere). |
| U5 | Text encoding invariants | French output with accents/diacritics survives console-print helpers on Windows (cp1252 default) — the `reconfigure(utf-8)` guard exists; test it with `PYTHONIOENCODING` unset. Add Yoruba tone-mark strings now (design doc §6a orthography risk) so Unicode bugs surface before the African-language milestone. |

### 1.2 Integration — with models, no audio I/O (behind `--models-installed` skip)

| ID | Test |
|---|---|
| I1 | MT: run the 20 canonical `mt_smoke.py` sentences + 15 fragments through `translate()`; assert (a) no empty outputs, (b) the known-hallucination fragment "Our target is to raise two million" does **not** contain "personnes" when fed as a *complete sentence* ("...two million naira for the school project."), and (c) latency per sentence < 500ms on the benchmark PC (regression guard; validation measured ~115ms). |
| I2 | TTS: `synthesize("Bonjour.")` via the piper binary returns non-empty int16 PCM with even length (a common piper failure is silent truncation — odd byte counts crash `np.frombuffer`). |
| I3 | Offline run: with `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`, `live_loop.py --test-tts` must still load the tokenizer (catches the network-dependent `AutoTokenizer.from_pretrained` pitfall — see analysis). |
| I4 | Pre-flight checks: `live_loop.py` exits with a clear message when piper binary / MT dir / voice `.onnx` is missing or renamed (move them in a tmp fixture dir). |
| I5 | ASR determinism: fixed WAV (`validation/asr/test_audio_en.wav`) → transcription is stable across 3 runs (beam_size=1 should be deterministic; if not, that's a finding). |

### 1.3 Performance/soak (benchmark PC, no human)

| ID | Test |
|---|---|
| P1 | Feed a 10-minute concatenated audio file (repeat the test WAV) through the capture→VAD→ASR→buffer path *without* mic input (inject arrays directly). Assert: no unbounded memory growth (the `audio = np.concatenate` pattern is O(n²) over time — measure RSS), and the 30s force-flush fires. |
| P2 | Latency budget instrumentation: log per-utterance timestamps (utterance end → EN text → FR text → TTS queued → playback start). Even before the ≤5s target applies, the numbers must exist so F2 has a baseline. |

### 1.4 CI hygiene

- `pytest -m "not models"` must pass on any machine with just the venv (guard with markers).
- Lint: `ruff check validation/` — cheap, catches the unused-import/encoding class of bug early.
- Do **not** commit model binaries to make CI pass; CI tests logic only (models are gitignored by design).

---

## 2. Manual tests [M]

Run these yourself at the benchmark PC. Each row is one test — fill in the **Result** column (✅ pass / ❌ fail + what happened / ⚠️ partial) as you go, and use a row's ID when reporting. That gives us a verifiable record of what "works" means before anything gets marked done.

### ID prefixes (used throughout this plan)

| Prefix | Meaning | Run by |
|---|---|---|
| U | Unit test — pure logic, no models/audio | automated (pytest) |
| I | Integration test — real models, no audio hardware | automated, needs models installed |
| P | Performance/soak test — long runs, measurements | automated |
| M | Manual smoke — happy path by hand | you |
| R | Robustness — deliberate failure conditions by hand | you |
| Q | Quality gate — human judgement (native speaker, voice taste) | you + native speaker |
| X | Cross-project — ls2 ↔ LANStreamer integration | you |

### 2.1 Smoke — current loop (run first, ~10 min total)

| ID | Test | Why | Expected | Result |
|---|---|---|---|---|
| M1 | `.\live-loop.cmd --list-devices` | Confirm device enumeration + the wrapper script work | Device table printed, hint about `--input-device`/`--output-device` shown | ✅ Pass — full device table printed (103 devices incl. VB-Cables, BT headsets, WASAPI/WDM-KS). |
| M2 | `.\live-loop.cmd --test-tts` | Speakers + Piper + the Player queue work in isolation | Both French sentences heard, in order, within ~15s | ✅ Pass — both French sentences heard in order. |
| M3 | Full loop **with headphones**: speak 3 short English sentences, pausing at each end | The whole pipeline end-to-end after the 2026-09 changes (local models, MarianTokenizer, VAD rate-limit) | Each sentence printed as EN then FR, spoken in order, no overlap or cut-off; overall feel no laggier than before | ✅ Pass — EN→FR per sentence, in order; turn-based wait confirmed as designed. MT 72–113ms/sentence. |
| M4 | Say: "Dr. Adebayo raised two million naira for the school project" | Numbers + names are the documented hallucination class (validation §6b) | Name and number survive into the French output exactly once — no invented words | ⚠️ Partial — number survived, but two findings: (a) splitter broke 'Dr.' into its own fragment → FIXED (abbreviation-aware splitting); (b) ASR misheard 'naira' as NIRA/$/NIRR until repetition — ASR vocabulary gap, glossary/hotword (F5) territory, also worth trying `small`→`medium` or initial_prompt later. |
| M5 | Speak one long run-on sentence with no pause for >5s | Exercises the `max-hold` expiry path for unpunctuated fragments | `[hold expired — translating incomplete fragment]` prints, fragment translated, loop continues normally afterwards | ✅ Pass — long run-on split into sentences; second utterance's tail held then flushed. No hang. |
| M6 | Ctrl+C mid-speech, then Ctrl+C again mid-French-playback | Clean shutdown from any state | "Stopped." prints both times; no python.exe left in Task Manager; next run starts without "device in use" errors | ⚠️ Partial — clean stop mid-speech; but Ctrl+C during French playback raised a KeyboardInterrupt traceback in shutdown → FIXED (guarded player.join). |
| M7 | Full loop **without headphones** (speakers on) | Document the known echo mode (mic hears the French) | Loop doesn't crash or spiral into runaway feedback (each playback may trigger new utterances — note how bad it gets); recording this is the point, fixing is not | ❌ Confirmed failure mode (expected, unfixed by design) — speakers-on echo loop: each French playback re-enters mic and gets re-translated, spiraling into repeats and a filler hallucination ('I'll see you in the next video'). Headphones or virtual-cable routing (F7) are the real answers; hallucination filter (TODO) is the partial mitigation. |
| M8 | Unplug the USB mic (or disable it) mid-session while speaking | Device loss is the #1 field failure class (LANStreamer lesson) | Ideally: clear visible error and clean exit. Record what actually happens — even "hard crash" is a valid result, it becomes the robustness spec | ⚠️ Partial — mic loss ended the stream without a crash or traceback, but with no user-visible explanation either. Needs a 'device lost — reconnect/restart' message when we do the robustness pass. |
| M9 | `.\live-loop.cmd --input-device "DoesNotExist"` | Bad device names should fail fast, not hang | Clear error message quickly (a hang or stack trace is a finding, not a pass) | ❌ Fail (then FIXED) — ValueError traceback on bad device name; now exits with a clean message pointing to --list-devices. |
| M10 | Disconnect from the network (WiFi off / cable out), then run the full loop | Proves the offline-models fix — nothing should touch HuggingFace | Works identically to M3; this is the pass/fail for "no internet at the venue" | ✅ Pass — full loop worked with WiFi off. Offline-models requirement verified by the user, not just by the dev. |

### 2.2 Robustness matrix (LANStreamer lesson: devices are the #1 field failure)

| ID | Test | Why | Expected | Result |
|---|---|---|---|---|
| R1 | Start with default devices; then rerun with explicit `--input-device`/`--output-device` name substrings | Windows renames devices between sessions ("Microphone (2)"); substring matching must hold | Both runs capture/playback correctly | Skipped by tester (deemed technical). |
| R2 | Bluetooth headset: loop with mic + speakers on the same BT device | Classic Windows failure: BT mic forces a low sample-rate profile | Loop works, or fails with a clear message; if audio sounds wrong/8kHz-ish, record it — it's a known Windows/BT limitation, not our bug | Skipped by tester (deemed technical). |
| R3 | Output device that doesn't natively support the voice's rate (e.g. 22050 Hz voice on a 48 kHz-only device) | Verify sounddevice/PortAudio resamples rather than failing | French plays at normal pitch/speed; any failure mode is a finding | Skipped by tester (deemed technical). |
| R4 | Leave the loop listening for 1 hour, speak a sentence every few minutes | Memory leak / drift soak, human-survivable version of P1 | Responsive at minute 60 as at minute 1; check python.exe memory in Task Manager at start vs end and note the two numbers | ✅ Pass (shortened, ~35min not 60) — stable, no drift; memory numbers not recorded. Re-run full hour with Task Manager numbers before F2. |

### 2.3 Human quality gates (already tracked in TODO.md — keep them gated there)

| ID | Test | Why | Expected | Result |
|---|---|---|---|---|
| Q1 | Native French speaker reviews **all lines** of both MT tables (`validation/mt/mt_smoke_results.md`, `mt_smoke_partials_results.md`) | Blocks MT sign-off — the flagged lines alone aren't enough (TODO Blocking item) | Verdict per table: acceptable / needs-work with specifics; recorded in TODO | Pending — native speaker review. |
| Q2 | Audition the three voices on real conference sentences: `--voice fr_FR-siwis-medium`, `fr_FR-tom-medium`, `fr_FR-upmc-medium` | Blocks the voice pick (TODO Blocking item) | One voice chosen, noted in TODO | Pending — voice audition. |
| Q3 | *(When F2 lands)* A/B turn-based vs streaming on the same 5-min recorded talk; re-run the 15-fragment suite against the streaming segmenter's output | Sentence-boundary buffering quality must not regress under streaming | No new hallucinations; fragments handled at least as well as turn-based | |

### 2.4 Integration with LANStreamer (F7, when reached)

| ID | Test | Why | Expected | Result |
|---|---|---|---|---|
| X1 | Route Piper output → VB-Cable A → LANStreamer stream → listen on a phone browser over WiFi | First real test of the full listener experience (browser page on event LAN) | Audio arrives on the phone; note latency feel and any dropouts over 10 min | |
| X2 | Two language pairs simultaneously → two virtual cables → two LANStreamer streams | The multi-language fan-out shape (N MT + N TTS concurrent) | Both streams real-time and stable; note CPU load in Task Manager | |
| X3 | Restart LANStreamer admin mid-broadcast | Downstream restarts shouldn't kill the interpretation loop | Loop survives; streams reconnect or restart cleanly | |

---

## 3. Definition of done for the PoC (test view)

- All [A] unit tests green on a clean clone + venv (models absent).
- I1–I5 green on the benchmark PC.
- M1–M6, M9 pass; M7, M8, M10 have recorded actual behaviour and filed issues.
- Q1, Q2 signed off by humans.
- P2 latency numbers recorded in `validation/` for the F2 baseline.
