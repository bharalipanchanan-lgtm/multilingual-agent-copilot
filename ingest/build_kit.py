#!/usr/bin/env python3
"""Per-product close kit: sale papers and claim papers, each from that wording.

    python3 ingest/build_kit.py [--write]

Scans data/pages for documents the wording names. Papers are split into:
  buy_papers  — needed at proposal / sale (pre-policy check, past medical
                records, previous policy / portability, KYC or bank only when
                the hit sits in a proposal / underwriting context)
  claim_papers — needed at claim time (claim form, discharge, bills, …)

Never invents a paper that the wording does not name. Also records the
30-day initial waiting clause when present.

Writes products[].close_kit =
  {buy_papers, claim_papers, papers (= buy+claim for quote tests), initial_wait}.
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAT = ROOT / "web" / "data" / "catalogue.json"
PAGES = ROOT / "data" / "pages"

# key, regex, default phase ("buy" | "claim")
PAPERS = [
    ("claim_form", r"claim form", "claim"),
    ("discharge", r"discharge summary|discharge certificate|discharge card", "claim"),
    ("bills", r"original (?:hospital |final |main )?bills?|hospital main bill|bills? and (?:payment )?receipts|payment receipts?", "claim"),
    ("reports", r"investigation(?:/diagnostic)? reports?|diagnostic (?:test )?reports?|laborator(?:y|ies) reports?|lab reports?", "claim"),
    ("prescription", r"prescriptions? (?:of|from|by) the (?:treating |attending )?(?:medical practitioner|doctor)|doctor'?s prescription|medical practitioner'?s prescription", "claim"),
    ("pharmacy", r"pharmacy bills?|chemist bills?", "claim"),
    ("fir_mlc", r"\bFIR\b|first information report|medico[- ]legal", "claim"),
    ("pre_policy_check", r"pre[- ]?policy (?:medical )?(?:check[- ]?up|tests?|screening|examination)|pre[- ]acceptance medical|pre[- ]insurance medical|prePolicy medical", "buy"),
    ("medical_records", r"(?:previous|past|earlier|prior) (?:medical|treatment|consultation|hospitali[sz]ation) (?:records?|papers|documents|history)|past medical records", "buy"),
    ("prev_policy", r"previous policy (?:copy|documents?|details)|portability form", "buy"),
    # KYC / bank / age proof appear in both claim lists and proposal text — phase from context
    ("kyc", r"\bKYC\b|photo identity|photo id\b|identity proof|id proof|age proof", "either"),
    ("bank", r"cancell?ed cheque|\bNEFT\b|bank account details", "either"),
]
INITIAL = re.compile(
    r"(?:within|during) (?:the )?(?:first )?30 days (?:from|of) (?:the )?(?:first )?(?:policy )?(?:commencement|inception|start)[^.]{0,160}",
    re.I,
)
BUY_CTX = re.compile(r"proposal|underwrit|pre[- ]?policy|prePolicy|portabilit|declar(?:ation|ed) in the proposal", re.I)
CLAIM_CTX = re.compile(r"\bclaim\b|reimburs|cashless|hospitali[sz]ation documents|documentation will include", re.I)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def snippet(flat: str, m: re.Match) -> str:
    """The line around a match, verbatim, cut at sentence / list boundaries."""
    a = max(0, m.start() - 90)
    b = min(len(flat), m.end() + 90)
    left = flat[a : m.start()]
    cut = max(left.rfind(". "), left.rfind("• "), left.rfind("; "), left.rfind(": "), left.rfind("\n"))
    a = a + cut + 2 if cut >= 0 else a + (left.find(" ") + 1 if " " in left else 0)
    # do not start mid-word, and skip a lone OCR letter before the match ("r claim form")
    while a > 0 and a < m.start() and flat[a - 1].isalnum():
        a -= 1
    head = flat[a : m.start()].strip()
    if re.fullmatch(r"[A-Za-z]", head) or re.fullmatch(r".*[:•]\s*[A-Za-z]", head):
        # prefer the sentence start further left when the immediate head is junk
        left2 = flat[max(0, m.start() - 160) : m.start()]
        cut2 = max(left2.rfind(". "), left2.rfind(": "))
        if cut2 >= 0:
            a = max(0, m.start() - 160) + cut2 + 2
    right = flat[m.end() : b]
    stop = min([i for i in (right.find(". "), right.find("; "), right.find(" •")) if i >= 0] or [len(right)])
    b = m.end() + stop + (1 if stop < len(right) and right[stop] == "." else 0)
    if b == m.end() + len(right) and " " in right:
        b = m.end() + right.rfind(" ")
    return flat[a:b].strip(" ,;•")


def phase_for(key_phase: str, flat: str, m: re.Match) -> str | None:
    """Buy vs claim. Drop an 'either' hit that has no clear context."""
    window = flat[max(0, m.start() - 400) : m.end() + 200]
    buy = bool(BUY_CTX.search(window))
    claim = bool(CLAIM_CTX.search(window))
    if key_phase == "buy":
        return "buy"
    if key_phase == "claim":
        return "claim"
    if buy and not claim:
        return "buy"
    if claim and not buy:
        return "claim"
    if buy and claim:
        # claim documentation lists usually win when both words appear
        return "claim"
    return None


def kit_for(doc_pages, offset):
    pages = [(p["page"], re.sub(r"\s+", " ", p["text"])) for p in doc_pages]
    buy, claim = [], []
    seen = set()
    for key, pat, key_phase in PAPERS:
        rx = re.compile(pat, re.I)
        # prefer buy-context pages for buy keys, claim-context for claim keys
        def rank(item):
            n, flat = item
            has_buy, has_claim = bool(BUY_CTX.search(flat)), bool(CLAIM_CTX.search(flat))
            if key_phase == "buy":
                return (not has_buy, n)
            if key_phase == "claim":
                return (not has_claim, n)
            return (not (has_buy or has_claim), n)

        for n, flat in sorted(pages, key=rank):
            m = rx.search(flat)
            if not m:
                continue
            phase = phase_for(key_phase, flat, m)
            if not phase or key in seen:
                continue
            q = snippet(flat, m)
            if len(norm(q)) < 12:
                continue
            item = {
                "key": key,
                "phase": phase,
                "pdf_page": n,
                "printed_page": n + offset if offset is not None else None,
                "quote": q,
            }
            (buy if phase == "buy" else claim).append(item)
            seen.add(key)
            break

    initial = None
    for n, flat in pages:
        m = INITIAL.search(flat)
        if m:
            q = m.group(0).strip()
            q = q[: q.rfind(" ")] if len(m.group(0)) >= 200 and " " in q else q
            initial = {
                "pdf_page": n,
                "printed_page": n + offset if offset is not None else None,
                "quote": q,
            }
            break
    papers = buy + claim  # flat list for the catalogue quote test
    return {"buy_papers": buy, "claim_papers": claim, "papers": papers, "initial_wait": initial}


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
            assert norm(item["quote"]) in norm(page), (p["id"], item.get("key"), item["quote"][:80])
        p["close_kit"] = kit
        print(
            f"{p['id']:<70} buy={len(kit['buy_papers']):>2} claim={len(kit['claim_papers']):>2} "
            f"[{','.join(x['key'] for x in kit['buy_papers'])}] / "
            f"[{','.join(x['key'] for x in kit['claim_papers'])}]"
            f"{'  +30d' if kit['initial_wait'] else ''}"
        )
    if write:
        CAT.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
