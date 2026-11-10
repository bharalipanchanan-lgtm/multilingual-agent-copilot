"""Rank policies (and their plans) against what a customer cares about.

  python rank.py "no waiting periods, best claim ratio, premium does not matter"

Input is the agent's request in English, Hindi or Hinglish. Output is a ranked list in which
every score is traceable to a fact table row (value, page, verbatim quote) or to the IRDAI
figure in data/insurers.json. Rules that keep the ranking honest:

  1. Scores come only from the fact table and the IRDAI file, never from free text search
     or a model. The same input always gives the same ranking.
  2. A fact the document does not state, or one not in the fact table yet, scores 0 for that
     criterion and is listed as missing. A gap never lifts a policy above one with a known value.
  3. Every number used is shown next to the text it was read from, so a reviewer can check it.
  4. Premium is not in the policy wordings, so the ranking cannot use it and says so.
  5. The claims measure is IRDAI's incurred claims ratio (ICR), the only insurer-wise figure
     IRDAI publishes. The answer names it as such; it is not a claim settlement ratio.

Scales are absolute (for example 0 to 48 months), not relative to the policies loaded, so a
policy keeps the same score when the catalogue grows from 5 to 300 policies.
"""
import json
import re
import sys
from dataclasses import dataclass, field
from functools import lru_cache

from config import ROOT
from fact_table import ATTRIBUTES, load_facts, manifest

INSURERS_FILE = ROOT / "data" / "insurers.json"

# ------------------------------------------------------------------ reading numbers from fact values

_DUR = re.compile(r"(\d+(?:\.\d+)?)\s*(days?|months?|years?|yrs?)\b", re.I)


_AGE_BEFORE = re.compile(r"(below|above|under|over|aged?|upto|up to|than)\s*$", re.I)
_AGE_AFTER = re.compile(r"^\s*(of age|old|and above|\+)", re.I)
_NOT_A_WAIT = re.compile(r"(continuous (coverage|cover) (for )?(of )?(more than|over)\s*)$", re.I)


def durations_months(text: str) -> list[float]:
    """Every waiting duration in the text, in months ("90 days" -> 3, "2 years" -> 24).
    Ages ("below 45 years") and continuity conditions ("continuous coverage for more than
    12 months") are not waiting periods and are skipped."""
    out = []
    for m in _DUR.finditer(text):
        before, after = text[:m.start()], text[m.end():]
        if _AGE_BEFORE.search(before) or _AGE_AFTER.match(after) or _NOT_A_WAIT.search(before):
            continue
        n, u = float(m.group(1)), m.group(2).lower()
        out.append(n / 30 if u.startswith("day") else n * 12 if u.startswith(("year", "yr")) else n)
    return out


def longest_wait(text: str) -> float | None:
    """The longest waiting period stated. Age dependent values take the longer one, so the
    score is what every customer can rely on."""
    d = durations_months(text)
    return max(d) if d else None


def room_rent_score(text: str) -> tuple[float, str] | None:
    t = text.lower()
    if re.search(r"no room rent cap|no cap|without any cap|actual expenses incurred per day", t):
        return 1.0, "no cap"
    if "above" in t and "actual" in t:  # capped up to some sum insured, actual above it
        return 0.6, "capped below a sum insured, no cap above it"
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", t)
    if m:
        return 0.3, f"capped at {m.group(1)}% of sum insured per day"
    return None


def copay_score(text: str) -> tuple[float, str] | None:
    t = text.lower()
    if re.match(r"\s*(not applicable|nil|none)\b", t) or t.startswith("no mandatory co-pay"):
        return 1.0, "no mandatory co-pay"
    if "non-network" in t:
        m = re.search(r"(\d+)\s*%", t)
        return 0.7, f"{m.group(1) if m else 'some'}% co-pay only in non-network hospitals"
    m = re.search(r"(\d+)\s*%", t)
    if m:
        return max(0.0, 1 - int(m.group(1)) / 50), f"{m.group(1)}% co-pay"
    return None


def maternity_score(text: str) -> tuple[float, str] | None:
    t = text.lower()
    if re.match(r"\s*(excluded|not covered|not available)", t):
        return 0.0, "not covered"
    if t.startswith("covered"):
        return 1.0, "covered"
    return None


def bonus_score(text: str) -> tuple[float, str] | None:
    caps = [int(x) for x in re.findall(r"(?:up to|maximum|max)\s*(\d+)\s*%", text, re.I)]
    if caps:
        cap = max(caps)
        return min(cap, 100) / 100, f"bonus up to {cap}% of sum insured"
    return None


