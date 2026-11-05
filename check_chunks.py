"""Acceptance check for parsing and ingest (handoff task 1).

  python check_chunks.py            all policies in the manifest
  python check_chunks.py --index    also check page and printed_page on every stored chunk in Chroma

Three checks per policy:
  size     no chunk longer than CHUNK_MAX characters
  leaks    no running header or footer inside a chunk. Running lines are found independently of
           the manifest strip_regex: any raw text line that repeats on at least 40% of pages
           (and on 3 or more pages) counts as a header or footer. Each is then searched for in
           the chunk text, after whitespace normalisation.
  pages    every chunk has a physical page within the document; with --index every stored
           chunk also has printed_page = page - page_offset.
  review   chunks containing header-like tokens (UIN codes, CIN, "Page n of m", IRDAI Reg) are
           listed for a human to read. Body text can cite a UIN legitimately, so these do not
           fail the check on their own; a one-off header block shows up here.
Exit code 1 if any check fails. Failures are listed, not hidden.
"""
import argparse
import csv
import re
import sys
from collections import Counter

import pymupdf

from config import CHROMA_DIR, CHUNK_MAX, COLLECTION, MANIFEST, POLICY_DIR
from parse import manifest_args, parse_pdf


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def running_lines(path, skip: set[int]) -> list[str]:
    doc = pymupdf.open(path)
    pages = [i + 1 for i in range(doc.page_count) if i + 1 not in skip]
    seen = Counter()
    for pno in pages:
        lines = {norm(l) for l in doc[pno - 1].get_text("text").splitlines()}
        # digits vary from page to page ("Page 3 of 75"), so compare with digits masked
        seen.update({re.sub(r"\d+", "#", l) for l in lines if len(l) >= 12})
    need = max(3, int(0.4 * len(pages)))
    return [l for l, n in seen.items() if n >= need]


SIGNATURE = re.compile(r"UIN[: ]*[A-Z]{6,}\w+|P a g e|Page \d+ of \d+|IRDAI? Reg|Corporate Identity Number|"
                       r"CIN[: ]*(?:No\.)?[A-Z]\d{4,}|Registered Office")


def check_policy(r: dict) -> tuple[list[str], dict]:
    path, skip, strip_regex, plans = manifest_args(r, POLICY_DIR)
    parsed = parse_pdf(path, skip, strip_regex, plans)
    chunks = parsed["chunks"]
    fails = []
    for i, c in enumerate(chunks):
        if len(c["text"]) > CHUNK_MAX:
            fails.append(f"size: chunk {i} p{c['page']} has {len(c['text'])} chars")
        if not (1 <= c.get("page", 0) <= parsed["n_pages"]):
            fails.append(f"pages: chunk {i} has page {c.get('page')}")
    runners = running_lines(path, skip)
    masked = [(i, c["page"], re.sub(r"\d+", "#", norm(c["text"]))) for i, c in enumerate(chunks)]
    for line in runners:
        hits = [(i, p) for i, p, t in masked if line in t]
        if hits:
            where = ", ".join(f"chunk {i} p{p}" for i, p in hits[:4])
            fails.append(f"leak: running line {line[:70]!r} in {len(hits)} chunks ({where})")
    review = []
    for i, c in enumerate(chunks):
        for m in SIGNATURE.finditer(c["text"]):
            review.append(f"chunk {i} p{c['page']}: ...{c['text'][max(0, m.start() - 50):m.end() + 30]}...")
    sizes = [len(c["text"]) for c in chunks]
    stats = {"review": review, "pages": parsed["n_pages"], "chunks": len(chunks), "max": max(sizes, default=0),
             "running_lines": len(runners)}
    return fails, stats


def check_index(rows: list[dict]) -> list[str]:
    import chromadb
    col = chromadb.PersistentClient(path=str(CHROMA_DIR)).get_collection(COLLECTION, embedding_function=None)
    fails = []
    for r in rows:
        offset = int(r.get("page_offset") or 0)
        res = col.get(where={"policy_id": r["policy_id"]}, include=["metadatas"])
        if not res["ids"]:
            fails.append(f"index: {r['policy_id']} has no chunks in Chroma")
        for cid, m in zip(res["ids"], res["metadatas"]):
            if not isinstance(m.get("page"), int) or not isinstance(m.get("printed_page"), int):
                fails.append(f"index: {cid} missing page or printed_page")
            elif m["printed_page"] != m["page"] - offset:
                fails.append(f"index: {cid} printed_page {m['printed_page']} != page {m['page']} - {offset}")
        print(f"  index {r['policy_id']:22} {len(res['ids'])} stored chunks checked")
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--index", action="store_true")
    a = ap.parse_args()
    rows = [r for r in csv.DictReader(open(MANIFEST, encoding="utf-8")) if not a.only or r["policy_id"] == a.only]
    all_fails = []
    print(f"{'policy':24} {'pages':>5} {'chunks':>6} {'max':>5} {'running lines':>13}  result")
    for r in rows:
        fails, s = check_policy(r)
        print(f"{r['policy_id']:24} {s['pages']:>5} {s['chunks']:>6} {s['max']:>5} {s['running_lines']:>13}  "
              f"{'PASS' if not fails else f'FAIL ({len(fails)})'}")
        all_fails += [f"{r['policy_id']}: {f}" for f in fails]
        for line in s["review"]:
            print(f"    review {line}")
    if a.index:
        all_fails += check_index(rows)
    for f in all_fails:
        print("  " + f)
    print(f"\n{'PASS' if not all_fails else 'FAIL'}: {len(all_fails)} problems, CHUNK_MAX {CHUNK_MAX}")
    sys.exit(1 if all_fails else 0)


if __name__ == "__main__":
    main()
