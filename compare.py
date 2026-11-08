"""Comparison across policies, answered only from the fact table in facts/*.json.

Free text search cannot compare documents reliably, so comparison questions are mapped to a
fixed attribute list and answered from the fact rows (fact_table.py), one row per plan where
plans differ. Rules:
  status not_stated  -> "Not stated in the document", never "not covered"
  status unclear     -> the recorded reading, marked unclear
  no row at all      -> "Not in the fact table yet", which says nothing about the document
  verified false     -> every answer says the values are not yet verified by a person
The table keeps the shape web/index.html expects (task 7 replaces the view with plan rows).
"""
import re

from fact_table import ATTRIBUTES, load_facts, manifest

KEYWORDS = [
    (r"diabet|sugar|madhumeh|मधुमेह|डायबिटीज", ["ped_waiting", "specific_disease_waiting"]),
    (r"pre.?existing|\bped\b|pehle se|पहले से", ["ped_waiting"]),
    (r"initial|first 30|30 day", ["initial_waiting"]),
    (r"specific|cataract|hernia|knee|joint", ["specific_disease_waiting"]),
    (r"moratorium", ["moratorium"]),
    (r"waiting", ["ped_waiting", "specific_disease_waiting", "initial_waiting"]),
    (r"room|kamra|कमरा", ["room_rent"]),
    (r"\bicu\b|intensive care", ["icu_limit"]),
    (r"co.?pay", ["copay"]),
    (r"maternity|pregnan|delivery|prasav|प्रसव|मातृत्व", ["maternity"]),
    (r"ayush|ayurved|homeo|आयुर्वेद", ["ayush"]),
    (r"day.?care", ["daycare"]),
    (r"pre.?hosp|post.?hosp|pre and post", ["pre_post_hospitalisation"]),
    (r"no.?claim|bonus|\bncb\b", ["no_claim_bonus"]),
    (r"renew", ["renewal"]),
    (r"sub.?limit|\bcap\b", ["sublimits"]),
    (r"cashless|network hospital", ["cashless"]),
    (r"mental|psychiatr|मानसिक", ["mental_illness"]),
    (r"entry age|\bage\b|umar|उम्र|family member", ["entry_age"]),
    (r"sum insured|cover amount", ["sum_insured_options"]),
    (r"restor|reload|recharge|refill|multiplier", ["restoration_reload"]),
]
NOTE = {
    "en": ("From the policy fact table.", "Not yet verified by a person against the PDF.",
           "Not stated in the document", "Not in the fact table yet", "unclear"),
    "hi": ("पॉलिसी फैक्ट टेबल से।", "अभी तक किसी व्यक्ति ने PDF से इसकी जाँच नहीं की है।",
           "दस्तावेज़ में नहीं दिया गया है", "फैक्ट टेबल में अभी नहीं है", "अस्पष्ट"),
    "hinglish": ("Policy fact table se.", "Abhi tak kisi ne PDF se verify nahi kiya hai.",
                 "Document mein nahi diya gaya hai", "Fact table mein abhi nahi hai", "unclear"),
}


def attrs_for(question: str) -> list[str]:
    q = question.lower()
    found: list[str] = []
    for rx, keys in KEYWORDS:
        if rx == r"waiting" and found:
            continue  # generic word only when nothing more specific matched
        if re.search(rx, q):
            found += [k for k in keys if k not in found]
    return found


def _cell_text(rows: list[dict], words) -> str:
    _, _, missing, absent, unclear = words
    if not rows:
        return absent
    parts = []
    for r in rows:
        v = missing if r["status"] == "not_stated" else r["value"]
        if r["status"] == "unclear":
            v = f"{v} ({unclear})"
        parts.append(v if r["plan"] == "ALL" else f"{r['plan']}: {v}")
    return "; ".join(parts)


def compare_answer(question: str, lang: str = "en", only: list[str] | None = None) -> dict:
    """only: policy ids the agent named ("compare SBI and Oriental"); None compares every policy."""
    facts = [f for f in load_facts() if not only or f["policy_id"] in only]
    keys = attrs_for(question)
    words = NOTE[lang]
    head, unverified = words[0], words[1]
    if not keys:
        names = ", ".join(ATTRIBUTES.values())
        return {"status": "not_stated", "answer": {
            "en": "I can compare policies on: " + names + ".",
            "hi": "मैं इन बिंदुओं पर पॉलिसी की तुलना कर सकता हूँ: " + names + "।",
            "hinglish": "Main in points par policies compare kar sakta hoon: " + names + ".",
        }[lang], "citations": [], "table": None}
    man = manifest()
    rows, cites, lines = [], [], [head]
    for f in facts:
        offset = int(man.get(f["policy_id"], {}).get("page_offset") or 0)
        name = f"{f['insurer']}: {f['product']}"  # product names alone do not say whose policy it is
        cells = []
        for k in keys:
            frows = [r for r in f["rows"] if r["attribute"] == k]
            page = next((e["page"] for r in frows for e in r["evidence"]), None)
            cells.append({"attr": k, "value": _cell_text(frows, words), "page": page,
                          "printed_page": page - offset if page else None,
                          "verified": bool(frows) and all(r["verified"] for r in frows)})
            for r in frows:
                if r["status"] == "not_stated" or not r["evidence"]:
                    continue
                e = r["evidence"][0]
                quotes = " ... ".join(x["quote"] for x in r["evidence"] if x.get("quote"))
                plan = "" if r["plan"] == "ALL" else f" ({r['plan']})"
                cites.append({"n": len(cites) + 1, "policy_id": f["policy_id"], "product": name,
                              "section": f"{name}: {ATTRIBUTES[k]}{plan}", "page": e["page"],
                              "printed_page": e["page"] - offset, "quote": e.get("quote") or r["value"],
                              "text": f"{r['value']}\n\nFrom the policy: {quotes}" if quotes else r["value"]})
            lines.append(f"{name}: {ATTRIBUTES[k]}: {cells[-1]['value']}"
                         + (f" (page {cells[-1]['printed_page']})" if page else ""))
        rows.append({"policy_id": f["policy_id"], "product": name, "insurer": f["insurer"],
                     "verified": all(c["verified"] for c in cells), "cells": cells})
    if any(not r["verified"] for r in rows):
        lines.append(unverified)
    from fact_table import coverage_note
    note = coverage_note(lang, {f["policy_id"] for f in load_facts()})
    if note and not only:
        lines.append(note)
    if len(rows) == 1:
        lines.append({"en": "Only one policy is loaded, so there is nothing to compare it with yet.",
                      "hi": "अभी केवल एक पॉलिसी लोड है, इसलिए तुलना के लिए दूसरी पॉलिसी नहीं है।",
                      "hinglish": "Abhi sirf ek policy loaded hai, isliye compare karne ke liye doosri policy nahi hai."}[lang])
    return {"status": "compared", "answer": "\n".join(lines), "citations": cites,
            "table": {"attributes": [ATTRIBUTES[k] for k in keys], "rows": rows}}