# ------------------------------------------------------------------ criteria

@dataclass
class Criterion:
    key: str
    label: str
    attribute: str | None          # fact table attribute, or None for insurer level data
    read: object                   # value text -> (score 0..1, plain reading) or None
    weight: float = 1.0


def _shown(m: float) -> str:
    return f"{round(m * 30)} days" if m < 2 and abs(m * 30 - round(m * 30)) < 0.01 else f"{m:g} months"


def _wait_reader(scale_months: float, what: str, first: bool = False):
    """first: the initial waiting period is the first duration stated ("30 days ... not
    applicable if ..."); for the others the longest one counts."""
    def read(text):
        d = durations_months(text)
        if not d:
            return None
        m = d[0] if first else max(d)
        note = " (age dependent, longer value used)" if re.search(r"\b(below|above)\s+\d+\s*years", text, re.I) else ""
        return max(0.0, 1 - m / scale_months), f"{what} {_shown(m)}{note}"
    return read


CRITERIA = {
    "ped_waiting": Criterion("ped_waiting", "Pre-existing disease waiting", "ped_waiting", _wait_reader(48, "PED wait")),
    "specific_waiting": Criterion("specific_waiting", "Specific disease waiting", "specific_disease_waiting", _wait_reader(48, "longest specific disease wait")),
    "initial_waiting": Criterion("initial_waiting", "Initial waiting", "initial_waiting", _wait_reader(2, "initial wait", first=True)),
    "claims": Criterion("claims", "Claims paid against premium (IRDAI ICR)", None, None),
    "room_rent": Criterion("room_rent", "Room rent limit", "room_rent", room_rent_score),
    "copay": Criterion("copay", "Co-payment", "copay", copay_score),
    "maternity": Criterion("maternity", "Maternity cover", "maternity", maternity_score),
    "bonus": Criterion("bonus", "No claim bonus", "no_claim_bonus", bonus_score),
}

# What the agent said -> criteria and weights. Checked in order; Hindi and Hinglish included.
PREF_WORDS = [
    (r"pre.?existing|\bped\b|pehle se|पहले से|purani bimari", {"ped_waiting": 3}),
    (r"diabet|sugar|madhumeh|मधुमेह|डायबिटीज|hypertension|blood pressure|\bbp\b", {"ped_waiting": 3, "specific_waiting": 2}),
    (r"waiting|wait|waive|प्रतीक्षा|वेटिंग|intezaar|इंतज़ार", {"ped_waiting": 3, "specific_waiting": 2, "initial_waiting": 1}),
    (r"claim.{0,20}(ratio|record|settle|paid|pay)|settlement|क्लेम|दावा|claim\s+ratio", {"claims": 3}),
    (r"room|kamra|कमरा", {"room_rent": 2}),
    (r"co.?pay|copayment|सह.?भुगतान", {"copay": 2}),
    (r"maternity|pregnan|delivery|prasav|प्रसव|मातृत्व", {"maternity": 3}),
    (r"bonus|\bncb\b|no.?claim", {"bonus": 1}),
]
NEGATED = r"(not (really )?(concerned|worried|bothered) (about|with)|doesn'?t matter|does not matter|do(es)?n'?t (really )?care|(do|does|did) not (really )?care|not important|no issue with|koi baat nahi|chinta nahi|फर्क नहीं)"
PREMIUM_RE = re.compile(r"premium|price|cost|cheap|sasta|sasti|budget|प्रीमियम|कीमत", re.I)
MUST_MATERNITY = re.compile(r"(must|need|needs|chahiye|zaroori|ज़रूरी|जरूरी|with|wali|vali).{0,25}(maternity|pregnan|delivery)|(maternity|delivery|pregnan)\w*.{0,15}(chahiye|zaroori|must|required|ज़रूरी|जरूरी)", re.I)
BALANCED = {"ped_waiting": 2, "specific_waiting": 1, "initial_waiting": 0.5, "claims": 2, "room_rent": 1.5,
            "copay": 1.5, "bonus": 0.5}


# A negation ("premium does not matter") only reaches the words of its own clause, never the
# next sentence or the other half of "X and Y".
CLAUSE_SPLIT = re.compile(r"[.,;:?!।]|\b(?:and|but|aur|lekin|par|however)\b", re.I)


def clauses(t: str) -> list[str]:
    return [c for c in CLAUSE_SPLIT.split(t) if c and c.strip()]


