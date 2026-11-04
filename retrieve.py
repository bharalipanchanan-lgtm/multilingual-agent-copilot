"""Local semantic search over the ingested policies."""
import argparse

import chromadb
from sentence_transformers import SentenceTransformer

from config import CHROMA_DIR, COLLECTION, EMBED_MODEL, device

_model = None
_col = None


def _load():
    global _model, _col
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL, device=device())
        _model.max_seq_length = 512
        _col = chromadb.PersistentClient(path=str(CHROMA_DIR)).get_collection(COLLECTION)
    return _model, _col


def search(query: str, policy_id: str | None = None, k: int = 6) -> list[dict]:
    model, col = _load()
    qv = model.encode([query], normalize_embeddings=True).tolist()
    where = {"policy_id": policy_id} if policy_id else None
    res = col.query(query_embeddings=qv, n_results=k, where=where)
    hits = []
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        hits.append({"text": doc, "score": round(1 - dist, 4), **meta})
    return hits


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--policy")
    ap.add_argument("-k", type=int, default=5)
    a = ap.parse_args()
    for h in search(a.query, a.policy, a.k):
        print(f"[{h['policy_id']} p{h['page']} score {h['score']}] {h['section']}")
        print(h["text"][:400].replace("\n", " "), "\n")
