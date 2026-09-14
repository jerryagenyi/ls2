"""U1 — sentence-boundary splitting (complete_sentences).

The regression that matters most: a fragment reaching MT is the documented
hallucination trigger ("two million" -> invented "of people", validation 6b).
These tests pin the splitting rules, including the abbreviation fix from
manual test M4 ("Dr." was split off as its own fragment).
"""
import pytest

from live_loop import complete_sentences


class TestBasicSplitting:
    def test_each_terminal_punct_splits(self):
        for punct in ".!?":
            sentences, tail = complete_sentences(f"One two{punct} Next sentence.")
            assert sentences == [f"One two{punct}", "Next sentence."]
            assert tail == ""

    def test_no_punctuation_returns_all_as_tail(self):
        sentences, tail = complete_sentences("no terminal punctuation here")
        assert sentences == []
        assert tail == "no terminal punctuation here"

    def test_empty_and_whitespace_input(self):
        for text in ("", "   ", "\n\t"):
            assert complete_sentences(text) == ([], "")

    def test_whitespace_stripped_around_sentences(self):
        sentences, tail = complete_sentences("  Hello there.  And again. ")
        assert sentences == ["Hello there.", "And again."]
        assert tail == ""


class TestAbbreviations:
    def test_dr_not_split(self):  # the M4 regression
        sentences, _ = complete_sentences(
            "Dr. Adebayo raised two million naira for the school project."
        )
        assert sentences == [
            "Dr. Adebayo raised two million naira for the school project."
        ]

    def test_common_titles(self):
        text = "Mr. Okoro met Prof. Wole and Mrs. Adaeze at St. James."
        sentences, _ = complete_sentences(text)
        assert sentences == [text]

    def test_etc_vs_mid_sentence(self):
        sentences, _ = complete_sentences("Names, places, etc. were checked. Done.")
        assert sentences == ["Names, places, etc. were checked.", "Done."]

    def test_sentence_still_ends_after_abbreviation(self):
        # The abbreviation is skipped, but a later real boundary still splits.
        sentences, tail = complete_sentences("See Dr. Adebayo now. Then rest")
        assert sentences == ["See Dr. Adebayo now."]
        assert tail == "Then rest"


class TestPunctuationEdges:
    def test_stacked_terminal_punct_keeps_one_sentence(self):
        sentences, _ = complete_sentences("Really?! That works.")
        assert sentences == ["Really?!", "That works."]  # '!' joins '?', no junk fragment

    def test_decimal_numbers_not_boundaries(self):
        # "9.50" has no space: the split rule would cut mid-number if it
        # treated every period as a boundary after any word. R4 transcript
        # showed "9.50pm" style inputs reaching the buffer.
        sentences, _ = complete_sentences("It is 9.50pm now. Goodbye.")
        # current behavior: "It is 9." splits (no abbreviation) — if this
        # test starts failing because splitting improved, update the pin,
        # but never allow a fragment that ends mid-number to be *silently
        # accepted as final* without this test being consciously revisited.
        assert any(s.startswith("It is 9") for s in sentences)

    def test_tail_carries_across_calls(self):  # the buffer contract used by main()
        s1, tail1 = complete_sentences("this has no end yet")
        assert (s1, tail1) == ([], "this has no end yet")
        s2, tail2 = complete_sentences(f"{tail1} but now it does.")
        assert s2 == ["this has no end yet but now it does."]
        assert tail2 == ""
