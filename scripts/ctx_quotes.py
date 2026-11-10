"""Print failing facts with the pdftotext context around their topic word."""
import json
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from diag_quotes import CAT, PAGES, norm  # noqa: E402
from fix_quotes import TOPIC  # noqa: E402

WORD = {"ayush": r"ayush", "cataract": r"cataract", "robotic_surgery": r"robotic",
        "room_rent": r"room", "ped_wait_months": r"pre-?\s?existing", "entry_age_max": r"entry age",
        "diabetes_wait": r"diabet"}

cat = json.loads(CAT.read_text(encoding="utf-8"))
only = set(sys.argv[1:])
for p in cat["products"]:
    d = cat["documents"][p["id"]]
    pages = {x["page"]: x["text"] for x in json.loads((PAGES / (d["source"][:-4] + ".json")).read_text(encoding="utf-8"))["pages"]}
    for key, f in p["facts"].items():
        if not f.get("stated") or not f.get("quote"):
            continue
        name = f"{p['id']}.{key}"
        if only and name not in only:
            continue
        page = pages.get(f["pdf_page"], "")
        if norm(f["quote"]) in norm(page) and not only:
            continue
        print(f"\n######## {name}  page {f['pdf_page']}  value={f.get('value')!r} unit={f.get('unit')} section={f.get('section')!r}")
        print("QUOTE:", f["quote"])
        flat = re.sub(r"\s+", " ", page)
        for m in re.finditer(WORD[key], flat, re.I):
            print("  ...", flat[max(0, m.start() - 250): m.end() + 350])
