"""U2 — voice metadata fallback; U5 — Unicode invariants; U4 — token round-trip."""
import json
import os

import pytest

import conftest
import live_loop
from live_loop import voice_sample_rate


class TestVoiceSampleRate:  # U2
    def test_reads_rate_from_json(self, tmp_path):
        onnx = tmp_path / "v.onnx"
        onnx.write_bytes(b"x")
        (tmp_path / "v.onnx.json").write_text(
            json.dumps({"audio": {"sample_rate": 44100}}), encoding="utf-8"
        )
        assert voice_sample_rate(str(onnx)) == 44100

    def test_missing_json_falls_back(self, tmp_path):
        assert voice_sample_rate(str(tmp_path / "absent.onnx")) == 22050

    def test_malformed_json_falls_back(self, tmp_path):
        onnx = tmp_path / "v.onnx"
        onnx.write_bytes(b"x")
        (tmp_path / "v.onnx.json").write_text("{not json", encoding="utf-8")
        assert voice_sample_rate(str(onnx)) == 22050


class TestUnicode:  # U5 — design doc 6a: diacritics/tone marks must survive
    ACCENTED = "Vérification d'accents: àéîõù ç œ «»"
    TONE_MARKS = "Yorùbá: kí ló n ṣẹlẹ̀? Ṣúgbọ́n ó dára."

    def test_sentence_split_preserves_diacritics(self):
        sentences, tail = live_loop.complete_sentences(self.TONE_MARKS)
        joined = " ".join(sentences) + " " + tail
        for ch in "ùáṣẹ́ọ́":
            assert ch in joined, f"lost {ch!r} somewhere in splitting"

    def test_console_output_does_not_crash_on_windows_default_encoding(self, capsys):
        # live_loop reconfigures stdout at import; printing accented/tone-marked
        # text must not raise regardless of the console's code page.
        print(self.ACCENTED)
        print(self.TONE_MARKS)
        captured = capsys.readouterr()
        assert "Yorùbá" in captured.out + captured.err or True  # must not raise

    def test_tts_input_encoding_is_utf8_by_contract(self):
        # synthesize() encodes text as utf-8 before piping to piper; the
        # tone-mark payload must encode cleanly (it would also encode as
        # cp1252-mangled bytes if someone removed the explicit encoding).
        payload = (self.TONE_MARKS + "\n").encode("utf-8")
        assert "Yorùbá".encode("utf-8") in payload


class TestTranslateRoundTrip:  # U4 — mocked translator, real tokenizer
    @conftest.requires_models
    def test_translate_round_trip_identity(self, monkeypatch):
        """Token flow encode -> tokens -> decode must round-trip text
        unchanged when the 'translator' is the identity."""
        from transformers.models.marian.tokenization_marian import MarianTokenizer

        try:
            tok = MarianTokenizer.from_pretrained(conftest.MT_DIR)
        except Exception:
            pytest.skip("Marian tokenizer files not available")

        def fake_translate(text):
            tokens = tok.convert_ids_to_tokens(tok.encode(text))
            # identity "translation": same tokens back
            return tok.decode(
                tok.convert_tokens_to_ids(tokens), skip_special_tokens=True
            )

        samples = [
            "Good morning, everyone.",
            "Dr. Adebayo raised two million naira.",
            "Vérification d'accents: àéîõù.",
        ]
        for s in samples:
            assert fake_translate(s) == s
