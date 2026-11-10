"""peek.py <product-id> <page> <regex> [chars] — show page text around a match."""
import json
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
cat = json.loads((ROOT / "web/data/catalogue.json").read_text(encoding="utf-8"))
pid, n, pat = sys.argv[1], int(sys.argv[2]), sys.argv[3]
w = int(sys.argv[4]) if len(sys.argv) > 4 else 250
src = cat["documents"][pid]["source"][:-4]
pages = {p["page"]: p["text"] for p in json.loads((ROOT / f"data/pages/{src}.json").read_text(encoding="utf-8"))["pages"]}
t = re.sub(r"\s+", " ", pages[n])
for m in re.finditer(pat, t, re.I):
    print(f"[{pid} p{n}] ...{t[max(0, m.start() - w): m.end() + w]}...\n")
