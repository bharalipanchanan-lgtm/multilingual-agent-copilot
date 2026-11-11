import json
import time
import urllib.request
from pathlib import Path

pdf = Path("data/policies/6-icici-elevate.pdf").read_bytes()
boundary = "----bound" + str(int(time.time()))
fields = [
    ("insurer", "ICICI Lombard (ICC)"),
    ("product", "Elevate Upload Test"),
]
parts = []
for name, val in fields:
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{val}\r\n".encode()
    )
parts.append(
    (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="6-icici-elevate.pdf"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode()
    + pdf
    + b"\r\n"
)
parts.append(f"--{boundary}--\r\n".encode())
body = b"".join(parts)
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/upload",
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    method="POST",
)
t0 = time.time()
with urllib.request.urlopen(req, timeout=180) as r:
    data = json.load(r)
print("upload", {k: data.get(k) for k in ("ok", "under_10s", "ms", "n_pages", "n_chunks", "policy_id")})
print("wall_s", round(time.time() - t0, 2))

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
print("ask", {k: final.get(k) for k in ("status", "ms", "backend", "top_score")} if final else None)
print("cites", len((final or {}).get("citations") or []))
ans = (final or {}).get("answer") or ""
print("answer", ans[:240].replace("\n", " "))
