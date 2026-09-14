"""MT smoke test: Opus-MT EN->FR via CTranslate2 int8 on CPU.

20 conference-style sentences (logistics, names, numbers, church/register mix).
Writes side-by-side results + timing to validation/mt/mt_smoke_results.md
for native-speaker review.
"""
import os
import time

import ctranslate2
from transformers.models.marian.tokenization_marian import MarianTokenizer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(ROOT, "models", "opus-mt-en-fr")
OUT = os.path.join(ROOT, "mt", "mt_smoke_results.md")

SENTENCES = [
    "Good morning, everyone, and welcome to the second day of the conference.",
    "Please make sure your translation devices are switched on and set to your language.",
    "Our next speaker needs no introduction, but I will give him one anyway.",
    "Can we get a sound check on the microphones before the worship team comes up?",
    "The book of Romans chapter twelve begins with an appeal to present your bodies as a living sacrifice.",
    "Dr. Adebayo will now share the findings from the community health survey in Kano.",
    "Lunch will be served in the main hall at one o'clock sharp.",
    "We have over three thousand registered delegates from forty-two countries this year.",
    "Please silence your phones for the duration of the session.",
    "Faith is the substance of things hoped for, the evidence of things not seen.",
    "The shuttle buses to the hotels leave every thirty minutes from the east gate.",
    "If you are interpreting for the French channel, please keep your levels around minus six decibels.",
    "This workshop will cover financial accountability for non-profit organisations.",
    "Pastor Emeka Okafor from Lagos will lead the evening devotion.",
    "We apologise for the brief interruption in the audio feed.",
    "Registration for tomorrow's breakout sessions closes at six p.m.",
    "The choir will now minister a special number entitled 'Amazing Grace'.",
    "Please remain seated; the dignitaries are about to arrive.",
    "Our target is to raise two million naira for the school project in Jos.",
    "Thank you all for your attention; we will resume in fifteen minutes.",
]


def main():
    tokenizer = MarianTokenizer.from_pretrained(MODEL_DIR)
    translator = ctranslate2.Translator(
        MODEL_DIR, device="cpu", compute_type="int8"
    )

    def translate(text: str) -> str:
        tokens = tokenizer.convert_ids_to_tokens(tokenizer.encode(text))
        result = translator.translate_batch([tokens], beam_size=4)
        hyp_ids = tokenizer.convert_tokens_to_ids(result[0].hypotheses[0])
        return tokenizer.decode(hyp_ids, skip_special_tokens=True)

    # Warmup (first call pays some one-time cost)
    translate(SENTENCES[0])

    rows = []
    latencies = []
    total_tokens = 0
    for sent in SENTENCES:
        t0 = time.perf_counter()
        fr = translate(sent)
        dt = time.perf_counter() - t0
        latencies.append(dt)
        total_tokens += len(tokenizer.encode(fr))
        rows.append((sent, fr, dt))
        print(f"[{dt*1000:7.1f} ms] {fr}")

    avg = sum(latencies) / len(latencies)
    total_time = sum(latencies)
    lines = [
        "# MT smoke test — Opus-MT EN->FR (CTranslate2 int8, CPU)",
        "",
        f"- Model: `michaelfeil/ct2fast-opus-mt-en-fr` (Helsinki-NLP/opus-mt-en-fr converted), beam_size=4",
        f"- Sentences: {len(SENTENCES)}",
        f"- Avg latency/sentence: {avg*1000:.0f} ms | max: {max(latencies)*1000:.0f} ms",
        f"- Throughput: {total_tokens/total_time:.1f} target tokens/s",
        "",
        "## Output (for native-speaker review)",
        "",
        "| # | English | French |",
        "|---|---------|--------|",
    ]
    for i, (en, fr, _dt) in enumerate(rows, 1):
        en_c = en.replace("|", "/")
        fr_c = fr.replace("|", "/")
        lines.append(f"| {i} | {en_c} | {fr_c} |")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
