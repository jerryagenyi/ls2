import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "validation", "scripts"))

MODELS_DIR = os.path.join(ROOT, "validation", "models")
MT_DIR = os.path.join(MODELS_DIR, "opus-mt-en-fr")
ASR_SMALL = os.path.join(MODELS_DIR, "faster-whisper-small")
TEST_WAV = os.path.join(ROOT, "validation", "asr", "test_audio_en.wav")
PIPER = os.path.join(ROOT, "validation", "bin", "piper", "piper.exe")


def models_installed() -> bool:
    return all(os.path.exists(p) for p in (MT_DIR, ASR_SMALL, TEST_WAV))


requires_models = pytest.mark.skipif(
    not models_installed(), reason="model files not present in validation/models/"
)
