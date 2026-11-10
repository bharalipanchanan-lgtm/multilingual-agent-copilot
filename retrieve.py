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
    spare: list[dict] = []
    def frequency(w):  # the rarer word in this policy picks the clause: "robotic" before "surgery"
        return len(col.get(where={"policy_id": policy_id}, where_document={"$contains": w.lower()}, include=[])["ids"])
    counted = [(frequency(w), w) for w in set(words)]
    for _, w in sorted([c for c in counted if c[0]], key=lambda c: (c[0], -len(c[1])))[:3]:
        for form in {w.lower(), w.capitalize()}:
            res = col.get(where={"policy_id": policy_id}, where_document={"$contains": form}, limit=6)
            for cid, doc, meta in zip(res["ids"], res["documents"], res["metadatas"]):
                if cid in have or "means" in doc[:120]:
                    continue
                hit = {"id": cid, "text": doc, "score": None, "keyword": w, **meta}
                # prefer numbered clauses over appendix lists; section labels are unreliable in some
                # wordings (Care Supreme), so an unnumbered match is kept as a fallback
                if not (meta.get("section") or "")[:1].isdigit():
                    spare.append(hit)
                    continue
                have.add(cid)
                out.append(hit)
                if len(out) >= max_hits:
                    return out
    for hit in spare:
        if len(out) >= max_hits:
            break
        if hit["id"] not in have:
            have.add(hit["id"])
            out.append(hit)
    return out


def expand_sections(hits: list[dict], max_extra: int = 3) -> list[dict]:
    """Add the other chunks of each hit's clause, e.g. clause 4.3 whose list sits on the next page.

    Only numbered clauses are expanded; appendix and table-only sections are left alone.
    """
    _, col = _load()
    seen = {h["id"] for h in hits}
    out = list(hits)
    added = 0
    # a chunk found by a word of the question (a disease name) is the one most likely to need its context
    for h in sorted(hits, key=lambda h: not h.get("keyword")):
        sec = h.get("section") or ""
        # numbered clauses ("4.3"), and HDFC style parts ("SECTION C. SPECIAL TERMS ...") whose waiting
        # period tables span chunks; a table slice without its heading was read as an exclusion list
        if not (sec[:1].isdigit() or sec.upper().startswith("SECTION ")) or added >= max_extra:
            continue
        res = col.get(where={"$and": [{"policy_id": h["policy_id"]}, {"section": sec}]})
        items = list(zip(res["ids"], res["documents"], res["metadatas"]))
        if not sec[:1].isdigit():
            # a long part: only the chunks right before and after the hit (ids end in a running number)
            n = int(h["id"].rsplit("-", 1)[1])
            items = [it for it in items if abs(int(it[0].rsplit("-", 1)[1]) - n) == 1]
        for cid, doc, meta in items:
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
