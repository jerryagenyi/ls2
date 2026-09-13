"""Generate ~3 min of 16-bit mono English speech via Piper for ASR benchmarking.

Synthesizes conference-style paragraphs with en_US-lessac-medium, one WAV per
paragraph, then concatenates into validation/asr/test_audio_en.wav.
"""
import os
import subprocess
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIPER = os.path.join(ROOT, "bin", "piper", "piper.exe")
VOICE = os.path.join(ROOT, "models", "piper_voices", "en_US-lessac-medium.onnx")
TMP = os.path.join(ROOT, "asr", "chunks")
OUT = os.path.join(ROOT, "asr", "test_audio_en.wav")

PARAGRAPHS = [
    "Good morning everyone, and a very warm welcome to this year's leadership "
    "summit. We are delighted to see so many delegates gathered here from every "
    "part of the country, and from beyond our borders as well. Before we begin, "
    "I would like to thank the organising committee for the many months of "
    "preparation that brought us to this day.",
    "Our first plenary session will examine the state of community development "
    "in the region. Doctor Adebayo from the university will present the findings "
    "of a survey conducted across three hundred communities, covering health, "
    "education, and access to clean water. His team collected data over a period "
    "of eighteen months, and the results are both encouraging and challenging.",
    "In the afternoon, we will break into smaller groups for the workshops. "
    "Please check the notice board beside the main entrance to find your room "
    "assignment. Each workshop will run for ninety minutes, with a short break "
    "in the middle. Kindly keep your phones on silent, and step outside if you "
    "need to take a call.",
    "A few practical announcements. Lunch will be served in the main hall at one "
    "o'clock. The shuttle buses to the hotels depart from the east gate every "
    "thirty minutes, and the last bus leaves at nine in the evening. The "
    "registration desk remains open until six p m for anyone who still needs a "
    "name badge or a certificate of attendance.",
    "Finally, let me remind us all why we are here. The work we do is not for "
    "ourselves, but for the communities we serve. Faith without works is dead, "
    "and our planning this week must translate into action next month. Thank "
    "you for your attention, and may this be a profitable time for everyone.",
]


def main():
    os.makedirs(TMP, exist_ok=True)
    chunk_paths = []
    for i, text in enumerate(PARAGRAPHS):
        path = os.path.join(TMP, f"chunk_{i:02d}.wav")
        subprocess.run(
            [PIPER, "--model", VOICE, "--output_file", path],
            input=text.encode("utf-8"),
            check=True,
        )
        chunk_paths.append(path)

    with wave.open(chunk_paths[0], "rb") as w0:
        params = w0.getparams()

    with wave.open(OUT, "wb") as out:
        out.setparams(params)
        for path in chunk_paths:
            with wave.open(path, "rb") as w:
                out.writeframes(w.readframes(w.getnframes()))

    with wave.open(OUT, "rb") as w:
        print(f"Wrote {OUT}: {w.getnframes() / w.getframerate():.1f}s, "
              f"{w.getframerate()} Hz, {w.getnchannels()} ch")


if __name__ == "__main__":
    main()
