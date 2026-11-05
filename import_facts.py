"""Load the handoff fact table into facts/ and keep the review CSV in step with it.

  python import_facts.py                 handoff/fact_table_prefill.json + review CSV -> facts/<policy_id>.json
  python import_facts.py --export        facts/*.json -> facts/review/fact_table_review.csv (for a person)
  python import_facts.py --apply FILE    write a person's verified, verified_by, verified_on and any value
                                         or status edits from a review CSV back into facts/*.json

The JSON in facts/ is the single source of truth. On import, the review CSV is used only for
needs_extra_care (the JSON does not carry it), and every disagreement between the two handoff
files is printed so a person can see it; the JSON wins.
"""
import argparse
import csv
import json
import re
from collections import defaultdict

from config import FACTS_DIR, ROOT
from fact_table import ROW_FIELDS, load_facts, manifest

HANDOFF = ROOT / "handoff"
REVIEW_CSV = FACTS_DIR / "review" / "fact_table_review.csv"
CSV_FIELDS = ["policy_id", "plan", "attribute", "value", "status", "needs_extra_care", "pages",
              "evidence_quotes", "note", "verified", "verified_by", "verified_on"]
QUOTE_SEP = "  ||  "


def csv_quotes(cell: str) -> list[tuple[int, str]]:
    """'p38: text  ||  p18: text' -> [(38, text), (18, text)]. Some handoff rows use ' | ' instead."""
    parts = re.split(r"\s+\|\|?\s+(?=p\d+: )", cell.strip()) if cell.strip() else []
    out = []
    for p in parts:
        m = re.match(r"p(\d+): (.*)$", p, re.S)
        out.append((int(m.group(1)), m.group(2).strip()) if m else (None, p))
    return out


def do_import():
    rows = json.load(open(HANDOFF / "fact_table_prefill.json", encoding="utf-8"))
    review = {(r["policy_id"], r["plan"], r["attribute"]): r
              for r in csv.DictReader(open(HANDOFF / "fact_table_review.csv", encoding="utf-8-sig"))}
    man = manifest()
    by_policy, diffs = defaultdict(list), []
    for r in rows:
        key = (r["policy_id"], r["plan"], r["attribute"])
        c = review.get(key)
        if c is None:
            diffs.append(f"{key}: in JSON, missing from review CSV")
        else:
            if c["value"] != r["value"]:
                diffs.append(f"{key}: value differs")
            if c["status"] != r["status"]:
                diffs.append(f"{key}: status differs ({c['status']} vs {r['status']})")
            jq = [(e["page"], e["quote"]) for e in r["evidence"]]
            if csv_quotes(c["evidence_quotes"]) != jq:
                diffs.append(f"{key}: evidence quotes differ")
            pages = sorted({int(x) for x in c["pages"].split(";") if x.strip()})
            if pages != sorted({e["page"] for e in r["evidence"]}):
                diffs.append(f"{key}: pages {pages} vs evidence pages")
        row = {k: r.get(k) for k in ROW_FIELDS if k != "needs_extra_care"}
        row["needs_extra_care"] = bool(c and c["needs_extra_care"].strip().lower() == "yes")
        row["verified"] = bool(r.get("verified"))
        by_policy[r["policy_id"]].append({k: row[k] for k in ROW_FIELDS})
    for key in review.keys() - {(r["policy_id"], r["plan"], r["attribute"]) for r in rows}:
        diffs.append(f"{key}: in review CSV, missing from JSON")

    for pid, prow in by_policy.items():
        m = man[pid]
        out = {"format": 2, "policy_id": pid, "insurer": m["insurer"], "product": m["product"],
               "source": "handoff/fact_table_prefill.json, needs_extra_care from handoff/fact_table_review.csv",
               "rows": prow}
        path = FACTS_DIR / f"{pid}.json"
        if path.exists() and json.load(open(path, encoding="utf-8")).get("format") == 2:
            print(f"OVERWRITE {path.name}")
        json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"wrote facts/{path.name}: {len(prow)} rows, "
              f"{sum(r['needs_extra_care'] for r in prow)} need extra care")
    print(f"\n{len(rows)} rows imported. Differences between the two handoff files (JSON kept): {len(diffs)}")
    for d in diffs:
        print("  " + d)


def do_export():
    REVIEW_CSV.parent.mkdir(exist_ok=True)
    n = 0
    with open(REVIEW_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        for f in load_facts():
            if f["legacy"]:
                print(f"skip {f['file']}: legacy format, rebuilt in task 5")
                continue
            # needs_extra_care rows first, as the handoff verification flow asks
            for r in sorted(f["rows"], key=lambda r: not r["needs_extra_care"]):
                w.writerow({"policy_id": f["policy_id"], "plan": r["plan"], "attribute": r["attribute"],
                            "value": r["value"], "status": r["status"],
                            "needs_extra_care": "yes" if r["needs_extra_care"] else "",
                            "pages": ";".join(str(p) for p in sorted({e["page"] for e in r["evidence"]})),
                            "evidence_quotes": QUOTE_SEP.join(f"p{e['page']}: {e['quote']}" for e in r["evidence"]),
                            "note": r["note"], "verified": "yes" if r["verified"] else "",
                            "verified_by": r["verified_by"] or "", "verified_on": r["verified_on"] or ""})
                n += 1
    print(f"wrote {REVIEW_CSV.relative_to(ROOT)}: {n} rows")


def do_apply(path):
    edits = {(r["policy_id"], r["plan"], r["attribute"]): r for r in csv.DictReader(open(path, encoding="utf-8-sig"))}
    changed = 0
    for f in load_facts():
        if f["legacy"]:
            continue
        for r in f["rows"]:
            e = edits.get((f["policy_id"], r["plan"], r["attribute"]))
            if not e:
                continue
            new = {"value": e["value"], "status": e["status"],
                   "verified": e["verified"].strip().lower() in ("yes", "true", "1"),
                   "verified_by": e["verified_by"].strip() or None, "verified_on": e["verified_on"].strip() or None}
            if new["status"] not in ("stated", "not_stated", "unclear"):
                raise SystemExit(f"{f['policy_id']} {r['plan']} {r['attribute']}: bad status {new['status']!r}")
            if any(r[k] != v for k, v in new.items()):
                if r["value"] != new["value"] or r["status"] != new["status"]:
                    print(f"  edited {f['policy_id']} {r['plan']} {r['attribute']}")
                r.update(new)
                changed += 1
        src = FACTS_DIR / f["file"]
        doc = json.load(open(src, encoding="utf-8"))
        doc["rows"] = f["rows"]
        json.dump(doc, open(src, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{changed} rows updated. Run pytest tests/test_fact_quotes.py again.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--apply")
    a = ap.parse_args()
    do_export() if a.export else do_apply(a.apply) if a.apply else do_import()