def preferences(text: str) -> dict:
    """{"weights": {criterion: weight}, "premium": None | "ignored" | "asked", "must": [criteria], "balanced": bool}"""
    t = text.lower()
    weights: dict[str, float] = {}
    premium = None
    for part in clauses(t):
        negated = bool(re.search(NEGATED, part))
        for rx, w in PREF_WORDS:
            if re.search(rx, part) and not negated:
                for k, v in w.items():
                    weights[k] = max(weights.get(k, 0), v)
        if PREMIUM_RE.search(part):
            premium = "ignored" if negated else premium or "asked"
    must = ["maternity"] if MUST_MATERNITY.search(t) else []
    balanced = not weights
    if balanced:
        weights = dict(BALANCED)
    return {"weights": weights, "premium": premium, "must": must, "balanced": balanced}


# ------------------------------------------------------------------ candidates

@lru_cache(maxsize=1)
def insurer_data() -> dict:
    return json.load(open(INSURERS_FILE, encoding="utf-8"))


def claims_reading(insurer: str) -> tuple[float, str, dict] | None:
    d = insurer_data()["insurers"].get(insurer)
    if not d or not d.get("icr_health"):
        return None
    year = max(d["icr_health"])
    icr = d["icr_health"][year]
    src = insurer_data()["sources"][d["source"]]
    # More of the premium returned as claims is better for customers, up to 100%. Above 100%
    # the insurer paid out more than it earned, which is not rewarded further and is flagged.
    score = max(0.0, min(icr, 100) - 60) / 40
    reading = f"ICR {icr:g}% in {year}" + (" (above 100%: paid more in claims than it earned in premium)" if icr > 100 else "")
    return score, reading, {"source": src["title"], "printed_page": src["printed_page"], "year": year, "icr": icr}


def candidates(facts=None) -> list[dict]:
    """One candidate per policy plan. Rows for a plan override the policy's ALL rows."""
    out = []
    man = manifest()
    for f in facts if facts is not None else load_facts():
        r = man.get(f["policy_id"], {})
        prod = (r.get("product") or "").lower()
        # never shortlist a product that is no longer sold, or a top-up that needs a base policy
        if facts is None and ((r.get("status") or "active") == "withdrawn" or "top-up" in prod):
            continue
        plans = sorted({r["plan"] for r in f["rows"] if r["plan"] != "ALL"}) or ["ALL"]
        for plan in plans:
            rows = {}
            for r in f["rows"]:
                if r["plan"] in ("ALL", plan) and (r["attribute"] not in rows or r["plan"] == plan):
                    rows[r["attribute"]] = r
            out.append({"policy_id": f["policy_id"], "insurer": f["insurer"], "product": f["product"],
                        "plan": plan, "rows": rows})
    return out


def score_candidate(c: dict, weights: dict, offsets: dict) -> dict:
    total = got = 0.0
    parts, missing = [], []
    for key, w in weights.items():
        crit = CRITERIA[key]
        total += w
        if crit.attribute is None:
            r = claims_reading(c["insurer"])
            if r is None:
                missing.append(crit.label + ": no IRDAI figure on file")
                parts.append({"criterion": key, "label": crit.label, "score": 0.0, "reading": "no figure on file",
                              "weight": w, "value": None, "missing": True})
                continue
            s, reading, src = r
            got += w * s
            parts.append({"criterion": key, "label": crit.label, "score": round(s, 3), "reading": reading, "weight": w,
                          "value": reading, "source": src["source"], "printed_page": src["printed_page"]})
            continue
        row = c["rows"].get(crit.attribute)
        # only a stated row with a checked quote can score; an unclear draft is a gap, not a value
        res = crit.read(row["value"]) if row and row["status"] == "stated" and row["evidence"] else None
        if res is None:
            why = ("not in the fact table yet" if not row else "not stated in the document"
                   if row["status"] == "not_stated" else "unclear in the fact table" if row["status"] == "unclear"
                   or not row["evidence"] else "could not read a figure from: " + row["value"][:60])
            missing.append(f"{crit.label}: {why}")
            parts.append({"criterion": key, "label": crit.label, "score": 0.0, "reading": why, "weight": w,
                          "value": row["value"] if row else None, "missing": True})
            continue
        s, reading = res
        got += w * s
        ev = row["evidence"][0] if row["evidence"] else {}
        page = ev.get("page")
        off = offsets.get(c["policy_id"], 0)
        parts.append({"criterion": key, "label": crit.label, "score": round(s, 3), "reading": reading, "weight": w,
                      "value": row["value"], "page": page, "printed_page": page - off if page else None,
                      "quote": ev.get("quote"), "verified": row["verified"]})
    return {**{k: c[k] for k in ("policy_id", "insurer", "product", "plan")},
            "score": round(100 * got / total, 1) if total else 0.0, "parts": parts, "missing": missing,
            "verified": all(p.get("verified", True) for p in parts if "verified" in p)}


