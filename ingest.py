"""Parse every PDF listed in the manifest, embed locally, store in Chroma."""
import argparse
import csv
import re

import chromadb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from config import CHROMA_DIR, COLLECTION, EMBED_MODEL, MANIFEST, POLICY_DIR, device
from parse import parse_pdf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="ingest a single policy_id")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(MANIFEST, encoding="utf-8")))
    if args.only:
        rows = [r for r in rows if r["policy_id"] == args.only]

    model = SentenceTransformer(EMBED_MODEL, device=device())
    model.max_seq_length = 512
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    col = client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    summary = []
    for r in rows:
        path = POLICY_DIR / r["file"]
        if not path.exists():
            print(f"SKIP {r['policy_id']}: {path.name} not found")
            continue
        skip = {int(x) for x in re.split(r"[;,]", r.get("skip_pages") or "") if x.strip().isdigit()}
        offset = int(r.get("page_offset") or 0)
        parsed = parse_pdf(path, skip, (r.get("strip_regex") or "").strip() or None)
        chunks = parsed["chunks"]
        if parsed["sparse_pages"] and len(parsed["sparse_pages"]) > parsed["n_pages"] / 2:
            print(f"WARN {r['policy_id']}: mostly scanned, needs OCR. Skipping.")
            continue
        if not chunks:
            print(f"WARN {r['policy_id']}: no text extracted")
            continue

        col.delete(where={"policy_id": r["policy_id"]})
        embed_in = [f"{r['product']} | {c['section']}\n{c['text']}" for c in chunks]
        vecs = model.encode(embed_in, batch_size=16, normalize_embeddings=True,
                            show_progress_bar=False).tolist()
        ids = [f"{r['policy_id']}-p{c['page']}-{i}" for i, c in enumerate(chunks)]
        metas = [{"policy_id": r["policy_id"], "insurer": r["insurer"], "product": r["product"],
                  "page": c["page"], "printed_page": c["page"] - offset, "section": c["section"],
                  "type": c["type"], "chunk_idx": i}
                 for i, c in enumerate(chunks)]
        for s in tqdm(range(0, len(ids), 256), desc=r["policy_id"], leave=False):
            e = s + 256
            col.add(ids=ids[s:e], documents=[c["text"] for c in chunks][s:e],
                    embeddings=vecs[s:e], metadatas=metas[s:e])
        summary.append((r["policy_id"], parsed["n_pages"], len(chunks), len(parsed["sparse_pages"])))

    print(f"\n{'policy':32} {'pages':>6} {'chunks':>7} {'sparse pages':>13}")
    for pid, n, c, sp in summary:
        print(f"{pid:32} {n:>6} {c:>7} {sp:>13}")


if __name__ == "__main__":
    main()
