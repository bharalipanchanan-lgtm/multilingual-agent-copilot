"""Look-alike products, withdrawn products, the customer fit and quick answers. No model is loaded."""
import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chat import converse  # noqa: E402
from fit import add_months, check, fit_answer, is_need, profile  # noqa: E402
from policy_select import differences, mentioned, one_family, options, stopped_note  # noqa: E402
from quick import topic  # noqa: E402


def turn(text, current=None):
    evs = list(converse(text, current, gen=None))
    pol = next((e["policy_id"] for e in evs if e["type"] == "policy"), None)
    return pol, evs[-1]


# ---------------------------------------------------------------- which exact product

HDFC = {"hdfc_optima_secure", "hdfc_optima_restore", "hdfc_optima_senior"}


@pytest.mark.parametrize("text,ids", [
    ("HDFC health policy dekhna hai", HDFC),
    ("Optima", HDFC),
    ("ReAssure", {"niva_reassure", "niva_reassure2_platinum", "niva_reassure3"}),
    ("star health", {"star_super_star", "star_health_premier", "star_diabetes_safe", "star_super_surplus_gold"}),
])
def test_insurer_name_alone_names_the_family(text, ids):
    from policy_select import narrow_by_category
    found, rest = mentioned(text)
    found = narrow_by_category(found, rest)
    assert set(found) == ids and one_family(found)


@pytest.mark.parametrize("text,pid", [
    ("Optima Restore", "hdfc_optima_restore"),
    ("HDFC Optima Senior room rent", "hdfc_optima_senior"),
    ("ReAssure 2.0", "niva_reassure2_platinum"),
    ("Care Supreme", "care_supreme"),
    ("Care Senior", "care_senior"),
])
def test_specific_name_narrows_to_one(text, pid):
    assert mentioned(text)[0] == [pid]


def test_day_care_does_not_name_care_health():
    assert mentioned("day care treatment kya hai")[0] == []


def test_family_asks_which_exact_product_with_a_difference_each():
    pol, fin = turn("HDFC health")
    assert pol is None and fin["status"] == "choose_policy" and fin.get("which_product")
    assert {o["policy_id"] for o in fin["options"]} == HDFC
    assert all(o["differs"] for o in fin["options"])
    assert len({o["differs"] for o in fin["options"]}) == 3          # the lines tell them apart


def test_family_question_is_held_until_the_product_is_chosen():
    _, fin = turn("HDFC mein room rent kitna hai?")
    assert fin["status"] == "choose_policy" and fin["pending"] is True


def test_family_keeps_the_product_in_use():
    pol, fin = turn("HDFC", current="hdfc_optima_restore")
    assert fin["status"] == "selected" and fin["policy_id"] == "hdfc_optima_restore"


def test_two_insurers_are_still_ambiguous_not_a_family():
    found, _ = mentioned("SBI or United India")
    assert not one_family(found)


# ---------------------------------------------------------------- stopped products

def test_withdrawn_product_is_marked_and_names_its_replacement():
    note = stopped_note("niva_reassure", "en")
    assert "no longer sold" in note and "ReAssure 2.0" in note
    assert stopped_note("niva_reassure2_platinum", "en") is None


def test_selecting_a_withdrawn_product_warns():
    _, fin = turn("ReAssure 1.0")
    assert fin["status"] == "selected" and "no longer sold" in fin["answer"]


def test_withdrawn_options_are_listed_last():
    opts = options(["niva_reassure", "niva_reassure2_platinum", "niva_reassure3"])
    assert opts[-1]["policy_id"] == "niva_reassure" and opts[-1]["status"] == "withdrawn"
    assert "stopped" in differences([o["policy_id"] for o in opts])["niva_reassure"]


# ---------------------------------------------------------------- reading the customer

@pytest.mark.parametrize("text,age,member,cond,room", [
    ("Mother is 50, has diabetes, wants room rent more than 10,000", 50, "mother", ["diabetes"], 10000),
    ("mummy 50 saal, sugar hai, room rent 10000 se upar chahiye", 50, "mother", ["diabetes"], 10000),
    ("माँ 50 साल, डायबिटीज़, रूम रेंट 10,000 से ऊपर", 50, "mother", ["diabetes"], 10000),
    ("father aged 62 with BP, private room", 62, "father", ["hypertension"], None),
    ("for my wife 34, room rent 5k", 34, "spouse", [], 5000),
])
def test_profile(text, age, member, cond, room):
    p = profile(text)
    assert (p["age"], p["member"], p["conditions"], p["room_rent"]) == (age, member, cond, room)


def test_room_amount_is_not_read_as_age():
    assert profile("room rent 10,000, mother")["age"] is None


def test_sum_insured_and_start_date():
    p = profile("mother 50, 10 lakh cover, policy starts 1 December 2026", today=dt.date(2026, 11, 10))
    assert p["sum_insured"] == 1e6 and p["start"] == dt.date(2026, 12, 1)


@pytest.mark.parametrize("text,need", [
    ("Mother is 50, has diabetes, wants room rent more than 10,000", True),
    ("mother 62 private room", True),
    ("Diabetes ke liye waiting period kitna hai?", False),       # a clause question, not a customer
    ("What is the room rent limit?", False),
])
def test_is_need(text, need):
    assert is_need(text) is need


