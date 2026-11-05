"""Run the demo conversation against the running server N times and report status and timing.

  python demo_check.py [rounds]      (server must be running on localhost:8000)

The check behaves like the chat page: it starts with no policy, follows the "policy" events
the server sends, and re-asks a question that was held while the agent chose a policy.
"""
import json
import sys
import time
import urllib.request

SCRIPT = [
    ("Diabetes ke liye waiting period kitna hai?", "choose_policy"),   # no policy chosen yet
    ("National Mediclaim policy dekhna hai", "selected"),               # then the held question
    (None, "answered"),                                                 # is re-asked automatically
    ("Kya ICU charges par bhi room rent ka cap lagta hai?", "answered"),
    ("What is the premium for a 45 year old for 10 lakh?", "refused"),
    ("Is there any co-payment?", "not_stated"),
    ("क्या इस पॉलिसी में पहले से मौजूद बीमारियों के लिए वेटिंग पीरियड है?", "answered"),
    ("Is maternity covered?", "answered"),
    ("ab SBI wali policy dekhni hai", "selected"),                      # switch mid conversation
    ("Is maternity covered?", "answered"),
    ("Compare the diabetes waiting period across policies", "compared"),
]


def ask(q, policy_id):
    body = json.dumps({"question": q, "policy_id": policy_id}).encode()
    req = urllib.request.Request("http://localhost:8000/api/ask", body, {"Content-Type": "application/json"})
    t0, first, final, chosen = time.time(), None, None, None
    with urllib.request.urlopen(req, timeout=180) as r:
        for line in r:
            line = line.decode().strip()
            if not line.startswith("data: "):
                continue
            ev = json.loads(line[6:])
            if ev["type"] == "policy":
                chosen = ev["policy_id"]
            if ev["type"] == "token" and first is None:
                first = time.time() - t0
            if ev["type"] == "final":
                final = ev
    return final, chosen, first, time.time() - t0


rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 1
fails = total_steps = 0
for n in range(rounds):
    policy, pending = None, None
    for q, want in SCRIPT:
        if q is None:
            q, pending = pending, None
            if q is None:
                print(f"r{n + 1} BAD no held question to re-ask")
                fails += 1
                total_steps += 1
                continue
        ev, chosen, first, total = ask(q, policy)
        policy = chosen or policy
        if ev and ev["status"] == "choose_policy" and ev.get("pending"):
            pending = q
        ok = ev and ev["status"] == want
        fails += not ok
        total_steps += 1
        print(f"r{n + 1} {'OK ' if ok else 'BAD'} {ev['status'] if ev else None:13} {policy or '-':20} "
              f"first {first or 0:4.1f}s total {total:4.1f}s  {(ev or {}).get('answer', '')[:70]!r}")
print(f"\n{total_steps - fails}/{total_steps} as expected")
