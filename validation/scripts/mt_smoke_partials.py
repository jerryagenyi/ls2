"""MT partial-fragment smoke test: Opus-MT EN->FR on truncated/mid-sentence input.

The real pipeline feeds VAD-chunked fragments, not tidy full sentences
(design doc section 8: partial-translation jitter). This test deliberately
truncates and mid-cuts sentences to see what the MT stage does with them.
Writes validation/mt/mt_smoke_partials_results.md for native-speaker review.
"""
import os
import time

import ctranslate2
from transformers import AutoTokenizer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(ROOT, "models", "opus-mt-en-fr")
OUT = os.path.join(ROOT, "mt", "mt_smoke_partials_results.md")

# (label, fragment) — fragments a VAD chunker would realistically emit
FRAGMENTS = [
    ("truncated-head", "Good morning everyone and a"),
    ("truncated-head", "Before we begin I would like to thank the"),
    ("truncated-head", "The shuttle buses to the hotels leave every"),
    ("truncated-head", "Our target is to raise two million"),
    ("truncated-head", "Registration for tomorrow's breakout sessions closes at"),
    ("mid-sentence-start", "will now share the findings from the community health survey"),
    ("mid-sentence-start", "begins with an appeal to present your bodies as a living sacrifice"),
    ("mid-sentence-start", "if you need to take a call"),
    ("mid-sentence-start", "who still needs a name badge or a"),
    ("clause-cut", "We are delighted to see so many delegates gathered here from every"),
    ("clause-cut", "Please check the notice board beside the main entrance to find"),
    ("clause-cut", "Each workshop will run for ninety minutes, with a short"),
    ("short-utterance", "Thank you."),
    ("short-utterance", "Please be seated."),
    ("short-utterance", "One moment please"),
]


def main():
    tokenizer = AutoTokenizer.from_pretrained("Helsinki-NLP/opus-mt-en-fr")
    translator = ctranslate2.Translator(MODEL_DIR, device="cpu", compute_type="int8")

    def translate(text: str) -> str:
        tokens = tokenizer.convert_ids_to_tokens(tokenizer.encode(text))
        result = translator.translate_batch([tokens], beam_size=4)
        hyp_ids = tokenizer.convert_tokens_to_ids(result[0].hypotheses[0])
        return tokenizer.decode(hyp_ids, skip_special_tokens=True)

    translate(FRAGMENTS[0][1])  # warmup

    rows = []
    for label, frag in FRAGMENTS:
        t0 = time.perf_counter()
        fr = translate(frag)
        dt = time.perf_counter() - t0
        rows.append((label, frag, fr, dt))
        print(f"[{dt*1000:6.1f} ms] [{label}] {frag!r} -> {fr!r}")

    lines = [
        "# MT partial-fragment test — Opus-MT EN->FR (CTranslate2 int8, CPU)",
        "",
        "Inputs are deliberately truncated/mid-sentence, mimicking what VAD",
        "chunking feeds the MT stage in the live pipeline (design doc section 8).",
        "Review question for the native speaker: for each row, is the French an",
        "acceptable rendering of the fragment, and does anything get invented,",
        "completed, or garbled that would mislead a listener?",
        "",
        "| Type | English fragment | French output |",
        "|------|------------------|---------------|",
    ]
    for label, frag, fr, _dt in rows:
        lines.append(
            f"| {label} | {frag.replace('|', '/')} | {fr.replace('|', '/')} |"
        )
    lat = [r[3] for r in rows]
    lines += [
        "",
        f"Avg latency/fragment: {sum(lat)/len(lat)*1000:.0f} ms "
        f"(max {max(lat)*1000:.0f} ms).",
        "",
    ]

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
