"""I1–I5 — model-integration tests. Run with: pytest -m models

Need validation/models/ populated and (I2) the piper binary. Skipped
automatically otherwise via conftest.requires_models.
"""
import time

import pytest

import conftest

pytestmark = pytest.mark.models


@pytest.fixture(scope="module")
def translator_stack():
    """Load MT stack once per module run."""
    import ctranslate2
    from transformers.models.marian.tokenization_marian import MarianTokenizer

    tok = MarianTokenizer.from_pretrained(conftest.MT_DIR)
    tr = ctranslate2.Translator(conftest.MT_DIR, device="cpu", compute_type="int8")

    def translate(text: str) -> str:
        tokens = tok.convert_ids_to_tokens(tok.encode(text))
        result = tr.translate_batch([tokens], beam_size=4)
        ids = tok.convert_tokens_to_ids(result[0].hypotheses[0])
        return tok.decode(ids, skip_special_tokens=True)

    translate("Warmup.")
    return translate


class TestMT:  # I1
    CANONICAL = [
        "Good morning, everyone, and welcome to the second day of the conference.",
        "Lunch will be served in the main hall at one o'clock sharp.",
        "We have over three thousand registered delegates from forty-two countries this year.",
        "Pastor Emeka Okafor from Lagos will lead the evening devotion.",
        "Thank you all for your attention; we will resume in fifteen minutes.",
    ]

    @conftest.requires_models
    def test_no_empty_outputs(self, translator_stack):
        for s in self.CANONICAL:
            out = translator_stack(s)
            assert out and out.strip(), f"empty translation for: {s!r}"

    @conftest.requires_models
    def test_hallucination_regression_two_million(self, translator_stack):
        """The documented failure (validation 6b): truncated 'two million'
        fragment invented 'of people'. As a COMPLETE sentence it must not
        invent content — 'personnes' must not appear from nowhere."""
        out = translator_stack(
            "Our target is to raise two million naira for the school project in Jos."
        )
        assert "personnes" not in out.lower()
        assert "deux millions" in out.lower()

    @conftest.requires_models
    def test_latency_regression(self, translator_stack):
        # validation measured ~115ms/sentence; 500ms is a loose regression
        # ceiling to catch environment decay, not a performance target.
        t0 = time.perf_counter()
        for s in self.CANONICAL:
            translator_stack(s)
        avg_ms = (time.perf_counter() - t0) * 1000 / len(self.CANONICAL)
        assert avg_ms < 500, f"avg {avg_ms:.0f}ms/sentence"


class TestOfflineLoad:  # I3
    @conftest.requires_models
    def test_tokenizer_loads_with_hub_offline(self, monkeypatch):
        monkeypatch.setenv("HF_HUB_OFFLINE", "1")
        monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
        from transformers.models.marian.tokenization_marian import MarianTokenizer

        tok = MarianTokenizer.from_pretrained(conftest.MT_DIR)
        assert tok.encode("Warmup.")


class TestPreflight:  # I4
    def test_missing_model_dir_exits_cleanly(self, monkeypatch):
        import live_loop

        monkeypatch.setattr(live_loop, "MT_DIR", r"C:\definitely\not\here")
        monkeypatch.setattr(
            "sys.argv", ["live_loop.py", "--voice", "fr_FR-siwis-medium"]
        )
        with pytest.raises(SystemExit) as exc:
            live_loop.main()
        assert "Missing" in str(exc.value)


class TestASR:  # I5
    @conftest.requires_models
    def test_transcription_deterministic_and_sane(self):
        from faster_whisper import WhisperModel

        asr = WhisperModel(conftest.ASR_SMALL, device="cpu", compute_type="int8")
        texts = []
        for _ in range(2):
            segments, _ = asr.transcribe(
                conftest.TEST_WAV, language="en", beam_size=1
            )
            texts.append(" ".join(s.text.strip() for s in segments))
        assert texts[0] == texts[1], "greedy decode should be deterministic"
        assert "Good morning" in texts[0]
        assert len(texts[0]) > 200  # the wav is a multi-sentence talk snippet


class TestTTS:  # I2
    @pytest.mark.skipif(
        not __import__("os").path.exists(conftest.PIPER),
        reason="piper binary not present",
    )
    def test_synthesize_returns_even_length_pcm(self):
        import numpy as np

        from live_loop import synthesize

        pcm = synthesize(
            "Bonjour.",
            str(conftest.MODELS_DIR + "/piper_voices/fr_FR-siwis-medium.onnx"),
        )
        assert pcm is not None
        assert pcm.size > 0
        assert pcm.dtype == np.int16
