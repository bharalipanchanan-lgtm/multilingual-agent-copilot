import json
import time
import urllib.request
from pathlib import Path

pdf = Path("data/policies/2-hdfc-optima-secure.pdf").read_bytes()
boundary = "----bound" + str(int(time.time()))
parts = [
    (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="insurer"\r\n\r\nHDFC ERGO\r\n'
    ).encode(),
    (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="product"\r\n\r\nOptima Secure Upload\r\n'
    ).encode(),
    (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="2-hdfc-optima-secure.pdf"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode()
    + pdf
    + b"\r\n",
    f"--{boundary}--\r\n".encode(),
]
body = b"".join(parts)
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/upload",
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    method="POST",
)
t0 = time.time()
with urllib.request.urlopen(req, timeout=300) as r:
    data = json.load(r)
print("upload", {k: data.get(k) for k in ("ok", "under_10s", "ms", "n_pages", "n_chunks", "policy_id")})
print("wall_s", round(time.time() - t0, 2))
print("ped", (data.get("product") or {}).get("facts", {}).get("ped_wait_months"))

ask = json.dumps(
    {"question": "Diabetes ka waiting period kitna hai?", "policy_id": data["policy_id"]}
).encode()
req2 = urllib.request.Request(
    "http://127.0.0.1:8000/api/ask",
    data=ask,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req2, timeout=180) as r:
    raw = r.read().decode("utf-8", "replace")
final = None
for block in raw.split("\n\n"):
    line = next((l for l in block.split("\n") if l.startswith("data: ")), None)
    if not line:
        continue
    ev = json.loads(line[6:])
    if ev.get("type") == "final":
        final = ev
print("ask", {k: final.get(k) for k in ("status", "ms", "top_score")} if final else None)
print("cites", len((final or {}).get("citations") or []))
print(((final or {}).get("answer") or "")[:220].replace("\n", " "))
