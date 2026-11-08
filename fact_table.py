"""Fact table: schema, loading and quote validation.

One file per policy in facts/<policy_id>.json (format 2):

    {"format": 2, "policy_id": ..., "insurer": ..., "product": ..., "source": ...,
     "rows": [{"plan": "ALL" | plan name, "attribute": one of ATTRIBUTES,
               "value": plain language value, "status": "stated" | "not_stated" | "unclear",
               "needs_extra_care": bool, "evidence": [{"page": physical page, "quote": verbatim}],
               "note": str, "verified": bool, "verified_by": str | None, "verified_on": str | None}]}

The JSON files are the single source of truth. The review CSV is generated from them
(import_facts.py --export) and a person's verification is written back with --apply.

Older files without "format" (facts/national_mediclaim.json) are read through a legacy
adapter until task 5 rebuilds them with quotes; they are reported, never validated as passing.
"""
import csv
import json
import re
import unicodedata
from functools import lru_cache

from config import FACTS_DIR, MANIFEST, POLICY_DIR

ATTRIBUTES = {
    "ped_waiting": "Pre-existing disease waiting period",
    "specific_disease_waiting": "Specific disease waiting period",
    "initial_waiting": "Initial waiting period",
    "moratorium": "Moratorium period",
    "room_rent": "Room rent limit",
    "icu_limit": "ICU limit",
    "copay": "Co-payment",
    "maternity": "Maternity cover",
    "ayush": "AYUSH cover",
    "daycare": "Day care treatment",
    "pre_post_hospitalisation": "Pre and post hospitalisation",
    "no_claim_bonus": "No claim bonus",
    "renewal": "Renewal terms",
    "sublimits": "Sub-limits",
    "cashless": "Cashless facility",
    "mental_illness": "Mental illness cover",
    "entry_age": "Entry age and family members",
    "sum_insured_options": "Sum insured options",
    "restoration_reload": "Restoration or reload of sum insured",
}
STATUSES = {"stated", "not_stated", "unclear"}
ROW_FIELDS = ["plan", "attribute", "value", "status", "needs_extra_care", "evidence", "note",
              "verified", "verified_by", "verified_on"]

# legacy (format 1) attribute names
LEGACY_NAMES = {"specific_waiting": "specific_disease_waiting", "pre_post": "pre_post_hospitalisation",
                "ncb": "no_claim_bonus"}


def manifest() -> dict[str, dict]:
    return {r["policy_id"]: r for r in csv.DictReader(open(MANIFEST, encoding="utf-8"))}


COVERAGE = {
    "en": "The fact table covers {k} of the {n} loaded documents. Not yet included: {names}.",
    "hinglish": "Fact table abhi {n} loaded documents mein se {k} ko cover karti hai. Abhi shamil nahi: {names}.",
    "hi": "फैक्ट टेबल अभी {n} लोड किए गए दस्तावेज़ों में से {k} को कवर करती है। अभी शामिल नहीं: {names}।",
}


def coverage_note(lang: str, covered: set[str]) -> str | None:
    """Comparison and ranking read only the fact table. When documents are loaded without fact rows,
    say so, so a shortlist of 5 is never read as the best of all loaded documents."""
    from policy_select import options
    missing = [o["label"] for o in options() if o["policy_id"] not in covered]
    if not missing:
        return None
    n = len(options())
    names = ", ".join(missing[:8]) + (f" (+{len(missing) - 8})" if len(missing) > 8 else "")
    return COVERAGE[lang].format(k=n - len(missing), n=n, names=names)


def _legacy_to_rows(f: dict) -> list[dict]:
    rows = []
    for key, a in f.get("attributes", {}).items():
        has = bool(a.get("value"))
        rows.append({"plan": "ALL", "attribute": LEGACY_NAMES.get(key, key),
                     "value": a.get("value") or "Not stated in the document",
                     "status": "stated" if has else "not_stated", "needs_extra_care": True,
                     "evidence": [{"page": a["page"], "quote": None}] if a.get("page") else [],
                     "note": f"Legacy row (clause {a.get('clause')}), no verbatim quote yet. Rebuilt in task 5.",
                     "verified": bool(f.get("verified")), "verified_by": f.get("verified_by"), "verified_on": None})
    return rows


