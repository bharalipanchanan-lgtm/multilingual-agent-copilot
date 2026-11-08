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


@pytest.mark.parametrize("text", [
    "The provided policy clauses do not mention or state any co-payment [1][2].",
    "Co-payment is not specified in the provided clauses [3].",
    "There is no information about co-payment in the policy text [1].",
    "Clauses mein co-pay ka zikr nahi hai [2].",
    "पॉलिसी में को-पे का उल्लेख नहीं है [1]।",
    "Room Rent ki koi limit policy mein mentioned nahi hai [1].",
    "Is policy mein room rent par koi specific limit nahi di gayi hai [1].",
    "Room rent ki limit ke baare mein is policy wording mein kuch nahi bataya gaya hai [1][2].",
    "No specific limit is mentioned for room rent [2].",
])
def test_absence_in_words_is_not_an_answer(text):
    from answer import ABSENCE_RE
    assert ABSENCE_RE.search(text)


@pytest.mark.parametrize("text", [
    "Maternity is not covered under this policy [1].",
    "The policy does not cover cosmetic treatment [2].",
    "Room rent is limited to 1% of the sum insured per day [1].",
    "Yeh policy lifetime renewable nahi hai [1].",
    "Maternity is policy mein cover nahi hota hai [1].",
    "Room rent ki limit 1% of sum insured per day hai [1].",
    "Pre-existing diseases 36 months tak cover nahi honge [2].",
])
def test_real_answers_are_kept(text):
    from answer import ABSENCE_RE
    assert not ABSENCE_RE.search(text)
