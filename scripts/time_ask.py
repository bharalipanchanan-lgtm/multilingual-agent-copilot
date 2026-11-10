"""Time one /api/ask call twice and confirm the second (cached) final matches the first."""
import sys
import time

sys.path.insert(0, __import__("os").path.dirname(__file__))
from warm_answer_cache import ask

base = "http://127.0.0.1:8000"
question, policy_id = sys.argv[1], sys.argv[2]
runs = []
for _ in range(2):
    t0 = time.time()
    f = ask(base, question, policy_id)
    runs.append((time.time() - t0, f))
    print(f"{runs[-1][0]:5.2f}s cached={bool(f.get('cached'))} status={f.get('status')} answer={f.get('answer', '')[:120]!r}")
same = all(runs[0][1].get(k) == runs[1][1].get(k) for k in ("status", "answer", "citations"))
print("same answer:", same)
