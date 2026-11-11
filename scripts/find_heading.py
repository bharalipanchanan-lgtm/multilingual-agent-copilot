"""For facts with no section: list clause numbers / headings above the quote
(same page, then the page before), nearest last."""
import json
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from diag_quotes import CAT, PAGES, norm_map, norm  # noqa: E402

HEAD = re.compile(
    r"(?:Section\s+[A-Z]?[\-\s]?\d+(?:\.\d+)*(?:\s*[-–]\s*[A-Z][\w /&]{2,40})?"
    r"|\b[A-Z]?\d{1,2}(?:\.\d{1,2}){1,3}\.?\s+[A-Z][\w /&()\-]{3,50}"
    r"|Code\s*[-–]?\s*Excl\s?\d+"
    r"|Annexure\s*[-–]?\s*[IVX]+[:\s][\w /&\-]{0,50}"
    r"|\b\d{1,2}\.\s?[A-Z][A-Za-z /&\-]{3,45}:"
    r"|\b[a-z]\)\s+[A-Z][A-Za-z /&\-]{3,45}:)")

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
        n = f["pdf_page"]
        page = pages[n]
        np_, idx = norm_map(page)
        i = np_.find(norm(f["quote"]))
        here = re.sub(r"\s+", " ", page[: idx[i] if i >= 0 else 0])
        prev = re.sub(r"\s+", " ", pages.get(n - 1, ""))
        hits = [("p%d" % (n - 1), m.group(0)) for m in HEAD.finditer(prev)][-4:] + \
               [("p%d" % n, m.group(0)) for m in HEAD.finditer(here)][-6:]
        print(f"\n#### {name} p{n}")
        for pg, h in hits:
            print(f"   {pg}: {h.strip()}")
