import time
from pathlib import Path

from parse import parse_pdf
from retrieve import _load

p = Path("data/policies/2-hdfc-optima-secure.pdf")
_load()  # warm
t1 = time.time()
parsed = parse_pdf(p)
t2 = time.time()
print("pages", parsed["n_pages"], "chunks", len(parsed["chunks"]), "parse_s", round(t2 - t1, 2))
model, col = _load()
embed_in = [
    f"{'x'} | {c.get('part', '')} | {c['section']}\n{c['text']}" for c in parsed["chunks"]
]
t3 = time.time()
model.encode(embed_in, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
t4 = time.time()
print("embed_s", round(t4 - t3, 2))
