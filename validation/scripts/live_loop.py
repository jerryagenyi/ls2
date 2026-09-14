"""Live mic -> ASR -> MT -> TTS loop: speak English, hear French.

Implements the F2 design (design doc section 13): stages connected by bounded
queues, incremental in-utterance ASR (section 13.7 recommendation 1), a
compression ladder (Tiers 0-3), and an optional catch-up mode. Also writes a
timestamped EN/FR transcript log (PRD F11 groundwork).

Stages: capture (callback) -> segmenter (VAD, main thread; cuts partial
chunks every --partial-sec during dense speech) -> ASR worker (incremental,
sentence-committed) -> MT worker (Tier 1 merge when behind) -> TTS synth
worker (Tier 0 dynamic speed-up when behind) -> bounded playback queue ->
Player. Sentence-boundary buffering before MT remains a hard requirement
(design doc section 8): the incremental transcriber only commits sentences,
never partials.

Wear headphones if you can — otherwise the mic hears the French output
and tries to transcribe it (confirmed runaway feedback, test M7).

Usage (from repo root, venv active):
  python validation/scripts/live_loop.py                  # siwis voice
  python validation/scripts/live_loop.py --voice fr_FR-tom-medium
  python validation/scripts/live_loop.py --list-devices   # pick mic/speakers
  python validation/scripts/live_loop.py --test-tts       # speakers-only check
"""
import argparse
import datetime
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)
PIPER = os.path.join(ROOT, "bin", "piper", "piper.exe")
VOICES_DIR = os.path.join(ROOT, "models", "piper_voices")
MT_DIR = os.path.join(ROOT, "models", "opus-mt-en-fr")

SR = 16000  # capture/ASR sample rate

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def voice_sample_rate(onnx_path: str) -> int:
    try:
        with open(onnx_path + ".json", encoding="utf-8") as f:
            return int(json.load(f)["audio"]["sample_rate"])
    except Exception:
        return 22050


