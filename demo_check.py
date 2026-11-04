"""Run the demo script against the running server N times and report status and timing.

  python demo_check.py [rounds]      (server must be running on localhost:8000)
"""
import json
import sys
import time
import urllib.request

SCRIPT = [
    ("Diabetes ke liye waiting period kitna hai?", "answered"),
    ("Kya ICU charges par bhi room rent ka cap lagta hai?", "answered"),
    ("What is the premium for a 45 year old for 10 lakh?", "refused"),
    ("Is there any co-payment?", "not_stated"),
    ("क्या इस पॉलिसी में पहले से मौजूद बीमारियों के लिए वेटिंग पीरियड है?", "answered"),
    ("Is maternity covered?", "answered"),
    ("Compare the diabetes waiting period across policies", "compared"),
]


def ask(q):
    body = json.dumps({"question": q, "policy_id": "national_mediclaim"}).encode()
    req = urllib.request.Request("http://localhost:8000/api/ask", body, {"Content-Type": "application/json"})
    t0, first, final = time.time(), None, None
    with urllib.request.urlopen(req, timeout=180) as r:
        for line in r:
            line = line.decode().strip()
            if not line.startswith("data: "):
                continue
            ev = json.loads(line[6:])
            if ev["type"] == "token" and first is None:
                first = time.time() - t0
            if ev["type"] == "final":
                final = ev
    return final, first, time.time() - t0


rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 1
fails = 0
for n in range(rounds):
    for q, want in SCRIPT:
        ev, first, total = ask(q)
        ok = ev and ev["status"] == want
        fails += not ok
        print(f"r{n + 1} {'OK ' if ok else 'BAD'} {ev['status'] if ev else None:10} first {first or 0:4.1f}s total {total:4.1f}s  {(ev or {}).get('answer', '')[:90]!r}")
print(f"\n{rounds * len(SCRIPT) - fails}/{rounds * len(SCRIPT)} as expected")
