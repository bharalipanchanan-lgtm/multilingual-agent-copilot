"""Show why catalogue quotes no longer match data/pages (pdftotext text).

    .venv/Scripts/python scripts/diag_quotes.py [--fix]

For each failing quote: matched blocks between the normalised quote and the
normalised cited page. With --fix, a quote whose words all occur on the page
in order (only the layout between them differs) is replaced by the page's own
text span covering the same words, so the quote stays the same clause.
"""
import json
import pathlib
import re
import sys
import unicodedata
from difflib import SequenceMatcher

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAT = ROOT / "web" / "data" / "catalogue.json"
PAGES = ROOT / "data" / "pages"


def norm_map(s):
    """Normalised string plus, for each kept char, its index in s."""
    out, idx = [], []
    for i, ch in enumerate(s):
        for c in unicodedata.normalize("NFKD", ch).lower():
            if "a" <= c <= "z" or "0" <= c <= "9":
                out.append(c)
                idx.append(i)
    return "".join(out), idx


def norm(s):
    return norm_map(s)[0]


def main():
    fix = "--fix" in sys.argv
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    docs = {}
    for pid, d in cat["documents"].items():
        f = PAGES / (d["source"][:-4] + ".json")
        docs[pid] = {p["page"]: p["text"] for p in json.loads(f.read_text(encoding="utf-8"))["pages"]}
    changed = 0
    for p in cat["products"]:
        pages = docs.get(p["id"])
        if not pages:
            continue
        for key, f in p["facts"].items():
            if not f.get("stated") or not f.get("quote"):
                continue
            q = norm(f["quote"])
            page = pages.get(f["pdf_page"], "")
            np_, idx = norm_map(page)
            if q in np_:
                continue
            others = [n for n, t in pages.items() if q in norm(t)]
            sm = SequenceMatcher(None, q, np_, autojunk=False)
            blocks = [b for b in sm.get_matching_blocks() if b.size >= 8]
            cover = sum(b.size for b in blocks)
            print(f"\n== {p['id']}.{key}  page {f['pdf_page']}  other pages {others}  cover {cover}/{len(q)}")
            print("   quote:", f["quote"][:300])
            if blocks:
                a, b = blocks[0].b, blocks[-1].b + blocks[-1].size
                span = page[idx[a]: idx[b - 1] + 1]
                print("   page :", re.sub(r"\s+", " ", span)[:600])
                if fix and cover >= len(q) * 0.9 and b - a <= len(q) * 1.6:
                    new = re.sub(r"\s+", " ", span).strip()
                    f["quote"] = new
                    changed += 1
                    print("   -> replaced")
    if fix and changed:
        CAT.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n{changed} quotes replaced")


if __name__ == "__main__":
    main()
