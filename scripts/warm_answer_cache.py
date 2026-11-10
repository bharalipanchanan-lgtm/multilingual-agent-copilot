"""Fill data/answer_cache.json through the running server for the hard topics the fact table cannot answer.

Those questions go to retrieval + the LLM (about 10 s on CPU); once cached they return in milliseconds.
Usage: python scripts/warm_answer_cache.py [--base http://127.0.0.1:8000]
"""
import argparse
import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {
    "robotic_surgery": ["Is robotic surgery covered?", "robotic surgery covered hai?", "robotic surgery covered hai",
                        "robotic surgery ka limit kya hai?", "रोबोटिक सर्जरी कवर है?"],
    "cataract": ["Cataract limit?", "cataract limit kya hai?", "Is cataract covered?", "cataract covered hai?"],
    "ayush": ["AYUSH covered?", "ayush covered hai?", "Is AYUSH treatment covered?", "ayush limit kya hai?"],
}


def ask(base: str, question: str, policy_id: str) -> dict:
    req = urllib.request.Request(f"{base}/api/ask", method="POST", headers={"Content-Type": "application/json"},
                                 data=json.dumps({"question": question, "policy_id": policy_id}).encode())
    final = {}
    with urllib.request.urlopen(req, timeout=300) as r:
        for line in r.read().decode("utf-8").split("\n\n"):
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                if ev.get("type") == "final":
                    final = ev
    return final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    base = ap.parse_args().base
    cat = json.loads((ROOT / "web" / "data" / "catalogue.json").read_text(encoding="utf-8"))
    jobs = [(p.get("policy_id") or p["id"].replace("-", "_"), q)
            for p in cat["products"]
            for field, qs in FIELDS.items() if not (p["facts"].get(field) or {}).get("stated")
            for q in qs]
    print(f"{len(jobs)} questions")
    for i, (pid, q) in enumerate(jobs, 1):
        t0 = time.time()
        f = ask(base, q, pid)
        print(f"{i:>3}/{len(jobs)} {time.time() - t0:5.1f}s {'hit ' if f.get('cached') else 'new '}"
              f"{f.get('status', '?'):10} {pid} | {q}", flush=True)


if __name__ == "__main__":
    main()
