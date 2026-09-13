"""Live mic -> ASR -> MT -> TTS loop: speak English, hear French.

Local smoke-test harness, not the step-1 PoC pipeline. Implements the
section-8 requirement found in validation: fragments are buffered to
sentence boundaries (terminal punctuation, or a hold timeout) before
MT, so Opus-MT never sees a truncated fragment it might "complete"
(the "two million -> deux millions de personnes" failure mode).

Stages and settings come from the validation pass (validation-report.md):
ASR = faster-whisper int8 CPU (default small, RTF 0.15); MT = Opus-MT
en-fr via CTranslate2 int8 (~115ms/sentence); TTS = the same Piper
voices auditioned in validation/tts/samples.

Wear headphones if you can — otherwise the mic hears the French output
and tries to transcribe it.

Usage (from repo root, venv active):
  python validation/scripts/live_loop.py                  # siwis voice
  python validation/scripts/live_loop.py --voice fr_FR-tom-medium
  python validation/scripts/live_loop.py --list-devices   # pick mic/speakers
  python validation/scripts/live_loop.py --test-tts       # speakers-only check
"""
import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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


def synthesize(text: str, voice_onnx: str):
    """French text -> int16 mono PCM via the piper binary (--output_raw)."""
    proc = subprocess.run(
        [PIPER, "--model", voice_onnx, "--output_raw", "-q"],
        input=(text + "\n").encode("utf-8"),
        capture_output=True,
    )
    if proc.returncode != 0 or not proc.stdout:
        print(f"[tts error] {proc.stderr.decode(errors='replace')[:200]}")
        return None
    return np.frombuffer(proc.stdout, dtype=np.int16)


class Player(threading.Thread):
    """Single worker so French sentences play in order, capture never blocks."""

    def __init__(self, voice_onnx: str, device=None):
        super().__init__(daemon=True)
        self.voice_onnx = voice_onnx
        self.device = device
        self.sample_rate = voice_sample_rate(voice_onnx)
        self.q: "queue.Queue[str]" = queue.Queue()

    def run(self):
        import sounddevice as sd

        with sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            device=self.device,
        ) as stream:
            while True:
                text = self.q.get()
                if text is None:
                    break
                pcm = synthesize(text, self.voice_onnx)
                if pcm is not None and pcm.size:
                    stream.write(pcm)


def complete_sentences(text: str):
    """Split into (complete sentences, leftover tail lacking terminal punct)."""
    sentences, cur = [], []
    for ch in text:
        cur.append(ch)
        if ch in ".!?":
            s = "".join(cur).strip()
            if s:
                sentences.append(s)
            cur = []
    return sentences, "".join(cur).strip()


def list_devices():
    import sounddevice as sd

    print(sd.query_devices())
    print("\nPass a name substring: --input-device 'Headset' --output-device 'Speakers'")


def test_tts(voice: str):
    player = Player(os.path.join(VOICES_DIR, voice + ".onnx"))
    player.start()
    player.q.put("Bonjour. Ceci est un test du système de synthèse vocale.")
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
    ap.add_argument("--max-hold", type=float, default=5.0,
                    help="seconds an unpunctuated fragment is held before "
                         "translating it as-is (default 5.0)")
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
    from transformers import AutoTokenizer

    print(f"Loading models (ASR={args.asr_model}, MT=opus-mt-en-fr, voice={args.voice})...")
    asr = WhisperModel(args.asr_model, device="cpu", compute_type="int8")
    tokenizer = AutoTokenizer.from_pretrained("Helsinki-NLP/opus-mt-en-fr")
    translator = ctranslate2.Translator(MT_DIR, device="cpu", compute_type="int8")

    def translate(text: str) -> str:
        tokens = tokenizer.convert_ids_to_tokens(tokenizer.encode(text))
        result = translator.translate_batch([tokens], beam_size=4)
        hyp_ids = tokenizer.convert_tokens_to_ids(result[0].hypotheses[0])
        return tokenizer.decode(hyp_ids, skip_special_tokens=True)

    translate("Warmup.")

    player = Player(voice_onnx, device=args.output_device)
    player.start()

    def emit(sentence: str):
        t0 = time.perf_counter()
        fr = translate(sentence)
        dt = (time.perf_counter() - t0) * 1000
        print(f"FR  [{dt:5.0f} ms]  {fr}")
        player.q.put(fr)

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
    pending = ""            # unpunctuated tail held across utterances
    pending_since = None

    def handle_utterance(utt: np.ndarray):
        nonlocal pending, pending_since
        segments, _info = asr.transcribe(utt, language="en", beam_size=1)
        text = " ".join(s.text.strip() for s in segments).strip()
        if not text:
            return
        print(f"\nEN  {text}")
        pending = f"{pending} {text}".strip()
        sentences, tail = complete_sentences(pending)
        pending = tail
        pending_since = time.time() if tail else None
        for s in sentences:
            emit(s)

    try:
        with sd.InputStream(
            samplerate=SR, channels=1, dtype="float32",
            callback=on_audio, device=args.input_device,
        ):
            print("Listening. Speak English, pause at sentence ends. Ctrl+C stops.")
            while True:
                time.sleep(0.1)
                with lock:
                    new, chunks[:] = chunks[:], []
                if new:
                    audio = np.concatenate([audio] + new) if audio.size else np.concatenate(new)

                # Age out a held fragment so it eventually gets translated.
                if pending and time.time() - pending_since > args.max_hold:
                    print("[hold expired — translating incomplete fragment]")
                    emit(pending)
                    pending, pending_since = "", None

                if audio.size < SR:  # under 1s buffered
                    continue

                ts = get_speech_timestamps(audio, vad_opts)
                if not ts:
                    if audio.size > SR * 5:  # long pure silence: keep last 1s
                        audio = audio[-SR:]
                    continue

                last_end = int(ts[-1]["end"])
                trailing = (audio.size - last_end) / SR
                speech_dur = (last_end - int(ts[0]["start"])) / SR
                if trailing >= args.silence and speech_dur >= 0.25:
                    utt, audio = audio[:last_end], audio[last_end:]
                    handle_utterance(utt)
                elif audio.size > SR * 30:  # very long unbroken speech: force
                    utt, audio = audio.copy(), np.empty(0, dtype=np.float32)
                    handle_utterance(utt)
    except KeyboardInterrupt:
        pass
    finally:
        player.q.put(None)
        player.join(timeout=10)
        print("\nStopped.")


if __name__ == "__main__":
    main()