def test_add_months():
    assert add_months(dt.date(2026, 11, 10), 36) == dt.date(2029, 11, 10)
    assert add_months(dt.date(2026, 1, 31), 1) == dt.date(2026, 2, 28)


# ---------------------------------------------------------------- checking a product (synthetic facts)

def prod(**num):
    rows = {a: {"attribute": a, "status": "stated", "value": str(v), "numbers": v, "verified": False,
                "evidence": [{"page": 1, "quote": "q"}]} for a, v in num.items()}
    return {"policy_id": "x", "insurer": "Nobody", "product": "Test", "label": "Test", "display": "Nobody Test", "status": "active",
            "replaced_by": "", "top_up": False, "brochure": False, "offset": 0, "rows": rows}


P = profile("Mother is 50, has diabetes, wants room rent more than 10,000")


def test_entry_age_above_maximum_fails():
    r = check(prod(entry_age={"adult_min_years": 18, "adult_max_years": 45}), P)
    assert not r["fits"] and "up to 45" in r["fails"][0]


def test_senior_only_product_fails_for_50():
    r = check(prod(entry_age={"adult_min_years": 61, "adult_max_years": None}), P)
    assert not r["fits"] and "from 61" in r["fails"][0]


def test_room_rent_cap_below_need_fails():
    assert not check(prod(room_rent={"kind": "rupees", "rupees_per_day": 5000}), P)["fits"]
    assert check(prod(room_rent={"kind": "no_limit"}), P)["fits"]


def test_percent_room_rent_says_what_cover_is_needed():
    r = check(prod(room_rent={"kind": "percent_si", "percent_of_si": 1}), P)
    assert r["fits"] and any("10 lakh" in c for c in r["cautions"])


def test_missing_fact_is_never_a_pass():
    r = check(prod(), P)
    assert r["good"] == [] and any("not in the fact table" in c for c in r["cautions"])


def test_shorter_diabetes_wait_scores_higher():
    a = check(prod(ped_waiting={"months": 12}, room_rent={"kind": "no_limit"}), P)
    b = check(prod(ped_waiting={"months": 36}, room_rent={"kind": "no_limit"}), P)
    assert a["score"] > b["score"]


def test_need_answer_shows_at_most_two_and_no_withdrawn_or_top_up():
    out = fit_answer("Mother is 50, has diabetes, wants room rent more than 10,000", "en", today=dt.date(2026, 11, 10))
    best = out["fit"]["best"]
    assert len(best) <= 2 and all(r["fits"] for r in best)
    assert not any(r["policy_id"] in ("niva_reassure", "tata_medisenior", "star_super_surplus_gold") for r in best)
    if best:
        kit = out["fit"]["kit"]
        assert kit["whatsapp"] and kit["papers"] and kit["dont"]
        assert any("premium" in d.lower() for d in kit["dont"])


# ---------------------------------------------------------------- quick answers

@pytest.mark.parametrize("text,attrs", [
    ("What is the room rent limit?", ["room_rent"]),
    ("room rent kitna hai", ["room_rent"]),
    ("waiting period kya hai?", ["initial_waiting", "ped_waiting", "specific_disease_waiting"]),
    ("PED waiting period?", ["ped_waiting"]),
    ("age limit kya hai", ["entry_age"]),
    ("Is there a co-pay?", ["copay"]),
])
def test_simple_questions_are_quick(text, attrs):
    assert topic(text) == attrs


@pytest.mark.parametrize("text", [
    "Cataract ka waiting period kitna hai?", "Is robotic surgery covered?", "Is AYUSH treatment covered?",
    "Diabetes ke liye waiting period kitna hai?", "Kya ICU charges par bhi room rent ka cap lagta hai?",
])
def test_hard_questions_go_to_the_clauses(text):
    assert topic(text) is None


# ---------------------------------------------------------------- limits and list items

def test_missed_limit_is_added_verbatim():
    from answer import missed_limit
    clauses = [{"text": "vii. Robotic surgeries viii. Stereotactic radio surgeries Special condition applicable for robotic "
                        "surgeries: A limit of maximum INR 1 Lac will apply to all robotic surgeries, except the following: i. x"}]
    n, sent = missed_limit("Is robotic surgery covered?", "Yes, robotic surgery is covered [1].", clauses)
    assert n == 1 and "INR 1 Lac" in sent
    # the answer that already gives the cap needs nothing added; a citation [1] is not the figure 1
    assert missed_limit("Is robotic surgery covered?", "Covered up to INR 1 Lac [1].", clauses) is None


def test_lettered_list_items_stay_in_the_text():
    from parse import build_chunks
    lines = ["3.1.5 Modern Treatment", "expenses for treatment taken through following advance technology methods:",
             "A. Uterine Artery Embolization and HIFU", "B. Balloon Sinuplasty", "G. Robotic surgeries", "H. Stereotactic radio surgeries"]
    text = " ".join(c["text"] for c in build_chunks([lines]))
    assert "Robotic surgeries" in text and "Balloon Sinuplasty" in text
