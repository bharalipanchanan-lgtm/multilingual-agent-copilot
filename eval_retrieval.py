"""Measure whether retrieval surfaces the right clause before any LLM is involved.

Step 1: python eval_retrieval.py --init       writes blank gold files per policy
Step 2: fill each gold file by reading the PDF (see README)
Step 3: python eval_retrieval.py              scores retrieval, prints refusal-threshold hint
"""
import argparse
import csv
import re
import statistics
import time
from collections import defaultdict

import yaml

from config import GOLD_DIR, MANIFEST, QUESTIONS, REPORT_DIR

FIELDS = ["qid", "question", "answerable", "gold_pages", "key_phrases", "gold_answer", "notes"]


def load_questions():
    return yaml.safe_load(open(QUESTIONS, encoding="utf-8"))


def init_gold():
    qs = load_questions()
    for r in csv.DictReader(open(MANIFEST, encoding="utf-8")):
        path = GOLD_DIR / f"{r['policy_id']}.csv"
        if path.exists():
            print(f"keep  {path.name} (already exists)")
            continue
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            for q in qs:
                w.writerow({"qid": q["id"], "question": q["text"]})
        print(f"wrote {path.name}")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower())


def run(k: int):
    from retrieve import search  # heavy import kept out of --init

    qs = {q["id"]: q for q in load_questions()}
    rows, by_lang = [], defaultdict(list)
    ans_scores, trap_scores = [], []

    for r in csv.DictReader(open(MANIFEST, encoding="utf-8")):
        pid = r["policy_id"]
        gpath = GOLD_DIR / f"{pid}.csv"
        if not gpath.exists():
            continue
        for g in csv.DictReader(open(gpath, encoding="utf-8")):
            label = (g["answerable"] or "").strip().lower()
            if label not in ("yes", "no"):
                continue  # not labelled yet
            q = qs[g["qid"]]
            hits = search(q["text"], pid, k)
            top = hits[0]["score"] if hits else 0.0
            if label == "no":
                trap_scores.append(top)
                rows.append([pid, g["qid"], q["lang"], "no", "", "", top, ""])
                continue
            pages = [int(p) for p in re.split(r"[;,]", g["gold_pages"]) if p.strip().isdigit()]
            phrases = [norm(p) for p in g["key_phrases"].split("|") if p.strip()]

            def ok(sub):
                page_hit = any(h["page"] in pages for h in sub)
                text = norm(" ".join(h["text"] for h in sub))
                phrase_hit = any(p in text for p in phrases)
                return page_hit or phrase_hit

            h3, hk = ok(hits[:3]), ok(hits[:k])
            ans_scores.append(top)
            by_lang[q["lang"]].append((h3, hk))
            rows.append([pid, g["qid"], q["lang"], "yes", int(h3), int(hk), top,
                         ";".join(f"p{h['page']}" for h in hits[:k])])

    if not rows:
        print("No labelled gold rows found. Fill the answerable column first.")
        return

    REPORT_DIR.mkdir(exist_ok=True)
    out = REPORT_DIR / f"retrieval_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["policy", "qid", "lang", "answerable", "hit_at_3", f"hit_at_{k}", "top_score", "pages_returned"])
        w.writerows(rows)

    allr = [x for v in by_lang.values() for x in v]
    print(f"\nAnswerable questions scored: {len(allr)}")
    print(f"Recall@3: {sum(a for a, _ in allr) / len(allr):.0%}   Recall@{k}: {sum(b for _, b in allr) / len(allr):.0%}")
    for lang, v in sorted(by_lang.items()):
        print(f"  {lang:9} n={len(v):2}  recall@3 {sum(a for a, _ in v) / len(v):.0%}  recall@{k} {sum(b for _, b in v) / len(v):.0%}")

    if ans_scores and trap_scores:
        lo, hi = min(ans_scores), max(trap_scores)
        print(f"\nLowest top score on answerable questions: {lo:.3f}")
        print(f"Highest top score on not-stated questions: {hi:.3f}")
        if lo > hi:
            print(f"Separable. Suggested refusal threshold: {(lo + hi) / 2:.3f}")
        else:
            print("Overlapping ranges. A score threshold alone cannot gate refusals; "
                  "the LLM must also judge whether the clause answers the question.")
        print(f"Median top score, answerable {statistics.median(ans_scores):.3f}, not stated {statistics.median(trap_scores):.3f}")
    print(f"\nReport: {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("-k", type=int, default=6)
    a = ap.parse_args()
    init_gold() if a.init else run(a.k)
