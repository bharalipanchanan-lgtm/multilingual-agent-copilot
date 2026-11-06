"""Choosing the policy in conversation (chat.py, policy_select.py). No model is loaded: every
case here ends before retrieval, except where noted."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chat import converse  # noqa: E402
from policy_select import by_number, mentioned, selection_only  # noqa: E402


def turn(text, current=None):
    evs = list(converse(text, current, gen=None))
    pol = next((e["policy_id"] for e in evs if e["type"] == "policy"), None)
    return pol, evs[-1]


@pytest.mark.parametrize("text,pid", [
    ("I would like to review the SBI health insurance policy", "sbi_retail_health"),
    ("SBI dekhna hai", "sbi_retail_health"),
    ("mujhe oriental wali policy dekhni hai", "oriental_sampoorna"),
    ("Oriental Sampoorna Swasthya Suraksha", "oriental_sampoorna"),
    ("United India", "united_india"),
    ("Royal Sundaram multiplier policy kholo", "royal_multiplier"),
    ("national mediclaim", "national_mediclaim"),
    ("एसबीआई की पॉलिसी देखनी है", "sbi_retail_health"),
    ("मुझे यूनाइटेड इंडिया पॉलिसी दिखाओ", "united_india"),
    ("oriantal", "oriental_sampoorna"),  # spelling slip
    ("sundram", "royal_multiplier"),
])
def test_selection_only(text, pid):
    pol, fin = turn(text)
    assert pol == pid
    assert fin["status"] == "selected" and fin["policy_id"] == pid


@pytest.mark.parametrize("text,lang", [
    ("SBI dekhna hai", "hinglish"), ("I want to check the SBI policy", "en"), ("एसबीआई की पॉलिसी देखनी है", "hi")])
def test_reply_language(text, lang):
    _, fin = turn(text)
    assert fin["lang"] == lang


def test_number_picks_from_the_list():
    pol, fin = turn("2")
    assert pol == by_number("2") and fin["status"] == "selected"


def test_question_without_policy_asks_which_one():
    pol, fin = turn("Room rent kitna hai?")
    assert pol is None and fin["status"] == "choose_policy" and fin["pending"] is True
    assert "Kaunsa policy document" in fin["answer"]
    assert len(fin["options"]) == 5


def test_greeting_like_text_asks_in_english():
    _, fin = turn("What is the room rent limit?")
    assert fin["status"] == "choose_policy" and fin["answer"].startswith("Which policy document")


def test_two_policies_outside_compare_asks_which():
    pol, fin = turn("SBI or Oriental room rent?")
    assert pol is None and fin["status"] == "choose_policy" and len(fin["options"]) == 2


def test_unloaded_insurer_is_not_answered_from_the_current_policy():
    pol, fin = turn("HDFC Ergo ka room rent kitna hai?", current="sbi_retail_health")
    assert fin["status"] == "choose_policy" and "HDFC" in fin["answer"]


def test_switching_policy_mid_conversation():
    pol, fin = turn("ab united india dekhna hai", current="sbi_retail_health")
    assert pol == "united_india" and fin["status"] == "selected"


def test_same_policy_named_again_does_not_emit_a_change():
    pol, fin = turn("SBI", current="sbi_retail_health")
    assert pol is None and fin["status"] == "selected"


def test_brochure_carries_a_warning():
    _, fin = turn("Royal Sundaram")
    assert "brochure" in fin["answer"] and "not the full policy wording" in fin["answer"]


def test_oriental_plan_name_royal_does_not_select_royal_sundaram():
    found, _ = mentioned("Royal plan mein ICU ka limit kya hai?")
    assert found == []


def test_premium_question_is_refused_without_a_policy():
    _, fin = turn("What is the premium for a 45 year old for 10 lakh?")
    assert fin["status"] == "refused"


def test_compare_needs_no_policy_and_can_be_narrowed():
    _, fin = turn("Compare SBI and Oriental room rent")
    assert fin["status"] == "compared"
    assert {r["policy_id"] for r in fin["table"]["rows"]} == {"sbi_retail_health", "oriental_sampoorna"}
    _, fin = turn("Compare the diabetes waiting period across policies")
    assert len(fin["table"]["rows"]) == 5


def test_question_with_policy_name_is_not_selection_only():
    found, rest = mentioned("United India mein room rent kitna hai?")
    assert found == ["united_india"] and not selection_only(rest)


@pytest.mark.parametrize("text", ["Which policy document can I inspect?", "policy badlo", "switch policy",
                                  "Kaunsa policy document dekh sakte hain?", "dusri policy dekhni hai",
                                  "कौन सी पॉलिसी उपलब्ध है?"])
def test_asking_for_the_list(text):
    pol, fin = turn(text, current="sbi_retail_health")
    assert pol is None and fin["status"] == "choose_policy" and fin["pending"] is False


@pytest.mark.parametrize("text", ["Kaunsi policy mein mental illness cover hai?", "Which policy has the lowest co-pay?"])
def test_which_policy_questions_still_compare(text):
    _, fin = turn(text)
    assert fin["status"] == "compared"


@pytest.mark.parametrize("text", ["Which policy has the best room rent?", "Kaunsi policy mein mental illness cover hai?",
                                  "Which policy document covers maternity?"])
def test_content_after_which_policy_is_not_a_list_request(text):
    _, fin = turn(text)
    # "best room rent" asks for a shortlist (rank.py); the others are comparisons. Never the list.
    assert fin["status"] == ("ranked" if "best" in text else "compared")


def test_held_question_naming_two_policies_uses_the_chosen_one():
    evs = list(converse("SBI ya United India, room rent kitna hai?", "united_india", gen=None, held=True))
    # goes on to retrieval for United India instead of asking again
    assert not any(e.get("status") == "choose_policy" for e in evs)
    assert evs[-1]["policy_id"] == "united_india"


def test_bare_name_keeps_the_conversation_language():
    fin = list(converse("United India", None, gen=None, prev_lang="hinglish"))[-1]
    assert fin["status"] == "selected" and fin["lang"] == "hinglish" and fin["answer"].startswith("Theek hai")
    fin = list(converse("2", None, gen=None, prev_lang="hi"))[-1]
    assert fin["lang"] == "hi"


@pytest.mark.parametrize("text,clean", [
    ("SBI ya United India, room rent kitna hai?", "room rent kitna hai?"),
    ("United India mein room rent kitna hai?", "room rent kitna hai?"),
    ("What does the SBI policy say about maternity?", "What does the policy say about maternity?"),
    ("एसबीआई में मैटरनिटी कवर है क्या?", "मैटरनिटी कवर है क्या?"),
    ("Room rent kitna hai?", "Room rent kitna hai?"),
    ("Royal plan mein ICU ka limit kya hai?", "Royal plan mein ICU ka limit kya hai?"),
])
def test_strip_names(text, clean):
    from policy_select import strip_names
    assert strip_names(text) == clean


@pytest.mark.parametrize("text,pid", [
    # exact transcripts returned by Sarvam saaras:v3 (mode translit) for the test clips
    ("Mujhe SBI vali policy dekhni hai.", "sbi_retail_health"),
    ("Mujhe oriental vala policy chahie.", "oriental_sampoorna"),
])
def test_sarvam_transliteration_spellings_select(text, pid):
    pol, fin = turn(text)
    assert pol == pid and fin["status"] == "selected" and fin["lang"] == "hinglish"