def merge_same(rows: list[dict]) -> list[dict]:
    """Plans of one policy that score the same on every criterion asked about are one line
    ("Gold, Platinum, Senior plans"), so the shortlist is not filled with copies."""
    out: dict[tuple, dict] = {}
    for r in rows:
        key = (r["policy_id"], r["product"], r["score"], tuple((p["criterion"], p["reading"]) for p in r["parts"]))
        if key in out:
            prev = out[key]
            prev["plans"].append(r["plan"])
        else:
            out[key] = {**r, "plans": [r["plan"]]}
    for r in out.values():
        r["plan"] = "ALL" if r["plans"] == ["ALL"] else ", ".join(r["plans"])
    return list(out.values())


def rank(text: str, facts=None, top: int | None = None) -> dict:
    prefs = preferences(text)
    man = manifest()
    offsets = {pid: int(r.get("page_offset") or 0) for pid, r in man.items()}
    ranked, dropped = [], []
    for c in candidates(facts):
        res = score_candidate(c, prefs["weights"], offsets)
        failed = [m for m in prefs["must"] if not any(p["criterion"] == m and p["score"] >= 1 for p in res["parts"])]
        if failed:
            dropped.append({**res, "reason": "does not cover " + ", ".join(CRITERIA[m].label.lower() for m in failed)})
        else:
            ranked.append(res)
    ranked = merge_same(ranked)
    dropped = merge_same(dropped)
    # ties: fewer missing facts first, then name, so the order is stable
    ranked.sort(key=lambda r: (-r["score"], len(r["missing"]), r["insurer"], r["plan"]))
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return {"preferences": prefs, "ranked": ranked[:top] if top else ranked, "dropped": dropped,
            "total": len(ranked) + len(dropped)}


# ------------------------------------------------------------------ the chat answer

TEXT = {
    "en": {
        "head": "Ranked from the policy fact table{what}.",
        "balanced": " on a balanced mix of waiting periods, claims record, room rent and co-pay",
        "on": " on: {crits}",
        "premium_ignored": "Premium is left out, as you asked.",
        "premium_asked": "Premium is not in the policy documents, so this ranking cannot use it. Check the insurer's premium chart.",
        "dropped": "Left out because they lack {what}: {names}.",
        "missing": "{name}: scored 0 where the fact is missing ({what}).",
        "claims_note": "The claims figure is IRDAI's incurred claims ratio (claims as a share of premium), not a claim settlement ratio, which IRDAI no longer publishes per insurer.",
        "unverified": "The fact values are not yet verified by a person against the PDFs. Confirm before advising a customer.",
        "advice": "This is a shortlist for the agent, not advice to the customer. Eligibility, premium and the full wording still need checking.",
        "plan": " ({plan} plan)",
        "plans": " ({plan} plans)",
    },
    "hinglish": {
        "head": "Policy fact table se ranking{what}.",
        "balanced": ", waiting period, claims record, room rent aur co-pay ko barabar dekh kar",
        "on": ", in baaton par: {crits}",
        "premium_ignored": "Aapke kehne par premium ko ranking mein nahi liya gaya.",
        "premium_asked": "Premium policy document mein nahi hota, isliye ranking mein nahi liya ja sakta. Insurer ka premium chart dekhein.",
        "dropped": "Hataye gaye kyunki inmein {what} nahi hai: {names}.",
        "missing": "{name}: jo fact nahi mila uske liye 0 diya gaya ({what}).",
        "claims_note": "Claims figure IRDAI ka incurred claims ratio hai (premium ke mukable claims), claim settlement ratio nahi. IRDAI ab har insurer ka settlement ratio publish nahi karta.",
        "unverified": "Fact values abhi kisi ne PDF se verify nahi kiye hain. Customer ko batane se pehle check karein.",
        "advice": "Yeh agent ke liye shortlist hai, customer ke liye salah nahi. Eligibility, premium aur poori wording abhi check karni hai.",
        "plan": " ({plan} plan)",
        "plans": " ({plan} plans)",
    },
    "hi": {
        "head": "पॉलिसी फैक्ट टेबल से रैंकिंग{what}।",
        "balanced": ", वेटिंग पीरियड, क्लेम रिकॉर्ड, रूम रेंट और को-पे को बराबर देखकर",
        "on": ", इन बातों पर: {crits}",
        "premium_ignored": "आपके कहने पर प्रीमियम को रैंकिंग में नहीं लिया गया।",
        "premium_asked": "प्रीमियम पॉलिसी दस्तावेज़ में नहीं होता, इसलिए रैंकिंग में नहीं लिया जा सकता। बीमा कंपनी का प्रीमियम चार्ट देखें।",
        "dropped": "हटाए गए क्योंकि इनमें {what} नहीं है: {names}।",
        "missing": "{name}: जो तथ्य नहीं मिला उसके लिए 0 दिया गया ({what})।",
        "claims_note": "क्लेम का आंकड़ा IRDAI का इनकर्ड क्लेम्स रेशियो है (प्रीमियम के मुकाबले क्लेम), क्लेम सेटलमेंट रेशियो नहीं। IRDAI अब हर कंपनी का सेटलमेंट रेशियो प्रकाशित नहीं करता।",
        "unverified": "फैक्ट टेबल के मान अभी किसी व्यक्ति ने PDF से जाँचे नहीं हैं। ग्राहक को बताने से पहले जाँच लें।",
        "advice": "यह एजेंट के लिए शॉर्टलिस्ट है, ग्राहक के लिए सलाह नहीं। पात्रता, प्रीमियम और पूरी शर्तें अभी जाँचनी हैं।",
        "plan": " ({plan} प्लान)",
        "plans": " ({plan} प्लान)",
    },
}


