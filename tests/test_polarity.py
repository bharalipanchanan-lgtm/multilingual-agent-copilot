"""Polarity check (answer.affirms_cover): a covered claim built only on exclusion clauses is blocked."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from answer import affirms_cover  # noqa: E402


@pytest.mark.parametrize("text", [
    "Maternity expenses are covered except for ectopic pregnancy [1].",
    "Maternity is covered for medical treatment expenses traceable to childbirth, but not for ectopic pregnancy [1].",
    "Delivery ka kharcha cover hota hai [2].",
    "हाँ, डिलीवरी का खर्च कवर होता है [1]।",
])
def test_affirmative(text):
    assert affirms_cover(text)


@pytest.mark.parametrize("text", [
    "Maternity is not covered by this policy [2].",
    "Delivery ka kharcha cover nahi hota [2].",
    "डिलीवरी का खर्च कवर नहीं होता है [1]।",
    "Childbirth expenses are excluded, except ectopic pregnancy [1].",
    "This is not stated in the policy document.",
])
def test_not_affirmative(text):
    assert not affirms_cover(text)


@pytest.mark.parametrize("q,term", [
    ("Kya iss policy mein pehle se maujud bimariyon ke liye waiting period hai?", "pre-existing disease"),
    ("Delivery ka kharcha cover hota hai?", "maternity"),
    ("Motiyabind ke ilaj ka waiting period?", "cataract"),
])
def test_hinglish_terms_expand_the_search_only(q, term):
    from answer import search_query
    out = search_query(q)
    assert out.startswith(q) and term in out


def test_english_question_is_unchanged():
    from answer import search_query
    assert search_query("What is the room rent limit?") == "What is the room rent limit?"
