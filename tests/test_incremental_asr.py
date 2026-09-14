"""IncrementalASR + TranscriptLog (design 13.7 rec 1 / PRD F11).

The fake transcriber scripts Whisper-like behavior: it returns segments with
text and end-timestamps, and — crucially — may REVISION the unfinished tail
on later passes. The contract under test: committed sentences never change,
only complete sentences are ever emitted, and committed audio is dropped so
memory stays flat.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "validation", "scripts"))

from live_loop import IncrementalASR, TranscriptLog

SEC = 16000  # samples per second at SR


def chunk(seconds):
    return np.zeros(int(seconds * SEC), dtype=np.float32)


class FakeWhisper:
    """Returns scripted (text, end_s) segments per pass, in order."""

    def __init__(self, passes):
        self.passes = list(passes)
        self.calls = 0

    def __call__(self, audio):
        i = min(self.calls, len(self.passes) - 1)
        self.calls += 1
        return self.passes[i]


def test_commits_only_complete_sentences():
    fw = FakeWhisper([[("Hello there.", 1.0), (" And this is not fin", 2.0)]])
    inc = IncrementalASR(fw)
    sentences, tail, _ = inc.feed(chunk(2.0))
    assert sentences == ["Hello there."]
    assert "not fin" in tail


def test_tail_can_be_revised_without_changing_committed():
    fw = FakeWhisper([
        [("Hello there.", 1.0), (" And this is not", 2.0)],        # partial tail
        [(" And this is not finished yet", 2.0)],                  # revised tail, still open
        [(" And this is not finished yet. Done", 3.0)],            # now complete
    ])
    inc = IncrementalASR(fw)
    s1, t1, _ = inc.feed(chunk(2.0))
    s2, t2, _ = inc.feed(chunk(1.0))
    s3, t3, _ = inc.feed(chunk(1.0))
    assert s1 == ["Hello there."]
    assert s2 == []                      # tail still unfinished, nothing new committed
    assert s3 == ["And this is not finished yet."]
    assert "Done" in t3


def test_committed_audio_is_dropped_buffer_stays_bounded():
    # Many passes, each committing a sentence: buffer must not grow with
    # total session length (only with un-committed tail).
    class Repeater:
        """Sentence always ends at the end of whatever audio is given —
        faithful to real Whisper end-timestamps."""

        def __init__(self, text):
            self.text = text

        def __call__(self, audio):
            return [(self.text, len(audio) / SEC)]

    inc = IncrementalASR(Repeater("Sentence number is done."))
    sizes = []
    for _ in range(20):
        inc.feed(chunk(2.0))
        sizes.append(inc.buf.size)
    assert max(sizes) < 4 * SEC, f"buffer grew unboundedly: {max(sizes)/SEC:.1f}s"


def test_final_returns_remaining_sentences():
    fw = FakeWhisper([[("One. Two. Three unfinished", 3.0)]])
    inc = IncrementalASR(fw)
    sentences, tail, _ = inc.feed(chunk(3.0), final=True)
    assert sentences == ["One.", "Two."]
    assert "unfinished" in tail


def test_transcript_log_writes_jsonl(tmp_path):
    tlog = TranscriptLog(str(tmp_path / "sub" / "t.jsonl"))
    tlog.log("en", "Hello there.")
    tlog.log("fr", "Bonjour.")
    tlog.log("dropped", "Skipped line.")
    path = tmp_path / "sub" / "t.jsonl"
    lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    assert [l["kind"] for l in lines] == ["en", "fr", "dropped"]
    assert [l["text"] for l in lines] == ["Hello there.", "Bonjour.", "Skipped line."]
    assert all("t" in l for l in lines)
