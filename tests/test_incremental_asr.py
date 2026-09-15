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
        """A fresh sentence ending at the end of whatever audio is given —
        faithful to real Whisper end-timestamps and to real speech (each
        pass yields NEW sentences, not the same one forever)."""

        def __init__(self):
            self.n = 0

        def __call__(self, audio):
            self.n += 1
            return [(f"Sentence number {self.n} is done.", len(audio) / SEC)]

    inc = IncrementalASR(Repeater())
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


def test_drop_prefix_overlap_removes_revision_duplicates():
    from live_loop import drop_prefix_overlap
    recent = ["Hello there.", "How are you."]
    # Whisper re-emits both, then adds new — duplicates dropped
    assert drop_prefix_overlap(
        ["Hello there.", "How are you.", "I am fine."], recent
    ) == ["I am fine."]
    # No overlap — untouched
    assert drop_prefix_overlap(["Something new."], recent) == ["Something new."]


def test_drop_prefix_overlap_keeps_genuine_repeats():
    from live_loop import drop_prefix_overlap
    # "Thank you." repeated with other content between: NOT consecutive
    # suffix/prefix, so it survives (a real speaker may repeat themselves).
    recent = ["Thank you.", "Now a thing."]
    assert drop_prefix_overlap(["Thank you."], recent) == ["Thank you."]


def test_split_long_fragment_bounds_tts_blob():
    from live_loop import split_long_fragment
    short = " ".join(["word"] * 39)
    assert split_long_fragment(short) == [short]
    long_frag = " ".join([f"w{i}" for i in range(95)])
    parts = split_long_fragment(long_frag)
    assert len(parts) == 3
    assert all(len(p.split()) <= 40 for p in parts)
    assert " ".join(parts) == long_frag  # lossless reassembly


def test_incremental_dedupes_revision_prefix():
    fw = FakeWhisper([
        [("Alpha one. Beta two.", 2.0)],
        [("Alpha one. Beta two. Gamma three.", 3.0)],  # re-emits committed pair
    ])
    inc = IncrementalASR(fw)
    s1, _, _ = inc.feed(chunk(2.0))
    s2, _, _ = inc.feed(chunk(1.0))
    assert s1 == ["Alpha one.", "Beta two."]
    assert s2 == ["Gamma three."]
