"""Replace the two 3-page summaries (fix list item 6).

    .venv/Scripts/python scripts/replace_summaries.py <full-elevate.pdf>

- ICICI Lombard Elevate: the 3-page summary is replaced by the full policy
  wording; pages are re-extracted and every fact is rebuilt from it with
  ingest/build_facts.py, so no fact from the summary survives.
- Max Life "Smart Health Rider": no full health policy wording exists for it
  (Smart Secure Plus is a term life plan), so the product is removed from the
  catalogue and manifest until a wording is found.
"""
import csv
import json
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ingest"))
import extract  # noqa: E402
import build_facts  # noqa: E402

POL = ROOT / "data" / "policies"
PAGES = ROOT / "data" / "pages"
CAT = ROOT / "web" / "data" / "catalogue.json"
MANIFEST = POL / "manifest.csv"

ELEVATE_PDF = "6-icici-elevate.pdf"
ELEVATE_URL = "https://www.icicilombard.com/docs/default-source/default-document-library/elevate.pdf"
ELEVATE_STRIP = (r"(?m)^ICICI Lombard General Insurance Company Limited\s*$|IRDA Reg\. No\. 115[^\n]*|CIN: L67200MH2000PLC129408[^\n]*"
                 r"|^UIN:?\s*ICIHLIP27062V072627[^\n]*|^Mailing Address:[^\n]*|^Registered Office Address:[^\n]*|^Toll free no:[^\n]*"
                 r"|^Alternate no ?:[^\n]*|^E-mail: customersupport@icicilombard\.com[^\n]*|^Website ?: www\.icicilombard\.com[^\n]*")
MAX_ID, MAX_PID, MAX_PDF = "max-life-smart-secure-plus", "max_life_smart_secure_plus", "7-max-life-smart-secure-plus.pdf"


def main(src: str) -> int:
    shutil.copyfile(src, POL / ELEVATE_PDF)
    r = extract.extract(POL / ELEVATE_PDF, PAGES)
    print("extracted", r)

    b = build_facts.build_one({"file": ELEVATE_PDF, "#": "0", "insurer": "ICICI Lombard", "policy": "Elevate",
                               "uin": "ICIHLIP27062V072627", "url": ELEVATE_URL})
    pages_text = " ".join(p["text"] for p in json.loads((PAGES / "6-icici-elevate.json").read_text(encoding="utf-8"))["pages"])
    assert b["doc"]["uin"] == "ICIHLIP27062V072627" and "ICIHLIP27062V072627" in pages_text, b["doc"]

    cat = json.loads(CAT.read_text(encoding="utf-8"))
    for p in cat["products"]:
        if p["id"] == "icici-elevate":
            p.update(insurer="ICICI Lombard", name="Elevate", variant=None, status="active",
                     uin=b["doc"]["uin"], source_url=ELEVATE_URL, facts=b["product"]["facts"])
            p["differentiator"] = build_facts.differentiator(p)
            p.pop("close_kit", None)
    cat["documents"]["icici-elevate"] = b["doc"]
    cat["products"] = [p for p in cat["products"] if p["id"] != MAX_ID]
    cat["documents"].pop(MAX_ID, None)
    n = len(cat["documents"])
    cat["catalogue"]["source"] = f"{n} insurer policy wordings + plan variants, verified page by page."
    cat["_provenance"]["built_from"] = f"{n} policy wordings (PDF) in data/policies/"
    CAT.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows = list(csv.DictReader(open(MANIFEST, encoding="utf-8")))
    fields = list(rows[0].keys())
    out = []
    for row in rows:
        if row["policy_id"] == MAX_PID:
            continue
        if row["policy_id"] == "icici_elevate":
            off = b["doc"]["page_offset"]
            row.update(insurer="ICICI Lombard", product="ICICI Lombard Elevate",
                       page_offset=str(-off) if off is not None else "0", strip_regex=ELEVATE_STRIP)
        out.append(row)
    with open(MANIFEST, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(out)

    for f in (POL / MAX_PDF, PAGES / "7-max-life-smart-secure-plus.json"):
        if f.exists():
            f.unlink()
    print(f"catalogue: {len(cat['products'])} products, {n} documents; manifest {len(out)} rows")
    for k, x in b["product"]["facts"].items():
        print(f"  {k:30} {(x['value'] if x['stated'] else '— ' + x['note'])!s:.90}  p{x.get('pdf_page')} {x.get('section') or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
