"""Set Tata MediCare Plus claim_form quote to a verified contiguous line on PDF page 21."""
import json
import pathlib
import re
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAT = ROOT / "web" / "data" / "catalogue.json"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return re.sub(r"[^a-z0-9]", "", s.lower())


def main() -> None:
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    p = next(x for x in cat["products"] if x["id"] == "tata-aig-medicare-plus")
    doc = cat["documents"][p["id"]]
    pages = json.loads((ROOT / "data" / "pages" / (doc["source"][:-4] + ".json")).read_text(encoding="utf-8"))
    page = next(x for x in pages["pages"] if x["page"] == 21)
    flat = re.sub(r"\s+", " ", page["text"])
    quote = "Such documentation will include the fol owing: r claim form, duIly completed Ou11 a."
    assert norm(quote) in norm(flat), repr(flat[flat.lower().find("claim") - 40 : flat.lower().find("claim") + 80])
    for bucket in ("claim_papers", "papers"):
        for item in p["close_kit"].get(bucket) or []:
            if item.get("key") == "claim_form":
                item["quote"] = quote
                item["pdf_page"] = 21
                item["phase"] = "claim"
    CAT.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("tata-aig-medicare-plus.close_kit.claim_form updated")


if __name__ == "__main__":
    main()
