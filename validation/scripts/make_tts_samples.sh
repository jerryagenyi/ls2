#!/usr/bin/env bash
# Generate identical TTS audition samples with each French Piper voice.
# Usage: make_tts_samples.sh <text-file>
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIPER="$ROOT/bin/piper/piper.exe"
VOICES_DIR="$ROOT/models/piper_voices"
OUT_DIR="$ROOT/tts/samples"
TEXT_FILE="${1:?usage: make_tts_samples.sh <text-file>}"

mkdir -p "$OUT_DIR"

for voice in fr_FR-siwis-medium fr_FR-tom-medium fr_FR-upmc-medium; do
    echo "=== $voice ==="
    "$PIPER" --model "$VOICES_DIR/$voice.onnx" \
        --output_file "$OUT_DIR/$voice.wav" < "$TEXT_FILE"
done

ls -la "$OUT_DIR"
