"""Local semantic search over the ingested policies."""
import argparse
import re

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
        _col = chromadb.PersistentClient(path=str(CHROMA_DIR)).get_collection(COLLECTION, embedding_function=None)
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


STOP = {"what", "which", "there", "their", "about", "policy", "covered", "cover", "under", "after", "would",
        "should", "could", "treatment", "treatments", "insurance", "insured", "period", "waiting", "charges",
        "liye", "kitna", "kitne", "milta", "milega", "hota", "hoti", "lagta", "kaunsi", "kaise", "this", "with",
        "does", "from", "have", "limit", "limits"}


def keyword_hits(query: str, policy_id: str, have: set[str], max_hits: int = 2) -> list[dict]:
    """Chunks that literally contain a distinctive word of the question (e.g. a disease name).

    Semantic search can rank a long list clause low even when it names the exact disease
    the agent asked about, so these are added alongside the semantic hits.
    """
    if not policy_id:
        return []
    _, col = _load()
    words = [w for w in re.findall(r"[A-Za-z]{5,}", query) if w.lower() not in STOP]
    out: list[dict] = []
    for w in sorted(set(words), key=len, reverse=True)[:3]:
        for form in {w.lower(), w.capitalize()}:
            res = col.get(where={"policy_id": policy_id}, where_document={"$contains": form}, limit=4)
            for cid, doc, meta in zip(res["ids"], res["documents"], res["metadatas"]):
                # prefer numbered clauses over appendix lists and definitions,
                # but never drop a table: benefit tables carry the modern
                # treatment lists, room rent bands and sub-limits, and they
                # are stored with section "Table", which is not a digit.
                numbered = (meta.get("section") or "")[:1].isdigit()
                is_table = meta.get("type") == "table"
                if cid in have or not (numbered or is_table) or "means" in doc[:120]:
                    continue
                have.add(cid)
                out.append({"id": cid, "text": doc, "score": None, "keyword": w, **meta})
                if len(out) >= max_hits:
                    return out
    return out


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
