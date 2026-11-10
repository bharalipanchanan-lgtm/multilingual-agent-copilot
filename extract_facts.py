"""Draft fact table rows from the policy text, for a person to verify.

  python extract_facts.py care_care                 one policy, attributes it does not have yet
  python extract_facts.py --all                     every loaded policy
  python extract_facts.py care_care --redo room_rent

For each attribute: retrieve the clauses that answer it (retrieve.py), ask the hosted model
(generate.APIGenerator, COPILOT_LLM, Sarvam by default) for the value, one verbatim quote, the page and
the clause number, plus a few plain numbers the ranking reads ("numbers"). Then the quote is
checked mechanically against the PDF page (fact_table.quote_results):

  quote found on its page         row is "stated", with that evidence
  quote found on another page     the page is corrected to where it is
  quote not found anywhere        row is "unclear", evidence dropped, note says so

Rows are always written verified: false. A draft is a starting point for the reviewer, never
a fact on its own: the ranking and the quick answers label every value as unverified.
Existing rows are kept; only missing attributes are added (or those named in --redo).
"""
import argparse
import json
import re
import sys
import time

from config import FACTS_DIR
from fact_table import ATTRIBUTES, manifest, norm, page_texts

# attribute -> (retrieval queries, what to extract, the "numbers" object to fill)
SPEC = {
    "ped_waiting": (["pre-existing disease waiting period months continuous coverage",
                     "pre-existing diseases excluded until expiry of months"],
                    "the waiting period for pre-existing diseases",
                    '{"months": int or null}'),
    "specific_disease_waiting": (["specified disease procedure waiting period 24 months list cataract hernia",
                                  "specific waiting period diabetes hypertension"],
                                 "the specific disease or procedure waiting periods (longest one, and the ones for cataract and diabetes if listed)",
                                 '{"months_max": int or null, "cataract_months": int or null, "diabetes_months": int or null}'),
    "initial_waiting": (["first 30 days waiting period from policy commencement except accident"],
                        "the initial waiting period from the first policy start",
                        '{"days": int or null}'),
    "room_rent": (["room rent limit per day single private room", "room category accommodation charges sum insured per day"],
                  "the room rent limit or room category covered (for the base plan; say if it changes by sum insured or plan)",
                  '{"kind": "no_limit" | "category" | "percent_si" | "rupees" | "other", "percent_of_si": number or null, '
                  '"rupees_per_day": number or null, "category": string or null}'),
    "icu_limit": (["ICU intensive care unit charges limit"], "the ICU charges limit", '{"kind": "no_limit" | "percent_si" | "rupees" | "other"}'),
    "copay": (["co-payment percentage of admissible claim", "co-pay age zone"],
              "the co-payment that applies (and when: age, zone, non-network, voluntary)",
              '{"percent": number or null, "mandatory": true | false | null, "condition": string or null}'),
    "maternity": (["maternity expenses delivery waiting period newborn", "maternity exclusion pregnancy childbirth"],
                  "whether maternity (childbirth) is covered, and its waiting period",
                  '{"covered": true | false | null, "waiting_months": int or null}'),
    "ayush": (["AYUSH treatment ayurveda unani siddha homeopathy inpatient"],
              "whether AYUSH inpatient treatment is covered and up to what limit",
              '{"covered": true | false | null, "limit": string or null}'),
    "daycare": (["day care treatment procedures covered less than 24 hours"], "whether day care treatments are covered",
                '{"covered": true | false | null}'),
    "no_claim_bonus": (["cumulative bonus no claim bonus increase sum insured per claim free year maximum"],
                       "the no claim / cumulative bonus: how much per claim-free year and the maximum",
                       '{"percent_per_year": number or null, "max_percent": number or null}'),
    "entry_age": (["entry age minimum maximum adult years eligibility", "age at entry dependent children 91 days"],
                  "the minimum and maximum entry age for an adult (and children if stated)",
                  '{"adult_min_years": int or null, "adult_max_years": int or null (null when the document says there is no upper limit or does not state one)}'),
    "sum_insured_options": (["sum insured options available lakh", "sum insured from to rupees"],
                            "the sum insured options (lowest and highest)",
                            '{"min_rupees": int or null, "max_rupees": int or null}'),
    "restoration_reload": (["restore reinstatement of sum insured after claim exhausted", "recharge reload sum insured"],
                           "whether the sum insured is restored or reloaded after it is used up, and how",
                           '{"available": true | false | null}'),
    "sublimits": (["sub-limit cataract per eye limit", "modern treatment robotic surgery limit sum insured"],
                  "the sub-limits on specific treatments, especially cataract and modern treatments such as robotic surgery",
                  '{"cataract": string or null, "modern_treatment": string or null}'),
    "moratorium": (["moratorium period sixty months continuous coverage no claim contestable"],
                   "the moratorium period", '{"months": int or null}'),
    "mental_illness": (["mental illness treatment inpatient covered"], "whether inpatient mental illness treatment is covered",
                       '{"covered": true | false | null}'),
    "cashless": (["cashless facility network hospital pre-authorisation"], "whether cashless treatment is available and where",
                 '{"available": true | false | null}'),
    "pre_post_hospitalisation": (["pre-hospitalisation post-hospitalisation medical expenses days"],
                                 "the pre and post hospitalisation days covered", '{"pre_days": int or null, "post_days": int or null}'),
}
# Attributes a policy must have for the ranking, quick answers and sales help
CORE = ["ped_waiting", "specific_disease_waiting", "initial_waiting", "room_rent", "copay", "maternity", "ayush",
        "no_claim_bonus", "entry_age", "sum_insured_options", "restoration_reload", "sublimits", "daycare",
        "pre_post_hospitalisation", "icu_limit", "moratorium", "mental_illness", "cashless"]

