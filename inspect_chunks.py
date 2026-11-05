"""Dump what the parser extracted so a human can read it before trusting retrieval.
Usage: python inspect_chunks.py <policy_id>   ->  data/dumps/<policy_id>.txt
"""
import csv
import re
import sys

from config import MANIFEST, POLICY_DIR, ROOT
from parse import manifest_args, parse_pdf

pid = sys.argv[1]
r = next(x for x in csv.DictReader(open(MANIFEST, encoding="utf-8")) if x["policy_id"] == pid)
offset = int(r.get("page_offset") or 0)
parsed = parse_pdf(*manifest_args(r, POLICY_DIR))

out = ROOT / "data" / "dumps"
out.mkdir(exist_ok=True)
path = out / f"{pid}.txt"
with open(path, "w", encoding="utf-8") as f:
    for i, c in enumerate(parsed["chunks"]):
        f.write(f"--- chunk {i} | physical page {c['page']} | printed page {c['page'] - offset} | "
                f"{c['type']} | part: {c.get('part', '')} | section: {c['section']} | plans: {c.get('plans', '')}\n"
                f"{c['text']}\n\n")

sizes = [len(c["text"]) for c in parsed["chunks"]]
garbled = sum(bool(re.search(r"(?:\b\w{1,2}\b\s+){10,}", c["text"])) for c in parsed["chunks"])
print(f"pages {parsed['n_pages']}  chunks {len(sizes)}  avg {sum(sizes)//max(len(sizes),1)} chars  max {max(sizes)}")
print(f"sparse pages: {parsed['sparse_pages']}   chunks with long runs of 1-2 letter tokens (possible garble): {garbled}")
print(f"wrote {path}")
