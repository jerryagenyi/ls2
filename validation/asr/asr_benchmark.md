# ASR benchmark — faster-whisper, CPU int8, VAD on, beam=1

- Machine: AMD64 Family 25 Model 33 Stepping 2, AuthenticAMD (AMD64), Windows
- Audio: test_audio_en.wav (Piper en_US-lessac-medium, 90s)
- Settings: language=en, beam_size=1, vad_filter=True, int8
- Note: load time on first run includes one-time model download.

| Model | Load (s) | Processing (s) | Audio (s) | RTF | Segments | Words |
|-------|----------|----------------|-----------|-----|----------|-------|
| tiny | 1.5 | 3.0 | 90.0 | 0.03 | 26 | 286 |
| base | 4.9 | 4.6 | 90.0 | 0.05 | 24 | 287 |
| small | 12.9 | 13.7 | 90.0 | 0.15 | 23 | 285 |

RTF < 1.0 means faster than real-time — the threshold for live use.

