"""Re-anchor catalogue quotes on the pdftotext page text.

    .venv/Scripts/python scripts/fix_quotes.py [--write]

A failing quote is shrunk to the longest run of it that is contiguous on the
cited page (list markers and column gutters split the rest). The run is kept
only if it still names the fact's topic and carries the fact's own number;
otherwise the fact is listed for a manual fix. Nothing is invented: the new
quote is the page's own text.
"""
import json
import pathlib
import re
import sys
from difflib import SequenceMatcher

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from diag_quotes import CAT, PAGES, norm, norm_map  # noqa: E402

TOPIC = {
    "ayush": "ayush", "cataract": "cataract", "robotic_surgery": "robotic",
    "room_rent": "room", "ped_wait_months": "preexisting", "entry_age_max": "age",
    "diabetes_wait": "",
}
NUMWORD = {1: ["one"], 2: ["two"], 3: ["three"], 4: ["four"], 5: ["five"], 12: ["twelve"],
           24: ["twentyfour"], 36: ["thirtysix"], 48: ["fortyeight"]}


def has_value(f, q):
    v = f.get("value")
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return True
    v = int(v) if float(v).is_integer() else v
    if str(v) in q or any(w in q for w in NUMWORD.get(v, [])):
        return True
    if f.get("unit") == "months" and v % 12 == 0:
        y = v // 12
        return any(w + "year" in q for w in [str(y), *NUMWORD.get(y, [])])
    return False


def main():
    write = "--write" in sys.argv
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    docs = {}
    for pid, d in cat["documents"].items():
        f = PAGES / (d["source"][:-4] + ".json")
        docs[pid] = {p["page"]: p["text"] for p in json.loads(f.read_text(encoding="utf-8"))["pages"]}
    fixed, manual = 0, []
    for p in cat["products"]:
        pages = docs.get(p["id"])
        for key, f in p["facts"].items():
            if not f.get("stated") or not f.get("quote"):
                continue
            q = norm(f["quote"])
            page = pages.get(f["pdf_page"], "")
            np_, idx = norm_map(page)
            if q in np_:
                continue
            m = SequenceMatcher(None, q, np_, autojunk=False).find_longest_match(0, len(q), 0, len(np_))
            run = np_[m.b: m.b + m.size]
            topic = TOPIC.get(key, "")
            if m.size >= 25 and topic in run and has_value(f, run):
                span = page[idx[m.b]: idx[m.b + m.size - 1] + 1]
                new = re.sub(r"\s+", " ", span).strip()
                print(f"ok   {p['id']}.{key}\n     {f['quote'][:140]}\n  -> {new[:140]}")
                f["quote"] = new
                fixed += 1
            else:
                manual.append(f"{p['id']}.{key}")
    print(f"\n{fixed} re-anchored; manual: {len(manual)}")
    for m in manual:
        print("  ", m)
    if write:
        CAT.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
