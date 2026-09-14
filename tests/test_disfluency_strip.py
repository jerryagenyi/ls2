"""Disfluency stripping (design doc 13.4 item 2) — conservative by contract.

The stripper runs before MT: it must remove filler that wastes French audio
time and pollutes MT input, while NEVER touching words that can carry
meaning ("like", "so" are deliberately not stripped).
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "validation", "scripts"))

from live_loop import strip_disfluencies


def test_strips_common_fillers():
    assert strip_disfluencies("So um I think uh this works") == "So I think this works"


def test_strips_phrasal_fillers():
    assert strip_disfluencies(
        "It's kind of you know a test sort of thing, I mean really"
    ) == "It's a test thing, really"


def test_conservative_like_and_so_survive():
    # "like" and "so" carry meaning too often — they must NOT be stripped.
    assert strip_disfluencies("Amazing Grace like that") == "Amazing Grace like that"
    assert strip_disfluencies("So that we can proceed") == "So that we can proceed"


def test_names_and_content_untouched():
    text = "Dr. Adebayo raised two million naira for the school project in Jos."
    assert strip_disfluencies(f"um {text} uh") == text


def test_whitespace_collapsed():
    out = strip_disfluencies("um  hello   there  you know")
    assert out == "hello there"
    assert "  " not in out


def test_idempotent():
    once = strip_disfluencies("So um we kind of proceed")
    assert strip_disfluencies(once) == once
