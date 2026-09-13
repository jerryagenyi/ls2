"""ASR benchmark: faster-whisper on CPU, int8, VAD on, English.

Measures model load time and real-time factor (processing time / audio
duration) for tiny/base/small on validation/asr/test_audio_en.wav.
First run downloads models from HuggingFace (Systran/faster-whisper-*).
Writes validation/asr/asr_benchmark.md.
"""
import os
import platform
import time

from faster_whisper import WhisperModel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO = os.path.join(ROOT, "asr", "test_audio_en.wav")
OUT = os.path.join(ROOT, "asr", "asr_benchmark.md")

SIZES = ["tiny", "base", "small"]


def main():
    rows = []
    for size in SIZES:
        t0 = time.perf_counter()
        model = WhisperModel(size, device="cpu", compute_type="int8")
        load_s = time.perf_counter() - t0

        t0 = time.perf_counter()
        segments, info = model.transcribe(
            AUDIO, language="en", beam_size=1, vad_filter=True
        )
        n_seg, n_words, text_len = 0, 0, 0
        for seg in segments:
            n_seg += 1
            n_words += len(seg.text.split())
            text_len += len(seg.text)
        elapsed = time.perf_counter() - t0

        rtf = elapsed / info.duration
        rows.append((size, load_s, elapsed, info.duration, rtf, n_seg, n_words))
        print(f"{size:6s} load={load_s:5.1f}s proc={elapsed:6.1f}s "
              f"audio={info.duration:5.1f}s RTF={rtf:.2f} "
              f"segs={n_seg} words={n_words}")

    lines = [
        "# ASR benchmark — faster-whisper, CPU int8, VAD on, beam=1",
        "",
        f"- Machine: {platform.processor()} ({platform.machine()}), Windows",
        f"- Audio: test_audio_en.wav (Piper en_US-lessac-medium, "
        f"{rows[0][3]:.0f}s)",
        "- Settings: language=en, beam_size=1, vad_filter=True, int8",
        "- Note: load time on first run includes one-time model download.",
        "",
        "| Model | Load (s) | Processing (s) | Audio (s) | RTF | Segments | Words |",
        "|-------|----------|----------------|-----------|-----|----------|-------|",
    ]
    for size, load_s, elapsed, dur, rtf, n_seg, n_words in rows:
        lines.append(
            f"| {size} | {load_s:.1f} | {elapsed:.1f} | {dur:.1f} "
            f"| {rtf:.2f} | {n_seg} | {n_words} |"
        )
    lines += [
        "",
        "RTF < 1.0 means faster than real-time — the threshold for live use.",
        "",
    ]

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
