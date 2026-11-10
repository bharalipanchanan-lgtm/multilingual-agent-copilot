"""Second hand review (2026-11-10, evening): rows redrafted after extract_facts.py learned to scan
every chunk for room rent, co-pay and entry age.

Each fix was read in the PDF. Rows stay verified: false until a person signs them off.
Run once, after the redraft: python facts/review/hand_review_2026_11_10b.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOTE = "Corrected in the second 2026-11-10 review against the PDF; not yet verified by a person."
NOT_IN_WORDING = "The policy wording does not state the entry age (it is in the brochure or prospectus)."


def row(attr, value, status="stated", page=None, quote=None, clause=None, numbers=None):
    return {"plan": "ALL", "attribute": attr, "value": value, "status": status, "needs_extra_care": status != "stated",
            "evidence": [{"page": page, "quote": quote, "clause": clause}] if quote else [], "note": NOTE,
            "numbers": numbers or {}, "verified": False, "verified_by": None, "verified_on": None}


FIX = {
    # the draft quoted the bariatric surgery condition ("18 years of age or older"), not eligibility
    ("bajaj_hcs_vital", "entry_age"): row("entry_age", NOT_IN_WORDING, "not_stated"),
    ("care_senior", "entry_age"): row("entry_age", NOT_IN_WORDING, "not_stated"),
    # the clause caps the room at a single private AC room; it is not "no limit"
    ("icici_elevate", "room_rent"): row("room_rent", "Room rent up to a Single Private AC room", page=32,
        quote="i. Room Rent charges up to Single Private AC room;", clause=None,
        numbers={"kind": "category", "category": "Single Private AC room"}),
    # 50% / 100% is a paid enhancement of the room limit on two plans, not the limit itself
    ("oriental_sampoorna", "room_rent"): row("room_rent", "Room rent differs by plan; the 50% or 100% figure is an optional paid enhancement. Read the plan table.", "unclear"),
    ("abhi_activ_one_max", "room_rent"): row("room_rent", "Room options are set by the plan chosen (single private room or shared); read the plan table.", "unclear"),
    # 4.19 is listed under "Optional Benefit" (from 4.14): the co-pay applies only if the customer chooses it
    ("niva_reassure2_platinum", "copay"): row("copay",
        "Co-payment is an optional benefit (clause 4.19, listed under Optional Benefit); it applies only if chosen. The wording does not print the percentages.",
        page=16, quote="Co-Payment: It is the percentage of admissible claim amount You would have to bear, Rest we will pay.", clause="4.19",
        numbers={"percent": None, "mandatory": False, "condition": "optional benefit, only if chosen"}),
}


def main():
    for (pid, attr), new in FIX.items():
        p = ROOT / "facts" / f"{pid}.json"
        f = json.load(open(p, encoding="utf-8"))
        old = next((r for r in f["rows"] if r["plan"] == "ALL" and r["attribute"] == attr), None)
        f["rows"] = [r for r in f["rows"] if not (r["plan"] == "ALL" and r["attribute"] == attr)] + [new]
        json.dump(f, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("fixed", pid, attr, "(was:", (old or {}).get("value", "-")[:60], ")")


if __name__ == "__main__":
    main()