def synthesize(text: str, voice_onnx: str, length_scale: float = 1.0):
    """French text -> int16 mono PCM via the piper binary (--output_raw)."""
    proc = subprocess.run(
        [PIPER, "--model", voice_onnx, "--output_raw", "-q",
         "--length_scale", str(length_scale)],
        input=(text + "\n").encode("utf-8"),
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        print(f"[tts error] {proc.stderr.decode(errors='replace')[:200]}")
        return None
    return np.frombuffer(proc.stdout, dtype=np.int16)


# Titles/abbreviations whose period must NOT end a sentence (test M4: "Dr."
# was split off and its remainder translated as a headless fragment).
_ABBREV = {"dr", "mr", "mrs", "ms", "prof", "sr", "jr", "st", "vs", "etc",
           "no", "fig", "e.g", "i.e", "approx", "dept", "est", "inc", "ltd"}

# Filler phrases stripped before MT (design doc 13.4 item 2). Deliberately
# conservative: only phrases that are never load-bearing. "like" and "so" are
# NOT stripped — they carry meaning too often.
_FILLER = re.compile(
    r"\b(?:um+|uh+|erm+|hmm+|you know|i mean|kind of|sort of)\b[,;]?",
    re.IGNORECASE,
)


def strip_disfluencies(text: str) -> str:
    """Remove spoken fillers before MT: shortens output AND cleans MT input."""
    return re.sub(r"\s{2,}", " ", _FILLER.sub(" ", text)).strip()


def complete_sentences(text: str):
    """Split into (complete sentences, leftover tail lacking terminal punct)."""
    sentences, cur = [], []
    for ch in text:
        cur.append(ch)
        if ch in ".!?":
            so_far = "".join(cur)
            body = so_far[:-1]
            if not any(c.isalnum() for c in body):
                # bare/stacked punctuation ("?!", ". . ."): attach to the
                # previous sentence rather than starting a junk fragment
                if sentences:
                    sentences[-1] += ch
                    cur = []
                    continue
                continue
            last_word = body.rstrip(")").split()[-1] if body.split() else ""
            if last_word.lower().rstrip(".") in _ABBREV:
                continue  # abbreviation period, not a sentence end
            s = so_far.strip()
            if s:
                sentences.append(s)
            cur = []
    return sentences, "".join(cur).strip()


def rss_mb():
    """Process working-set size in MB (P1 memory watch); None if unavailable."""
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (n, ctypes.c_size_t) for n in (
                    "PeakWorkingSetSize", "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                    "PagefileUsage", "PeakPagefileUsage")]

        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        if psapi.GetProcessMemoryInfo(
                k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
            return pmc.WorkingSetSize / 1e6
    except Exception:
        pass
    return None


class TranscriptLog:
    """PRD F11 groundwork: append EN/FR/dropped text as JSONL lines."""

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def log(self, kind: str, text: str):
        rec = {"t": datetime.datetime.now().isoformat(timespec="seconds"),
               "kind": kind, "text": text}
        line = json.dumps(rec, ensure_ascii=False)
        with self.lock, open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


class IncrementalASR:
    """Streaming ASR over one continuous-speech session (design 13.7 rec 1).

    Audio chunks accumulate; each feed() re-transcribes only the un-committed
    tail. Sentences become committed (audio offset advances past the segment
    that closed them) the moment they are complete — so in dense speech,
    translation starts after --partial-sec, not after the 30s force-flush.
    The unfinished tail is re-transcribed next feed: Whisper may change its
    mind about the tail, but committed sentences never change, and the
    section-8 rule (only complete sentences reach MT) is preserved.
    """

    def __init__(self, transcribe, stats=None):
        self._transcribe = transcribe  # (audio) -> list of (text, end_s)
        self.stats = stats
        self.buf = np.empty(0, dtype=np.float32)
        self.committed = 0  # sample offset into buf: transcription is final

    def feed(self, chunk: np.ndarray, final: bool = False):
        """Returns (new_complete_sentences, tail_text, asr_ms)."""
        self.buf = (np.concatenate([self.buf, chunk]) if self.buf.size
                    else chunk)
        t0 = time.perf_counter()
        segs = self._transcribe(self.buf[self.committed:])
        asr_ms = (time.perf_counter() - t0) * 1000
        if self.stats is not None and segs:
            self.stats.note("asr_ms", asr_ms)

        texts, ends = [], []
        for text, end_s in segs:
            t = text.strip()
            if t:
                texts.append(t)
                ends.append(self.committed + min(int(end_s * SR), self.buf.size))
        full = " ".join(texts)
        sentences, tail = complete_sentences(full)

        # Advance commitment past the audio backing the last complete
        # sentence: include whole segments whose text fits inside the
        # emitted sentences, plus a small safety margin.
        if sentences:
            consumed = " ".join(sentences)
            cum, new_committed = 0, self.committed
            for t, e in zip(texts, ends):
                if cum + len(t) + 1 <= len(consumed) + 1:
                    cum += len(t) + 1
                    new_committed = e
            self.committed = max(0, min(new_committed, self.buf.size) - SR // 5)
            # drop fully-committed audio from the front (keeps memory flat)
            self.buf = self.buf[self.committed:]
            self.committed = 0
        return sentences, tail, asr_ms


class Stats:
    """P2 latency instrumentation: per-utterance stage timings + summary."""

    def __init__(self):
        self.asr_ms = []    # transcription pass duration
        self.mt_ms = []     # EN sentence -> FR text
        self.e2e_ms = []    # chunk end -> FR queued for playback
        self.dropped = 0    # sentences dropped by catch-up mode
        self.backlog_max_s = 0.0

    def note(self, series, value):
        getattr(self, series).append(value)

    def summary(self) -> str:
        def line(name, xs):
            if not xs:
                return f"  {name}: n/a"
            return (f"  {name}: n={len(xs)} avg={sum(xs)/len(xs):.0f}ms "
                    f"max={max(xs):.0f}ms")
        return "\n".join([
            "Stats (this session):",
            line("ASR (per pass)", self.asr_ms),
            line("MT  (EN->FR)", self.mt_ms),
            line("E2E (chunk end->FR queued)", self.e2e_ms),
            f"  dropped (catch-up): {self.dropped}",
            f"  playback backlog max: {self.backlog_max_s:.1f}s",
        ])


class Backlog:
    """Seconds of synthesized-but-unplayed audio (design doc 13.4)."""

    def __init__(self):
        self._s = 0.0
        self.lock = threading.Lock()

    def add(self, dur):
        with self.lock:
            self._s += dur

    def sub(self, dur):
        with self.lock:
            self._s -= dur

    def seconds(self):
        with self.lock:
            return self._s


class Player(threading.Thread):
    """Drains the bounded playback queue in order; capture never blocks.

    `q` IS the pipeline's bounded playback queue (design doc 13.2) — the TTS
    worker puts PCM into it directly, and catch-up mode drops from it. The
    sentinel None travels the same queue at shutdown.
    """

    def __init__(self, voice_onnx: str, device=None, backlog=None, stats=None,
                 qsize=16):
        super().__init__(daemon=True)
        self.voice_onnx = voice_onnx
        self.device = device
        self.sample_rate = voice_sample_rate(voice_onnx)
        self.q: "queue.Queue[tuple]" = queue.Queue(maxsize=qsize)
        self.backlog = backlog
        self.stats = stats

    def run(self):
        import sounddevice as sd

        with sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            device=self.device,
        ) as stream:
            while True:
                item = self.q.get()
                if item is None:
                    break
                pcm, queued_at, dur, _text = item
                if self.backlog is not None and self.stats is not None:
                    self.stats.backlog_max_s = max(
                        self.stats.backlog_max_s, self.backlog.seconds())
                wait_ms = (time.perf_counter() - queued_at) * 1000
                stream.write(pcm)
                print(f"SPK [wait {wait_ms:4.0f} ms, {dur * 1000:4.0f} ms audio]")
                if self.backlog is not None:
                    self.backlog.sub(dur)


def list_devices():
    import sounddevice as sd

    print(sd.query_devices())
    print("\nPass a name substring: --input-device 'Headset' --output-device 'Speakers'")


def test_tts(voice: str):
    player = Player(os.path.join(VOICES_DIR, voice + ".onnx"))
    player.start()
    pcm = synthesize("Bonjour. Ceci est un test du système de synthèse vocale.",
                     player.voice_onnx)
    if pcm is None or not pcm.size:
        sys.exit("Piper synthesis failed — check the piper binary/voice.")
    player.q.put((pcm, time.perf_counter(), pcm.size / player.sample_rate, "test"))
    player.q.put(None)
    player.join(timeout=15)
    print("If you heard both sentences, speakers + Piper are working.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--voice", default="fr_FR-siwis-medium",
                    help="Piper voice name (default fr_FR-siwis-medium)")
    ap.add_argument("--asr-model", default="small",
                    help="faster-whisper size: tiny/base/small (default small)")
    ap.add_argument("--silence", type=float, default=0.8,
                    help="seconds of silence that end an utterance (default 0.8)")
    ap.add_argument("--partial-sec", type=float, default=6.0,
                    help="during unbroken speech, transcribe incrementally "
                         "every this many seconds instead of waiting for a "
                         "pause (default 6)")
    ap.add_argument("--max-hold", type=float, default=5.0,
                    help="seconds an unpunctuated fragment is held before "
                         "translating it as-is (default 5.0)")
    ap.add_argument("--length-scale", type=float, default=0.9,
                    help="Piper speech rate: <1 faster, 1.0 natural (default 0.9)")
    ap.add_argument("--no-strip", action="store_true",
                    help="disable disfluency stripping before MT")
    ap.add_argument("--catchup", action="store_true",
                    help="enable catch-up mode (design 13.7 ladder: Tier 0 "
                         "dynamic TTS speed-up + Tier 1 MT merge + Tier 3 drop "
                         "when badly behind; default off)")
    ap.add_argument("--backlog-threshold", type=float, default=15.0,
                    help="seconds of backlog that triggers catch-up (default 15)")
    ap.add_argument("--playback-queue", type=int, default=16,
                    help="max sentences waiting for playback (default 16)")
    ap.add_argument("--transcript-dir", default=os.path.join(REPO, "logs"),
                    help="directory for the JSONL transcript log (F11)")
    ap.add_argument("--input-device", default=None)
    ap.add_argument("--output-device", default=None)
    ap.add_argument("--list-devices", action="store_true")
    ap.add_argument("--test-tts", action="store_true")
    args = ap.parse_args()

    if args.list_devices:
        list_devices()
        return
    if args.test_tts:
        test_tts(args.voice)
        return

    for path, what in [(PIPER, "piper binary"), (MT_DIR, "Opus-MT model dir")]:
        if not os.path.exists(path):
            sys.exit(f"Missing {what}: {path}")
    voice_onnx = os.path.join(VOICES_DIR, args.voice + ".onnx")
    if not os.path.exists(voice_onnx):
        sys.exit(f"Unknown voice: {voice_onnx} (see {VOICES_DIR})")

    import sounddevice as sd
    import ctranslate2
    from faster_whisper import WhisperModel
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    from transformers.models.marian.tokenization_marian import MarianTokenizer

    print(f"Loading models (ASR={args.asr_model}, MT=opus-mt-en-fr, voice={args.voice})...")
    asr_dir = os.path.join(ROOT, "models", f"faster-whisper-{args.asr_model}")
    if not os.path.exists(asr_dir):
        sys.exit(f"ASR model not downloaded locally: {asr_dir}")
    asr = WhisperModel(asr_dir, device="cpu", compute_type="int8")
    tokenizer = MarianTokenizer.from_pretrained(MT_DIR)
    translator = ctranslate2.Translator(MT_DIR, device="cpu", compute_type="int8")

    def translate(text: str) -> str:
        tokens = tokenizer.convert_ids_to_tokens(tokenizer.encode(text))
        result = translator.translate_batch([tokens], beam_size=4)
        hyp_ids = tokenizer.convert_tokens_to_ids(result[0].hypotheses[0])
        return tokenizer.decode(hyp_ids, skip_special_tokens=True)

    translate("Warmup.")

    def transcribe(audio):
        segments, _ = asr.transcribe(audio, language="en", beam_size=1)
        return [(s.text, s.end) for s in segments]

    stats = Stats()
    backlog = Backlog()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    tlog = TranscriptLog(os.path.join(args.transcript_dir, f"transcript-{stamp}.jsonl"))
    print(f"Transcript log: {tlog.path}")
    rss0 = rss_mb()
    if rss0 is not None:
        print(f"[mem] working set at start: {rss0:.0f} MB")
    last_rss_log = time.time()

    # ---- pipeline queues (design doc 13.2) ----
    utterance_q: "queue.Queue[tuple]" = queue.Queue()   # (audio, final?)
    mt_q: "queue.Queue[tuple]" = queue.Queue()          # (sentence, chunk_end)
    synth_q: "queue.Queue[tuple]" = queue.Queue()       # (fr_text, at)

    player = Player(voice_onnx, device=args.output_device,
                    backlog=backlog, stats=stats, qsize=args.playback_queue)
    playback_q = player.q  # the bounded playback queue the Player drains
    player.start()

    stop = threading.Event()

    def behind():
        """True when catch-up tiers should be active (hysteresis-free check;
        the drop loop in tts_worker applies the threshold/2 hysteresis)."""
        return args.catchup and backlog.seconds() > args.backlog_threshold * 0.5

    def mt_worker():
        """EN sentence -> FR text; Tier 1: merge queued sentences when behind."""
        while not stop.is_set():
            try:
                sentence, chunk_end = mt_q.get(timeout=0.25)
            except queue.Empty:
                continue
            batch = [sentence]
            if behind():
                while len(batch) < 3:
                    try:
                        s2, _e = mt_q.get_nowait()
                    except queue.Empty:
                        break
                    batch.append(s2)
                if len(batch) > 1:
                    print(f"[catch-up tier 1] merging {len(batch)} sentences")
            text = " ".join(batch)
            t0 = time.perf_counter()
            fr = translate(text)
            stats.note("mt_ms", (time.perf_counter() - t0) * 1000)
            if chunk_end is not None:
                stats.note("e2e_ms", (time.perf_counter() - chunk_end) * 1000)
            print(f"FR  [{(time.perf_counter() - t0) * 1000:5.0f} ms]  {fr}")
            tlog.log("fr", fr)
            synth_q.put((fr, time.perf_counter()))

    def tts_worker():
        """FR text -> PCM into the bounded playback queue (13.4 policy)."""
        while not stop.is_set():
            try:
                text, at = synth_q.get(timeout=0.25)
            except queue.Empty:
                continue
            # Tier 0: speak a notch faster while behind
            ls = args.length_scale
            if behind():
                ls = max(0.7, ls - 0.1)
            pcm = synthesize(text, voice_onnx, ls)
            if pcm is None or not pcm.size:
                continue
            dur = pcm.size / player.sample_rate
            backlog.add(dur)
            if (args.catchup and backlog.seconds() > args.backlog_threshold):
                # Tier 3 (last resort): drop oldest un-played sentence(s)
                while backlog.seconds() > args.backlog_threshold * 0.5:
                    try:
                        _, _, old_dur, old_text = playback_q.get_nowait()
                    except queue.Empty:
                        break
                    backlog.sub(old_dur)
                    stats.dropped += 1
                    print(f"[catch-up] dropped: {old_text}")
                    tlog.log("dropped", old_text)
            playback_q.put((pcm, at, dur, text))  # blocks when full (backpressure)

    def asr_worker():
        """Audio -> committed sentences via IncrementalASR; stitcher (sec 8)."""
        inc = None                     # active continuous-speech session
        hold_pending, hold_since = "", None  # text-level pending between sessions

        def flush_hold():
            nonlocal hold_pending, hold_since
            if hold_pending:
                print("[hold expired — translating incomplete fragment]")
                tlog.log("en", hold_pending)
                mt_q.put((hold_pending, None))
                hold_pending, hold_since = "", None

        while not stop.is_set():
            try:
                utt, final = utterance_q.get(timeout=0.25)
            except queue.Empty:
                if hold_pending and time.time() - hold_since > args.max_hold:
                    flush_hold()
                continue
            chunk_end = time.perf_counter()
            if inc is None:
                inc = IncrementalASR(transcribe, stats)
            sentences, tail, asr_ms = inc.feed(utt, final=final)
            if sentences:
                print(f"\nEN  [{asr_ms:5.0f} ms]  " + " ".join(sentences))
                tlog.log("en", " ".join(sentences))
                for s in sentences:
                    s = s if args.no_strip else strip_disfluencies(s)
                    mt_q.put((s, chunk_end))
            if final:
                if tail:
                    hold_pending = f"{hold_pending} {tail}".strip()
                    hold_since = time.time()
                inc = None  # session over; next speech starts fresh

    for target in (mt_worker, tts_worker, asr_worker):
        threading.Thread(target=target, daemon=True).start()

    chunks = []
    lock = threading.Lock()

    def on_audio(indata, frames, t, status):
        with lock:
            chunks.append(indata[:, 0].copy())

    vad_opts = VadOptions(
        min_silence_duration_ms=int(args.silence * 1000),
        speech_pad_ms=100,
    )

    audio = np.empty(0, dtype=np.float32)
    unchecked = 0         # samples buffered since the last VAD pass

    try:
        with sd.InputStream(
            samplerate=SR, channels=1, dtype="float32",
            callback=on_audio, device=args.input_device,
        ):
            print("Listening. Speak English, pause at sentence ends. Ctrl+C stops.")
            while True:
                time.sleep(0.1)
                if time.time() - last_rss_log > 300:  # P1 memory watch, 5-min cadence
                    last_rss_log = time.time()
                    rss = rss_mb()
                    if rss is not None:
                        print(f"[mem] working set: {rss:.0f} MB")
                with lock:
                    new, chunks[:] = chunks[:], []
                if new:
                    audio = np.concatenate([audio] + new) if audio.size else np.concatenate(new)
                    unchecked += sum(c.size for c in new)

                # VAD pass at most twice per silence window: re-copying and
                # re-scanning the whole buffer every 0.1s tick is wasted work,
                # and this caps added end-of-utterance latency at silence/2.
                if unchecked < SR * args.silence / 2:
                    continue
                unchecked = 0

                ts = get_speech_timestamps(audio, vad_opts)
                if not ts:
                    if audio.size > SR * 5:  # long pure silence: keep last 1s
                        audio = audio[-SR:]
                    continue

                last_end = int(ts[-1]["end"])
                trailing = (audio.size - last_end) / SR
                speech_dur = (last_end - int(ts[0]["start"])) / SR
                if trailing >= args.silence and speech_dur >= 0.25:
                    # endpoint: close the utterance, final=True
                    utt, audio = audio[:last_end], audio[last_end:]
                    utterance_q.put((utt, True))
                elif audio.size > SR * args.partial_sec:
                    # dense speech, no endpoint in sight: cut a partial chunk
                    # (keep 0.5s tail in the buffer; IncrementalASR will
                    # re-transcribe whatever it hasn't committed anyway)
                    cut = audio.size - SR // 2
                    utterance_q.put((audio[:cut], False))
                    audio = audio[cut:]
    except ValueError as e:
        # e.g. nonexistent --input-device name (test M9): fail clean, not a traceback
        stop.set()
        sys.exit(f"Audio device error: {e}\n"
                 "Run with --list-devices and pass a name substring that exists.")
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        try:
            player.q.put(None, timeout=2)  # may be full if badly backlogged
        except queue.Full:
            pass  # stop is set; Player exits after the current write anyway
        try:
            player.join(timeout=10)
        except KeyboardInterrupt:
            pass  # second Ctrl+C during playback shutdown (test M6) — just exit
        print("\n" + stats.summary())
        rss = rss_mb()
        if rss is not None and rss0 is not None:
            print(f"[mem] working set: start {rss0:.0f} MB -> end {rss:.0f} MB")
        print("\nStopped.")


if __name__ == "__main__":
    main()
