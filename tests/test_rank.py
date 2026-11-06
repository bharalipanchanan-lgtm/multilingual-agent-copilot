"""Ranking (rank.py): reading figures from fact values, preferences, and the order it gives."""
import random
import time

import pytest

from answer import route
from rank import (candidates, copay_score, durations_months, maternity_score, preferences, rank, rank_answer,
                  room_rent_score)


def test_durations_skip_ages_and_continuity():
    assert durations_months("12 months if below 45 years, 24 months if above 45") == [12, 24]
    assert durations_months("30 days from first policy commencement; not applicable if continuous "
                            "coverage for more than 12 months") == [1]
    assert durations_months("90 days: diabetes. 1 year: hernia. 3 years: joint replacement") == [3, 12, 36]


def test_readers():
    assert room_rent_score("No room rent capping")[0] == 1
    assert room_rent_score("Actual expenses incurred per day (no cap)")[0] == 1
    assert room_rent_score("Up to 10 lakh sum insured: 1% of sum insured per day. Above 10 lakh: actual expenses incurred")[0] == 0.6
    assert room_rent_score("1% of sum insured per day")[0] == 0.3
    assert copay_score("Not applicable")[0] == 1
    assert copay_score("No mandatory co-pay. Optional voluntary co-payment of 5%")[0] == 1
    assert copay_score("10% co-payment when treated in a non-network hospital")[0] == 0.7
    assert maternity_score("Excluded (exclusion code Excl 18)")[0] == 0
    assert maternity_score("Not available")[0] == 0
    assert maternity_score("Covered: up to 5% of sum insured")[0] == 1


def test_preferences_from_the_users_example():
    p = preferences("He would like to waive off any kind of waiting period. He is not concerned about the premium. "
                    "He wants the best claim ratio.")
    assert {"ped_waiting", "specific_waiting", "initial_waiting", "claims"} <= set(p["weights"])
    assert p["premium"] == "ignored" and not p["balanced"]


def test_preferences_hinglish_and_negation():
    p = preferences("maternity cover chahiye, co-pay ki chinta nahi")
    assert p["must"] == ["maternity"] and "copay" not in p["weights"]
    assert preferences("best policy")["balanced"]
    assert preferences("sasti policy chahiye")["premium"] == "asked"


def test_routes():
    assert route("Which policy will work best for him if he wants no waiting period?") == "recommend"
    assert route("Sabse acchi policy kaunsi hai?") == "recommend"
    assert route("सबसे अच्छी पॉलिसी कौन सी है?") == "recommend"
    assert route("Compare the diabetes waiting period across policies") == "compare"
    assert route("What is the premium for a 45 year old for 10 lakh?") == "premium"


def test_waiting_and_claims_ranking():
    res = rank("no waiting periods and best claim ratio, premium does not matter")
    top = res["ranked"][0]
    assert top["policy_id"] == "oriental_sampoorna" and "ELITE" in top["plan"]
    # every scored part names where it came from
    for r in res["ranked"]:
        for p in r["parts"]:
            if p["score"] > 0:
                assert p.get("printed_page") is not None or p.get("source"), p
    scores = [r["score"] for r in res["ranked"]]
    assert scores == sorted(scores, reverse=True)


def test_must_have_maternity_drops_policies_without_it():
    res = rank("maternity must be covered")
    assert {r["policy_id"] for r in res["ranked"]} == {"oriental_sampoorna"}
    assert all("maternity" in d["reason"] for d in res["dropped"])


def test_missing_fact_scores_zero_not_inferred():
    # United India does not state a no claim bonus: it must score 0 and be listed as missing
    res = rank("best no claim bonus")
    ui = next(r for r in res["ranked"] if r["policy_id"] == "united_india")
    assert ui["score"] == 0 and any("not stated" in m for m in ui["missing"])


def test_identical_plans_are_merged():
    res = rank("no waiting period")
    ui = [r for r in res["ranked"] if r["policy_id"] == "united_india"]
    assert len(ui) == 1 and "," in ui[0]["plan"]


def test_answer_text_is_honest():
    out = rank_answer("best claim ratio", "en")
    assert out["status"] == "ranked"
    assert "incurred claims ratio" in out["answer"] and "not a claim settlement ratio" in out["answer"]
    assert "not advice" in out["answer"]
    assert rank_answer("सबसे अच्छी पॉलिसी", "hi")["answer"].startswith("पॉलिसी फैक्ट टेबल")


def test_scales_to_300_policies():
    """A synthetic catalogue of 300 policies (test only, never shown): ranking stays fast and
    absolute scales keep a policy's score independent of the others."""
    real = {c["policy_id"]: c for c in candidates()}
    rng = random.Random(7)
    facts = []
    for i in range(300):
        months = rng.choice([12, 24, 36, 48])
        facts.append({"policy_id": f"synthetic_{i}", "insurer": "National Insurance", "product": f"Synthetic {i}",
                      "rows": [{"plan": "ALL", "attribute": "ped_waiting", "status": "stated",
                                "value": f"{months} months of continuous coverage", "verified": False,
                                "evidence": [{"page": 10, "quote": "x"}]}]})
    t0 = time.time()
    res = rank("no pre-existing disease waiting period", facts=facts)
    assert time.time() - t0 < 2
    assert len(res["ranked"]) == 300
    # 12 months on a 48 month scale scores the same alone as among 300 others (absolute scales)
    alone = rank("no pre-existing disease waiting period", facts=[f for f in facts if "12 months" in f["rows"][0]["value"]][:1])
    assert res["ranked"][0]["score"] == alone["ranked"][0]["score"] > 0
    assert real  # the real catalogue still loads


def test_negation_stays_in_its_clause():
    p = preferences("Which policy works best for a customer who wants no waiting period and a good claims record? "
                    "Premium does not matter.")
    assert "claims" in p["weights"] and p["premium"] == "ignored"
    p = preferences("He wants no waiting period and he does not care about co-pay")
    assert "ped_waiting" in p["weights"] and "copay" not in p["weights"]
