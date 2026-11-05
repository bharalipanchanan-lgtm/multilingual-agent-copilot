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