SYSTEM = """You read Indian health insurance policy text and extract one fact for an insurance agent.
Use only the numbered extracts given. Never use outside knowledge or guess.
Answer with a single JSON object and nothing else:
{"status": "stated" | "not_stated" | "unclear",
 "value": "the fact in one or two plain English sentences, with the numbers as written",
 "quote": "one sentence or phrase copied character for character from ONE extract, 8 to 40 words, that states the fact",
 "extract": the extract number the quote is from,
 "clause": "the clause or section number the fact is under, as printed, or null",
 "numbers": NUMBERS}
Rules: "not_stated" when the extracts do not answer; then quote is null. "unclear" when they conflict.
Copy the quote exactly, including punctuation; do not join text from two places. Ages and amounts as numbers
(5 lakh = 500000, 1 crore = 10000000). If the value differs by plan or sum insured, say so in value and give the
base plan's numbers."""


def extracts(policy_id: str, attribute: str) -> list[dict]:
    from retrieve import expand_sections, search
    seen, hits = set(), []
    for q in SPEC[attribute][0]:
        for h in search(q, policy_id, 5):
            if h["id"] not in seen:
                seen.add(h["id"])
                hits.append(h)
    hits = expand_sections(hits, max_extra=2)[:9]
    if attribute in SCAN:  # a rule in a table or schedule often ranks low: scan every chunk for its words
        for h in scan(policy_id, attribute):
            if h["id"] not in seen:
                seen.add(h["id"])
                hits.append(h)
    return hits[:16]


# words that name the fact; every chunk of the document that has them is read, best first
SCAN = {
    "room_rent": r"room rent|room category|single private|private (?:a/?c )?room|accommodation|shared room|room type|single occupancy",
    "copay": r"co-?pay(?:ment)?",
    "entry_age": r"entry age|age at entry|minimum age|maximum age|age of entry|eligib\w+|years? (?:and|to) \d+ years|91 days",
}


def scan(policy_id: str, attribute: str, limit: int = 7) -> list[dict]:
    from retrieve import _load
    _, col = _load()
    res = col.get(where={"policy_id": policy_id}, include=["documents", "metadatas"])
    rx = re.compile(SCAN[attribute], re.I)
    scored = []
    for cid, doc, meta in zip(res["ids"], res["documents"], res["metadatas"]):
        n = len(rx.findall(doc))
        if n:
            figures = len(re.findall(r"\d+\s*(?:%|years?|lakh|lac|days|rs|inr|₹)", doc, re.I))
            scored.append((n * 2 + min(figures, 6), {"id": cid, "text": doc, "score": None, **meta}))
    scored.sort(key=lambda x: -x[0])
    return [h for _, h in scored[:limit]]


def ask(gen, policy: dict, attribute: str, hits: list[dict]) -> dict:
    what, numbers = SPEC[attribute][1], SPEC[attribute][2]
    body = "\n\n".join(f"[extract {i}, page {h['page']}, section {h.get('section') or '-'}]\n{h['text']}"
                       for i, h in enumerate(hits, 1))
    user = (f"Policy: {policy['insurer']}, {policy['product']}\nFact to extract: {what}.\n\n{body}\n\n"
            f"Return the JSON object. NUMBERS is {numbers}.")
    out = "".join(gen.stream(SYSTEM.replace("NUMBERS", numbers), user))
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        raise ValueError("no JSON in reply: " + out[:200])
    return json.loads(m.group(0))


