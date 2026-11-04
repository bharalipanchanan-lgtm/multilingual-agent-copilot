"""End to end check of generated answers against the gold file (Phase 1 exit criteria).

  python eval_answers.py                       all labelled policies, configured backend
  python eval_answers.py --backend extractive  no LLM

Reports per question: status, whether a not-stated question was refused, numbers the
answer used that are not in the gold answer (a hint for a human, not a verdict),
blocked drafts, and latency. Writes eval/reports/answers_<time>.csv.
"""
import argparse
import csv
import time

from answer import _numbers, ask
from config import GOLD_DIR, MANIFEST, REPORT_DIR
from generate import get_generator


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend")
    ap.add_argument("--only", help="comma separated qids")
    a = ap.parse_args()
    gen = get_generator(a.backend)
    only = set(a.only.split(",")) if a.only else None
    rows = []
    for r in csv.DictReader(open(MANIFEST, encoding="utf-8")):
        gpath = GOLD_DIR / f"{r['policy_id']}.csv"
        if not gpath.exists():
            continue
        for g in csv.DictReader(open(gpath, encoding="utf-8")):
            label = (g["answerable"] or "").strip().lower()
            if label not in ("yes", "no") or (only and g["qid"] not in only):
                continue
            res = ask(g["question"], r["policy_id"], gen)
            status = res.get("status")
            refused = status in ("not_stated", "refused")
            gold_nums = _numbers(g["gold_answer"])
            extra = sorted(_numbers(res.get("answer", "")) - gold_nums - {str(c["n"]) for c in res.get("citations", [])})
            ok = (refused if label == "no" else (status == "answered"))
            rows.append({"policy": r["policy_id"], "qid": g["qid"], "answerable": label, "status": status,
                         "pass_basic": int(ok), "numbers_not_in_gold": " ".join(extra),
                         "pages_cited": " ".join(f"p{c['page']}" for c in res.get("citations", [])),
                         "gold_pages": g["gold_pages"], "ms": res.get("ms"),
                         "first_token_ms": res.get("first_token_ms"),
                         "answer": res.get("answer", "").replace("\n", " "),
                         "draft_if_blocked": (res.get("draft") or "").replace("\n", " "),
                         "unsupported_numbers": " ".join(res.get("unsupported_numbers") or [])})
            print(f"{g['qid']} [{status:10}] {res.get('ms')}ms  {res.get('answer', '')[:110]!r}")
    if not rows:
        print("No labelled gold rows.")
        return
    REPORT_DIR.mkdir(exist_ok=True)
    out = REPORT_DIR / f"answers_{gen.name}_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    traps = [x for x in rows if x["answerable"] == "no"]
    ans = [x for x in rows if x["answerable"] == "yes"]
    print(f"\nBackend {gen.name}")
    print(f"Not-stated questions refused: {sum(x['pass_basic'] for x in traps)}/{len(traps)}")
    print(f"Answerable questions answered: {sum(x['pass_basic'] for x in ans)}/{len(ans)}")
    print(f"Drafts blocked by number check: {sum(x['status'] == 'blocked' for x in rows)}")
    lat = sorted(x["ms"] for x in rows if x["ms"])
    if lat:
        print(f"Latency median {lat[len(lat) // 2]} ms, max {lat[-1]} ms")
    print(f"Report: {out}  (read the answers; pass_basic is not a correctness score)")


if __name__ == "__main__":
    main()
