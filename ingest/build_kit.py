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
# a paper counts only where the wording asks for it: a list of documents to submit / furnish / attach
REQ_CTX = re.compile(
    r"documents?\b[^.]{0,60}\b(?:required|needed|necessary|submit|furnish|support|list)|"
    r"(?:submit|furnish|produce|provide|send|attach|enclos)\w*\b|along with|accompanied by|"
    r"following documents|documentation|duly (?:filled|completed|signed)|original",
    re.I,
)
# a hit that names the paper only to rule it out or in passing ("not for medico-legal purposes",
# "store their lab reports" on an app portal)
NOT_REQ = re.compile(r"\bnot (?:for|be|required|necessary)\b[^.]{0,30}$|\bportal\b|\bapp\b|\bstore\b|\bupload\b|disclos|misrepresent|fraud", re.I)


# hand-checked quotes where the PDF's two columns interleave and no rule can find the clean end.
# each value must still be verbatim text from that page (checked by the assert in main)
QUOTE_FIX = {
    # p34: "a. Duly completed claim form, and surgeons, g. ..." — "and surgeons" is the next column
    ("star-family-health-optima", "claim_form"): "Duly completed claim form",
    # p21: the text layer spaces letters apart ("du ly completed and s igned fo r on beha lf");
    # same words, normal spacing (norm() ignores spaces, so the page check still applies)
    ("tata-aig-medicare-plus", "claim_form"): "Our claim form, duly completed and signed for on behalf of the Insured Person.",
}


# garbled-text check and the clean re-read live with extraction, so data/pages already holds clean text
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from extract import garbled, repair_page  # noqa: E402


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
    cut_short = b == m.end() + len(right) and " " in right and b < len(flat)
    if cut_short:
        b = m.end() + right.rfind(" ")
    q = clean_end(flat[a:b])
    # the sentence goes on past the window: say so rather than present a fragment as the whole line
    return q + " …" if cut_short and not q.endswith((".", ")")) else q


# the next list item's marker leaks onto the end of a quote: "claim form, and b." / "original d."
TAIL_MARKER = re.compile(r"(?:[\s,;]+(?:and|or))?[\s,;]+(?:[a-z]|[ivx]{1,4})\.?$", re.I)
# a word cut by the window edge, or a dangling joiner
TAIL_JOINER = re.compile(r"[\s,;]+(?:and|or|the|of|to|in|for|with|by|from|as|at|a|an)$", re.I)


def clean_end(q: str) -> str:
    """Trim to a clean end. Only removes text (and table tick marks), so the quote stays verbatim."""
    q = re.sub(r"\s*[√×✓✗]\s*", " ", q)  # tick / cross cells and Symbol-font bullets from tables
    q = re.sub(r"\s{2,}", " ", q)
    q = q.strip(" ,;•\u0007\t")
    for _ in range(3):
        before = q
        q = TAIL_MARKER.sub("", q)
        q = TAIL_JOINER.sub("", q)
        q = q.rstrip(" ,;:•(-")
        if q == before:
            break
    return q


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
            if key in seen:
                break
            for m in rx.finditer(flat):
                phase = phase_for(key_phase, flat, m)
                if not phase:
                    continue
                # buy papers are named in underwriting text ("results of the pre-policy medical
                # examination"), not in a submit list, so only claim papers need the request context
                if phase == "claim" and not REQ_CTX.search(flat[max(0, m.start() - 250) : m.end() + 80]):
                    continue
                if NOT_REQ.search(flat[max(0, m.start() - 60) : m.start()]):
                    continue
                q = snippet(flat, m)
                # a quote may keep a letter-spaced word ("du ly completed"), never OCR noise ("duIly ... Ou11")
                if len(norm(q)) < 12 or NOT_REQ.search(q) or garbled(q, 0.2):
                    continue
                break
            else:
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
        # pages whose text layer is broken by a hidden OCR overlay: re-read them without it
        pdf = ROOT / "data" / "policies" / d["source"]
        # (normally done by `extract.py --repair`; repeated here so a stale data/pages cannot leak noise)
        for pg in doc["pages"]:
            if pdf.exists() and repair_page(pdf, pg):
                print(f"  {p['id']}: page {pg['page']} re-read without the OCR layer — run extract.py --repair")
        kit = kit_for(doc["pages"], d.get("page_offset"))
        for item in kit["papers"]:
            fix = QUOTE_FIX.get((p["id"], item["key"]))
            if fix:
                item["quote"] = fix  # same dict object as in buy/claim lists
        for item in kit["papers"] + ([kit["initial_wait"]] if kit["initial_wait"] else []):
            page = next(x["text"] for x in doc["pages"] if x["page"] == item["pdf_page"])
            assert norm(item["quote"]) in norm(page), (p["id"], item.get("key"), item["quote"][:80])
            # never ship OCR noise as an "exact line"
            assert not garbled(item["quote"], 0.2), (p["id"], item.get("key"), "garbled quote", item["quote"][:80])
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