def display(r: dict, lang: str) -> str:
    plan = "" if r["plan"] == "ALL" else TEXT[lang]["plan" if "," not in r["plan"] else "plans"].format(plan=r["plan"].title())
    return f"{r['insurer']}: {r['product'].split(' (')[0]}{plan}"


def rank_answer(question: str, lang: str = "en", top: int = 3) -> dict:
    res = rank(question)
    w = TEXT[lang]
    prefs = res["preferences"]
    crits = ", ".join(CRITERIA[k].label.lower() for k, _ in sorted(prefs["weights"].items(), key=lambda kv: -kv[1]))
    lines = [w["head"].format(what=w["balanced"] if prefs["balanced"] else w["on"].format(crits=crits))]
    cites = []
    for r in res["ranked"][:top]:
        reasons = "; ".join(p["reading"] for p in r["parts"] if p["score"] > 0)
        lines.append(f"{r['rank']}. {display(r, lang)}: {r['score']:g}/100. {reasons}.")
        for p in r["parts"]:
            if p.get("page") and p.get("quote"):
                cites.append({"n": len(cites) + 1, "policy_id": r["policy_id"], "product": display(r, lang),
                              "section": f"{display(r, lang)}: {p['label']}", "page": p["page"],
                              "printed_page": p["printed_page"], "quote": p["quote"], "text": p["value"]})
    for r in res["ranked"][:top]:
        if r["missing"]:
            lines.append(w["missing"].format(name=display(r, lang), what="; ".join(r["missing"])))
    if res["dropped"]:
        names = ", ".join(display(d, lang) for d in res["dropped"])
        lines.append(w["dropped"].format(names=names, what=CRITERIA[prefs["must"][0]].label.lower()))
    if prefs["premium"]:
        lines.append(w["premium_" + prefs["premium"]])
    if "claims" in prefs["weights"]:
        lines.append(w["claims_note"])
    if any(not r["verified"] for r in res["ranked"][:top]):
        lines.append(w["unverified"])
    from fact_table import coverage_note
    note = coverage_note(lang, {f["policy_id"] for f in load_facts()})
    if note:
        lines.append(note)
    lines.append(w["advice"])
    return {"status": "ranked", "answer": "\n".join(lines), "citations": cites, "table": None,
            "ranking": {"criteria": [{"key": k, "label": CRITERIA[k].label, "weight": v}
                                     for k, v in sorted(prefs["weights"].items(), key=lambda kv: -kv[1])],
                        "rows": [{**r, "name": display(r, lang)} for r in res["ranked"]],
                        "dropped": [{"name": display(d, lang), "reason": d["reason"]} for d in res["dropped"]],
                        "premium": prefs["premium"], "total": res["total"]}}


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "no waiting periods, best claim ratio, premium does not matter"
    out = rank_answer(q)
    print(out["answer"])
    print()
    for r in out["ranking"]["rows"]:
        print(f"{r['rank']:2}. {r['score']:5.1f}  {r['name']}")
        for p in r["parts"]:
            print(f"      {p['label']:42} {p['score']:.2f}  {p['reading']}")
