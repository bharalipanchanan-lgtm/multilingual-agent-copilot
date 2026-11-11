"""Print the text before each section-less fact's quote, to read its clause number."""
import json
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from diag_quotes import CAT, PAGES, norm_map, norm  # noqa: E402

KEYS = ("cataract", "ayush", "robotic_surgery", "ped_wait_months", "room_rent", "entry_age_max")
cat = json.loads(CAT.read_text(encoding="utf-8"))
only = set(sys.argv[1:])
for p in cat["products"]:
    d = cat["documents"][p["id"]]
    pages = {x["page"]: x["text"] for x in json.loads((PAGES / (d["source"][:-4] + ".json")).read_text(encoding="utf-8"))["pages"]}
    for k in KEYS:
        f = p["facts"].get(k)
        if not f or not f.get("stated") or f.get("section"):
            continue
        name = f"{p['id']}.{k}"
        if only and name not in only:
            continue
        page = pages[f["pdf_page"]]
        np_, idx = norm_map(page)
        i = np_.find(norm(f["quote"]))
        start = idx[i] if i >= 0 else 0
        before = re.sub(r"\s+", " ", page[max(0, start - 700): start])
        print(f"\n#### {name} p{f['pdf_page']}\n  BEFORE: {before}\n  QUOTE: {f['quote'][:160]}")
