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
    for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
        hits.append({"id": cid, "text": doc, "score": round(1 - dist, 4), **meta})
    return hits


def expand_sections(hits: list[dict], max_extra: int = 3) -> list[dict]:
    """Add the other chunks of each hit's clause, e.g. clause 4.3 whose list sits on the next page.

    Only numbered clauses are expanded; appendix and table-only sections are left alone.
    """
    _, col = _load()
    seen = {h["id"] for h in hits}
    out = list(hits)
    added = 0
    for h in hits:
        sec = h.get("section") or ""
        if not sec[:1].isdigit() or added >= max_extra:
            continue
        res = col.get(where={"$and": [{"policy_id": h["policy_id"]}, {"section": sec}]})
        for cid, doc, meta in zip(res["ids"], res["documents"], res["metadatas"]):
            if cid in seen or added >= max_extra:
                continue
            seen.add(cid)
            out.append({"id": cid, "text": doc, "score": h["score"], "expanded_from": h["id"], **meta})
            added += 1
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--policy")
    ap.add_argument("-k", type=int, default=5)
    a = ap.parse_args()
    for h in search(a.query, a.policy, a.k):
        print(f"[{h['policy_id']} p{h['page']} score {h['score']}] {h['section']}")
        print(h["text"][:400].replace("\n", " "), "\n")