def load_facts() -> list[dict]:
    """Every policy's facts as {policy_id, insurer, product, legacy, rows}."""
    out = []
    for p in sorted(FACTS_DIR.glob("*.json")):
        f = json.load(open(p, encoding="utf-8"))
        legacy = f.get("format") != 2
        out.append({"policy_id": f["policy_id"], "insurer": f.get("insurer", ""), "product": f.get("product", ""),
                    "legacy": legacy, "file": p.name,
                    "rows": _legacy_to_rows(f) if legacy else f["rows"]})
    return out


# ---------------------------------------------------------------- validation

QUOTE_MARKS = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
                             "“": '"', "”": '"', "„": '"', "″": '"'})


def norm(s: str) -> str:
    """Normalisation used to find a quote on its page: NFKC (ligatures), quote marks, case, whitespace.

    All whitespace is removed, not just collapsed, because PDF text extraction both inserts
    and drops spaces in justified text ("Upto10lakhs" against "Upto 10 lakhs"). Nothing else
    is relaxed: punctuation, digits and word order must match exactly.
    """
    s = unicodedata.normalize("NFKC", s).translate(QUOTE_MARKS).casefold()
    return re.sub(r"\s+", "", s)


@lru_cache(maxsize=None)
def page_texts(policy_id: str) -> tuple[str, ...]:
    """Normalised text of each physical page, in two reading orders (as stored and sorted by position)."""
    import pymupdf
    r = manifest()[policy_id]
    doc = pymupdf.open(POLICY_DIR / r["file"])
    return tuple(norm(pg.get_text("text")) + "\x00" + norm(pg.get_text("text", sort=True)) for pg in doc)


def schema_problems(f: dict) -> list[str]:
    probs = []
    if f["policy_id"] not in manifest():
        probs.append(f"{f['policy_id']}: not in the manifest")
    seen = set()
    for i, r in enumerate(f["rows"]):
        where = f"{f['policy_id']} row {i} ({r.get('plan')}/{r.get('attribute')})"
        missing = [k for k in ROW_FIELDS if k not in r]
        if missing:
            probs.append(f"{where}: missing fields {missing}")
            continue
        if r["attribute"] not in ATTRIBUTES:
            probs.append(f"{where}: unknown attribute")
        if r["status"] not in STATUSES:
            probs.append(f"{where}: bad status {r['status']!r}")
        if r["status"] == "stated" and not r["evidence"]:
            probs.append(f"{where}: stated with no evidence quote")
        key = (r["plan"], r["attribute"])
        if key in seen:
            probs.append(f"{where}: duplicate plan and attribute")
        seen.add(key)
        if r["verified"] and not (r["verified_by"] and r["verified_on"]):
            probs.append(f"{where}: verified without verified_by and verified_on")
    return probs


def quote_results(f: dict) -> list[dict]:
    """One result per evidence quote: found on its stated page or not, and where else it occurs."""
    texts = page_texts(f["policy_id"])
    out = []
    for r in f["rows"]:
        for e in r["evidence"]:
            q, page = e.get("quote"), e.get("page")
            res = {"policy_id": f["policy_id"], "plan": r["plan"], "attribute": r["attribute"],
                   "page": page, "quote": q, "found": False, "found_on": []}
            if q and isinstance(page, int) and 1 <= page <= len(texts):
                nq = norm(q)
                res["found"] = nq in texts[page - 1]
                if not res["found"]:
                    res["found_on"] = [i + 1 for i, t in enumerate(texts) if nq in t]
            out.append(res)
    return out
