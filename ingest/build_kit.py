#!/usr/bin/env python3
"""Per-product close kit: the papers each wording itself asks for.

    python3 ingest/build_kit.py [--write]

For every product in web/data/catalogue.json, scan its extracted pages
(data/pages) for the documents the wording names — claim form, discharge
summary, KYC, pre-policy check-up and so on. Each paper found is stored with
the verbatim line and its page, so the kit shows only papers that product's
wording asks for. Papers the wording does not name are left out, never filled
from a template. Also records the 30-day initial waiting clause when present.

Writes products[].close_kit = {papers: [...], initial_wait: {...} | null}.
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAT = ROOT / "web" / "data" / "catalogue.json"
PAGES = ROOT / "data" / "pages"

# key, regex that must occur in the wording
PAPERS = [
    ("claim_form", r"claim form"),
    ("kyc", r"\bKYC\b|photo identity|photo id\b|identity proof|id proof"),
    ("discharge", r"discharge summary|discharge certificate|discharge card"),
    ("bills", r"original (?:hospital |final |main )?bills?|hospital main bill|bills? and (?:payment )?receipts|payment receipts?"),
    ("reports", r"investigation(?:/diagnostic)? reports?|diagnostic (?:test )?reports?|laborator(?:y|ies) reports?|lab reports?"),
    ("prescription", r"prescriptions? (?:of|from|by) the (?:treating |attending )?(?:medical practitioner|doctor)|doctor'?s prescription|medical practitioner'?s prescription"),
    ("pharmacy", r"pharmacy bills?|chemist bills?"),
    ("bank", r"cancell?ed cheque|\bNEFT\b|bank account details"),
    ("fir_mlc", r"\bFIR\b|first information report|medico[- ]legal"),
    ("pre_policy_check", r"pre[- ]?policy (?:medical )?(?:check[- ]?up|tests?|screening|examination)|pre[- ]acceptance medical|pre[- ]insurance medical"),
    ("medical_records", r"(?:previous|past|earlier|prior) (?:medical|treatment|consultation|hospitali[sz]ation) (?:records?|papers|documents|history)"),
    ("prev_policy", r"previous policy (?:copy|documents?|details)|portability form"),
]
INITIAL = re.compile(r"(?:within|during) (?:the )?(?:first )?30 days (?:from|of) (?:the )?(?:first )?(?:policy )?(?:commencement|inception|start)[^.]{0,160}", re.I)
CLAIMISH = re.compile(r"claim", re.I)
DOCISH = re.compile(r"document", re.I)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def snippet(flat: str, m: re.Match) -> str:
    """The line around a match, verbatim, cut at sentence / list boundaries."""
    a = max(0, m.start() - 90)
    b = min(len(flat), m.end() + 90)
    left = flat[a:m.start()]
    cut = max(left.rfind(". "), left.rfind("• "), left.rfind("; "), left.rfind(": "))
    a = a + cut + 2 if cut >= 0 else a + (left.find(" ") + 1 if " " in left else 0)
    right = flat[m.end():b]
    stop = min([i for i in (right.find(". "), right.find("; "), right.find(" •")) if i >= 0] or [len(right)])
    b = m.end() + stop + (1 if stop < len(right) and right[stop] == "." else 0)
    if b == m.end() + len(right) and " " in right:
        b = m.end() + right.rfind(" ")
    return flat[a:b].strip(" ,;•")


def kit_for(doc_pages, offset):
    pages = [(p["page"], re.sub(r"\s+", " ", p["text"])) for p in doc_pages]
    # pages that talk about claim documents come first
    order = sorted(pages, key=lambda x: (not (CLAIMISH.search(x[1]) and DOCISH.search(x[1])), x[0]))
    papers = []
    for key, pat in PAPERS:
        rx = re.compile(pat, re.I)
        for n, flat in order:
            m = rx.search(flat)
            if m:
                q = snippet(flat, m)
                papers.append({"key": key, "pdf_page": n, "printed_page": n + offset if offset is not None else None, "quote": q})
                break
    initial = None
    for n, flat in pages:
        m = INITIAL.search(flat)
        if m:
            q = m.group(0).strip()
            q = q[: q.rfind(" ")] if len(m.group(0)) >= 200 and " " in q else q
            initial = {"pdf_page": n, "printed_page": n + offset if offset is not None else None, "quote": q}
            break
    return {"papers": papers, "initial_wait": initial}


def main() -> int:
    write = "--write" in sys.argv
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    for p in cat["products"]:
        d = cat["documents"].get(p["id"])
        if not d:
            continue
        f = PAGES / (d["source"][:-4] + ".json")
        doc = json.loads(f.read_text(encoding="utf-8"))
        kit = kit_for(doc["pages"], d.get("page_offset"))
        for item in kit["papers"] + ([kit["initial_wait"]] if kit["initial_wait"] else []):
            page = next(x["text"] for x in doc["pages"] if x["page"] == item["pdf_page"])
            assert norm(item["quote"]) in norm(page), (p["id"], item)
        p["close_kit"] = kit
        print(f"{p['id']:<70} papers={len(kit['papers']):>2} {','.join(x['key'] for x in kit['papers'])}"
              f"{'  +30d' if kit['initial_wait'] else ''}")
    if write:
        CAT.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