def check_quote(policy_id: str, quote: str | None, page: int | None) -> tuple[int | None, str | None]:
    """(page, the verbatim quote) or (page, None). The quote must appear verbatim (after
    fact_table.norm). When the model joined or retyped a few words, the longest run of at least six
    consecutive words of its quote that does appear on a page is used instead: still the policy's
    own words, never the model's."""
    if not quote:
        return page, None
    texts = page_texts(policy_id)
    order = ([page - 1] if page and 1 <= page <= len(texts) else []) + [i for i in range(len(texts)) if i != (page or 0) - 1]
    nq = norm(quote)
    for i in order:
        if nq in texts[i]:
            return i + 1, quote
    words = quote.split()
    for n in range(len(words) - 1, 5, -1):
        for j in range(len(words) - n + 1):
            frag = " ".join(words[j:j + n]).strip(" ,;:")
            nf = norm(frag)
            for i in order:
                if nf in texts[i]:
                    return i + 1, frag
    return page, None


def row_for(policy_id: str, attribute: str, d: dict, hits: list[dict], model: str) -> dict:
    status = d.get("status") if d.get("status") in ("stated", "not_stated", "unclear") else "unclear"
    note = f"Drafted by extract_facts.py ({model}) on {time.strftime('%Y-%m-%d')}; not verified by a person."
    evidence = []
    if status == "stated":
        i = d.get("extract")
        page = hits[i - 1]["page"] if isinstance(i, int) and 1 <= i <= len(hits) else None
        page, quote = check_quote(policy_id, d.get("quote"), page)
        if quote:
            evidence = [{"page": page, "quote": quote, "clause": d.get("clause")}]
            if quote != d["quote"]:
                note += " Quote shortened to the words found verbatim in the PDF."
        else:
            status = "unclear"
            note += " The model's quote was not found verbatim in the PDF, so the value needs reading by hand."
    value = d.get("value") or ("Not stated in the document" if status == "not_stated" else "")
    return {"plan": "ALL", "attribute": attribute, "value": value, "status": status,
            "needs_extra_care": status != "stated", "evidence": evidence, "note": note,
            "numbers": d.get("numbers") or {}, "verified": False, "verified_by": None, "verified_on": None}


def run(policy_id: str, gen, redo: set[str], only: list[str] | None = None) -> None:
    man = manifest()[policy_id]
    path = FACTS_DIR / f"{policy_id}.json"
    f = json.load(open(path, encoding="utf-8")) if path.exists() else None
    if f is None or f.get("format") != 2:
        legacy = f
        f = {"format": 2, "policy_id": policy_id, "insurer": man["insurer"], "product": man["product"],
             "source": f"{man['file']}, UIN {man.get('uin') or 'not printed'}", "rows": []}
        if legacy:
            f["source"] += "; replaces the legacy (format 1) rows, which had no quotes"
    have = {(r["plan"], r["attribute"]) for r in f["rows"]}
    todo = [a for a in (only or CORE) if a in redo or ("ALL", a) not in have and not any(r["attribute"] == a for r in f["rows"])]
    for a in todo:
        hits = extracts(policy_id, a)
        try:
            d = ask(gen, man, a, hits)
        except Exception as e:  # one bad reply should not stop the run; the row says why
            d = {"status": "unclear", "value": f"Extraction failed: {e}"[:200]}
        row = row_for(policy_id, a, d, hits, gen.name)
        f["rows"] = [r for r in f["rows"] if not (r["plan"] == "ALL" and r["attribute"] == a)] + [row]
        ev = row["evidence"][0] if row["evidence"] else {}
        print(f"  {policy_id:34} {a:26} {row['status']:10} p{ev.get('page', '-')}  {row['value'][:90]}", flush=True)
        json.dump(f, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("policy", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--redo", default="", help="comma separated attributes to extract again")
    ap.add_argument("--only", default="", help="comma separated attributes to consider")
    a = ap.parse_args()
    from generate import APIGenerator
    gen = APIGenerator()
    gen.max_tokens = 900
    ok, why = gen.available()
    if not ok:
        sys.exit(why)
    from policy_select import policies
    ids = [p["policy_id"] for p in policies()] if a.all else a.policy
    redo = {x for x in a.redo.split(",") if x}
    only = [x for x in a.only.split(",") if x] or None
    for pid in ids:
        run(pid, gen, redo, only)


if __name__ == "__main__":
    for k in SPEC:
        assert k in ATTRIBUTES, k
    main()
