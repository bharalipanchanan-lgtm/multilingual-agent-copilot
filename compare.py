"""Comparison across policies, answered only from the fact table in facts/*.json.

Free text search cannot compare 20 documents reliably, so comparison questions are
mapped to a fixed attribute list and answered from values a human has checked against
the PDF. Values not yet verified are flagged as such in every answer.
"""
import json
import re

from config import FACTS_DIR

ATTRS = {
    "ped_waiting": "Pre-existing disease waiting period",
    "specific_waiting": "Specific disease waiting period",
    "initial_waiting": "Initial waiting period",
    "room_rent": "Room rent cap",
    "copay": "Co-payment",
    "maternity": "Maternity cover",
    "ayush": "AYUSH cover",
    "daycare": "Day care procedures",
    "pre_post": "Pre and post hospitalisation",
    "ncb": "No claim bonus",
    "renewal": "Renewal terms",
    "sublimits": "Sub-limits",
}
KEYWORDS = [
    (r"diabet|sugar|madhumeh|मधुमेह|डायबिटीज", ["ped_waiting", "specific_waiting"]),
    (r"pre.?existing|\bped\b|pehle se|पहले से", ["ped_waiting"]),
    (r"initial|first 30|30 day", ["initial_waiting"]),
    (r"specific|cataract|hernia|knee|joint", ["specific_waiting"]),
    (r"waiting", ["ped_waiting", "specific_waiting", "initial_waiting"]),
    (r"room|icu|kamra|कमरा", ["room_rent"]),
    (r"co.?pay", ["copay"]),
    (r"maternity|pregnan|delivery|prasav|प्रसव|मातृत्व", ["maternity"]),
    (r"ayush|ayurved|homeo|आयुर्वेद", ["ayush"]),
    (r"day.?care", ["daycare"]),
    (r"pre.?hosp|post.?hosp|pre and post", ["pre_post"]),
    (r"no.?claim|bonus|\bncb\b", ["ncb"]),
    (r"renew", ["renewal"]),
    (r"sub.?limit|cap", ["sublimits"]),
]
NOTE = {
    "en": ("From the policy fact table.", "Not yet verified by a human against the PDF.", "Not stated in the document."),
    "hi": ("पॉलिसी फैक्ट टेबल से।", "अभी तक किसी व्यक्ति ने PDF से इसकी जाँच नहीं की है।", "दस्तावेज़ में नहीं दिया गया है।"),
    "hinglish": ("Policy fact table se.", "Abhi tak kisi ne PDF se verify nahi kiya hai.", "Document mein nahi diya gaya hai."),
}


def load_facts() -> list[dict]:
    return [json.load(open(p, encoding="utf-8")) for p in sorted(FACTS_DIR.glob("*.json"))]


def attrs_for(question: str) -> list[str]:
    q = question.lower()
    found: list[str] = []
    for rx, keys in KEYWORDS:
        if rx == r"waiting" and found:
            continue  # generic word only when nothing more specific matched
        if re.search(rx, q):
            found += [k for k in keys if k not in found]
    return found


def compare_answer(question: str, lang: str = "en") -> dict:
    facts = load_facts()
    keys = attrs_for(question)
    head, unverified, missing = NOTE[lang]
    if not keys:
        return {"status": "not_stated", "answer": {
            "en": "I can compare policies on: " + ", ".join(ATTRS.values()) + ".",
            "hi": "मैं इन बिंदुओं पर पॉलिसी की तुलना कर सकता हूँ: " + ", ".join(ATTRS.values()) + "।",
            "hinglish": "Main in points par policies compare kar sakta hoon: " + ", ".join(ATTRS.values()) + ".",
        }[lang], "citations": [], "table": None}
    rows, cites = [], []
    for f in facts:
        cells = []
        for k in keys:
            a = f["attributes"].get(k, {})
            cells.append({"attr": k, "value": a.get("value") or missing, "clause": a.get("clause"),
                          "printed_page": a.get("printed_page"), "page": a.get("page")})
            if a.get("value"):
                cites.append({"n": len(cites) + 1, "policy_id": f["policy_id"], "product": f["product"],
                              "section": f"Clause {a.get('clause')}", "page": a.get("page"),
                              "printed_page": a.get("printed_page"), "quote": a["value"], "text": a["value"]})
        rows.append({"policy_id": f["policy_id"], "product": f["product"], "insurer": f["insurer"],
                     "verified": f.get("verified", False), "cells": cells})
    lines = [head]
    for r in rows:
        for c in r["cells"]:
            page = f" (clause {c['clause']}, page {c['printed_page']})" if c["clause"] else ""
            lines.append(f"{r['product']}: {ATTRS[c['attr']]}: {c['value']}{page}")
    if any(not r["verified"] for r in rows):
        lines.append(unverified)
    if len(rows) == 1:
        lines.append({"en": "Only one policy is loaded, so there is nothing to compare it with yet.",
                      "hi": "अभी केवल एक पॉलिसी लोड है, इसलिए तुलना के लिए दूसरी पॉलिसी नहीं है।",
                      "hinglish": "Abhi sirf ek policy loaded hai, isliye compare karne ke liye doosri policy nahi hai."}[lang])
    return {"status": "compared", "answer": "\n".join(lines), "citations": cites,
            "table": {"attributes": [ATTRS[k] for k in keys], "rows": rows}}
