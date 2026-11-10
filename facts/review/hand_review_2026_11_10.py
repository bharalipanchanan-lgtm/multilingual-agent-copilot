"""Hand review of the drafted fact rows the customer fit depends on (2026-11-10).

Each fix was read in the PDF. Quotes are verbatim and tests/test_fact_quotes.py checks them on
their page. Rows stay verified: false until a person signs them off (import_facts.py --apply).
Run once: python facts/review/hand_review_2026_11_10.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOTE = "Corrected in the 2026-11-10 review against the PDF; not yet verified by a person."
BARIATRIC = "has to be 18 years of age or older"


def row(attr, value, status="stated", page=None, quote=None, clause=None, numbers=None, plan="ALL", note=NOTE):
    return {"plan": plan, "attribute": attr, "value": value, "status": status, "needs_extra_care": status != "stated",
            "evidence": [{"page": page, "quote": quote, "clause": clause}] if quote else [], "note": note,
            "numbers": numbers or {}, "verified": False, "verified_by": None, "verified_on": None}


NOT_IN_WORDING = "The policy wording does not state the entry age (it is in the brochure or prospectus)."
FIX = {
    # entry age: the drafts quoted the bariatric surgery condition or an add-on, not eligibility
    ("care_senior", "entry_age"): row("entry_age", NOT_IN_WORDING, "not_stated"),
    ("care_supreme", "entry_age"): row("entry_age", NOT_IN_WORDING, "not_stated"),
    ("tata_elder_care", "entry_age"): row("entry_age", NOT_IN_WORDING, "not_stated"),
    ("icici_elevate", "entry_age"): row("entry_age", NOT_IN_WORDING + " The age 65 in the draft is for the BeFit add-on.", "not_stated"),
    ("niva_reassure3", "ped_waiting"): row("ped_waiting", "The brochure gives only the option to reduce the pre-existing disease wait to 12 or 24 months; the base wait is not stated.", "not_stated"),
    ("star_super_star", "ped_waiting"): row("ped_waiting", "36 months of continuous coverage (can be reduced to 24 or 12 months as an option at first purchase)", page=18,
        quote="shall be excluded until the expiry of 36 months of continuous coverage after the date of inception of the first policy with insurer",
        clause="Excl 01", numbers={"months": 36}),
    ("hdfc_optima_senior", "ped_waiting"): row("ped_waiting", "36 months of continuous coverage", page=13,
        quote="shall be excluded until the expiry of 36 months of continuous coverage after the date of inception of the first policy with insurer",
        clause="Excl01", numbers={"months": 36}),
    ("newindia_premier_mediclaim", "ped_waiting"): row("ped_waiting", "36 months of continuous coverage", page=17,
        quote="shall be excluded until the expiry of 36 months of continuous coverage after the date of inception of the first policy with us",
        clause="4.1", numbers={"months": 36}),
    ("digit_double_wallet", "ped_waiting"): row("ped_waiting", "3 years for most plans, 1 year for some, as per the plan in the schedule", page=68,
        quote="Pre-existing Waiting Period 3 years 3 years 3 years 3 years 1 year", clause="plan table", numbers={"months": 36}),
    ("acko_platinum_health", "ped_waiting"): row("ped_waiting", "Set in the policy schedule; the wording does not give the number of months.", "not_stated"),
    # Diabetes Safe: diabetes complications are Section 1, outside the PED exclusion (Sections 2 and 4)
    ("star_diabetes_safe", "specific_disease_waiting"): row("specific_disease_waiting",
        "Section 1 (complications of diabetes): Plan B waits 12 months; the PED exclusion of 36 months applies to Sections 2 and 4, not to Section 1.",
        page=4, quote="Applicable for Section 1 under Plan B A. Expenses related to the treatment of following listed systems shall be excluded until the expiry of 12 months",
        clause="Excl 02", numbers={"months_max": 12, "diabetes_months": 12, "diabetes_overrides_ped": True}),
    ("star_health_premier", "room_rent"): row("room_rent", "Up to 1% of sum insured, maximum Rs 20,000 per day", page=None, quote=None, status="pending"),
    ("star_health_premier", "copay"): row("copay", "20% co-payment on every claim for insured persons whose age at entry is above 65 years", page=6,
        quote="Each and every claim under the Policy shall be subject to a Copayment of 20%", clause=None,
        numbers={"percent": 20, "mandatory": False, "condition": "only if age at entry is above 65"}),
    ("digit_double_wallet", "copay"): None,   # numbers fixed below
    ("abhi_activ_one_max", "room_rent"): row("room_rent", "Room options are set by the plan chosen (single private room or shared); read the plan table.", "unclear"),
}


def main():
    for (pid, attr), new in FIX.items():
        p = ROOT / "facts" / f"{pid}.json"
        f = json.load(open(p, encoding="utf-8"))
        old = next((r for r in f["rows"] if r["plan"] == "ALL" and r["attribute"] == attr), None)
        if new is None or (new["status"] == "pending"):
            continue
        f["rows"] = [r for r in f["rows"] if not (r["plan"] == "ALL" and r["attribute"] == attr)] + [new]
        json.dump(f, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("fixed", pid, attr, "(was:", (old or {}).get("value", "-")[:60], ")")

    def edit(pid, fn):
        p = ROOT / "facts" / f"{pid}.json"
        f = json.load(open(p, encoding="utf-8"))
        fn(f["rows"])
        json.dump(f, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    def setnum(pid, attr, nums, plan="ALL", note=True):
        def fn(rows):
            for r in rows:
                if r["attribute"] == attr and r["plan"] == plan:
                    r["numbers"] = nums
                    if note and NOTE not in r["note"]:
                        r["note"] = (r["note"] + " " + NOTE).strip()
        edit(pid, fn)

    # any other entry age row resting on the bariatric clause is not an entry age
    for p in (ROOT / "facts").glob("*.json"):
        f = json.load(open(p, encoding="utf-8"))
        hit = False
        for r in f["rows"]:
            if r["attribute"] == "entry_age" and any(BARIATRIC in (e.get("quote") or "") for e in r["evidence"]):
                r.update(row("entry_age", NOT_IN_WORDING, "not_stated"))
                hit = True
        if hit:
            json.dump(f, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print("entry age: bariatric quote removed in", p.stem)

    setnum("star_health_premier", "room_rent", {"kind": "percent_si", "percent_of_si": 1, "max_rupees_per_day": 20000})
    setnum("digit_double_wallet", "copay", {"percent": 10, "mandatory": False, "condition": "only without address proof for the pricing zone"})
    setnum("hdfc_optima_senior", "copay", {"percent": 15, "mandatory": False, "condition": "if a single or higher room is taken"})
    setnum("niva_reassure2_platinum", "copay", {"percent": None, "mandatory": None, "condition": "rates vary by sum insured and age"})
    # the hand built rows of the first five policies get the plain numbers the fit reads
    for plan, ped, room, cp in [("PREMIUM", 36, {"kind": "percent_si", "percent_of_si": 1}, 10),
                                ("ELITE", 24, {"kind": "percent_si", "percent_of_si": 1}, 5),
                                ("ROYAL", 24, {"kind": "no_limit"}, 0)]:
        setnum("oriental_sampoorna", "ped_waiting", {"months": ped}, plan)
        setnum("oriental_sampoorna", "room_rent", room, plan)
        setnum("oriental_sampoorna", "copay", {"percent": cp, "mandatory": False, "condition": "only in a non-network hospital" if cp else None}, plan)
    for pid in ("oriental_sampoorna", "royal_multiplier", "united_india", "sbi_retail_health"):
        setnum(pid, "initial_waiting", {"days": 30})
    setnum("oriental_sampoorna", "specific_disease_waiting", {"months_max": 24, "cataract_months": 24})
    setnum("royal_multiplier", "ped_waiting", {"months": 36})
    setnum("royal_multiplier", "specific_disease_waiting", {"months_max": 24, "cataract_months": 24})
    setnum("royal_multiplier", "room_rent", {"kind": "no_limit"})
    setnum("royal_multiplier", "copay", {"percent": 0, "mandatory": False})
    setnum("united_india", "ped_waiting", {"months": 48})
    setnum("united_india", "specific_disease_waiting", {"months_max": 24, "cataract_months": 24})
    setnum("united_india", "room_rent", {"kind": "percent_si", "percent_of_si": 1})
    setnum("united_india", "copay", {"percent": 0, "mandatory": False})
    setnum("sbi_retail_health", "ped_waiting", {"months": 48})
    setnum("sbi_retail_health", "specific_disease_waiting", {"months_max": 36, "cataract_months": 24, "diabetes_months": 3})
    setnum("sbi_retail_health", "room_rent", {"kind": "percent_si", "percent_of_si": 1})
    setnum("sbi_retail_health", "copay", {"percent": 10, "mandatory": False, "condition": "only in a non-network hospital"})


if __name__ == "__main__":
    sys.exit(main())
