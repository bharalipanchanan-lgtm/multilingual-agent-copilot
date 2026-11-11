"""Hybrid search over the ingested policies: dense (bge-m3) + BM25, fused by reciprocal rank."""
import argparse
import math
import re
from collections import Counter

import chromadb
import numpy as np
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


# ── lexical side: BM25 per policy, built from the stored chunks ──────────

BM25_K1, BM25_B, RRF_K = 1.4, 0.72, 60
LEX_STOP = {"the", "of", "and", "or", "to", "in", "a", "an", "is", "are", "be", "for", "on", "by", "as", "at", "any",
            "this", "that", "with", "shall", "will", "which", "from", "such", "under", "per", "its", "it", "we", "us",
            "our", "you", "your", "policy", "insured", "person", "kya", "hai", "ka", "ki", "ke", "mein", "kitna"}
_bm25: dict[str, dict] = {}


def _stem(w: str) -> str:
    if len(w) > 4:
        if w.endswith("ies"):
            return w[:-3] + "y"
        if w.endswith("es") and not w.endswith("ses"):
            return w[:-2]
        if w.endswith("s") and not w.endswith("ss"):
            return w[:-1]
    return w


def _tokens(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in LEX_STOP and len(w) > 1]


def _index(policy_id: str) -> dict:
    _, col = _load()
    res = col.get(where={"policy_id": policy_id}, include=["documents", "metadatas"])
    n = len(res["ids"])
    cached = _bm25.get(policy_id)
    if cached and cached["n"] == n:
        return cached
    docs = [_tokens(f"{(m or {}).get('section') or ''} {d}") for d, m in zip(res["documents"], res["metadatas"])]
    tfs = [Counter(t) for t in docs]
    df = Counter(w for t in tfs for w in t)
    avg = (sum(len(t) for t in docs) / n) if n else 1.0
    idx = {"n": n, "ids": res["ids"], "docs": res["documents"], "metas": res["metadatas"], "tfs": tfs,
           "lens": [len(t) for t in docs], "avg": avg,
           "idf": {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}}
    _bm25[policy_id] = idx
    return idx


def bm25_search(query: str, policy_id: str, k: int = 24) -> list[tuple[int, float]]:
    idx = _index(policy_id)
    qt = [w for w in dict.fromkeys(_tokens(query)) if w in idx["idf"]]
    if not qt:
        return []
    scores = []
    for i, tf in enumerate(idx["tfs"]):
        s = 0.0
        norm = BM25_K1 * (1 - BM25_B + BM25_B * idx["lens"][i] / idx["avg"])
        for w in qt:
            f = tf.get(w)
            if f:
                s += idx["idf"][w] * f * (BM25_K1 + 1) / (f + norm)
        if s > 0:
            scores.append((i, s))
    scores.sort(key=lambda x: -x[1])
    return scores[:k]


def hybrid(query: str, policy_id: str | None = None, k: int = 6, pool: int = 24) -> list[dict]:
    """Dense and BM25 rankings fused by reciprocal rank. Every hit keeps its cosine `score`
    (the not-stated gate depends on it) and carries `rrf`, `dense_rank`, `lex_rank`."""
    model, col = _load()
    qv = model.encode([query], normalize_embeddings=True)[0]
    where = {"policy_id": policy_id} if policy_id else None
    res = col.query(query_embeddings=[qv.tolist()], n_results=pool, where=where)
    hits: dict[str, dict] = {}
    for r, (cid, doc, meta, dist) in enumerate(zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0])):
        hits[cid] = {"id": cid, "text": doc, "score": round(1 - dist, 4), "dense_rank": r + 1, "rrf": 1 / (RRF_K + r + 1), **meta}
    if policy_id:
        idx = _index(policy_id)
        lex = bm25_search(query, policy_id, pool)
        missing = [idx["ids"][i] for i, _ in lex if idx["ids"][i] not in hits]
        emb = {}
        if missing:
            got = col.get(ids=missing, include=["embeddings"])
            emb = {cid: float(np.dot(qv, np.asarray(e))) for cid, e in zip(got["ids"], got["embeddings"])}
        for r, (i, s) in enumerate(lex):
            cid = idx["ids"][i]
            h = hits.get(cid)
            if h is None:
                h = hits[cid] = {"id": cid, "text": idx["docs"][i], "score": round(emb.get(cid, 0.0), 4), "rrf": 0.0, **idx["metas"][i]}
            h["lex_rank"] = r + 1
            h["bm25"] = round(s, 3)
            h["rrf"] += 1 / (RRF_K + r + 1)
    out = sorted(hits.values(), key=lambda h: -h["rrf"])
    return out[:k]


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


# permanent exclusions only: waiting periods (Code-Excl01 to 03, "excluded until the expiry of 24 months")
# are not exclusions in this sense, so cataract or diabetes questions are not answered as "excluded"
EXCL_RE = re.compile(r"\bexclu(?!ded\s+until|sion\s+will\s+apply\s+until)|code\s*[-–]?\s*excl\s*(?:0?[4-9]|[1-9]\d)|"
                     r"not (?:be )?(?:covered|payable)|shall not be liable", re.I)


def is_exclusion_for(doc: str, meta: dict, word: str) -> bool:
    """The word sits near exclusion language, or inside a clause filed under an exclusions part."""
    if word.lower() not in doc.lower():
        return False
    where = f"{meta.get('part') or ''} {meta.get('section') or ''}"
    if re.search(r"definition|^\s*def\b", where, re.I):  # a definition never excludes anything by itself
        return False
    # only the policy's own exclusions: a "not covered" line inside one benefit's sub-list
    # ("Global cover ... vi. Oncological (Cancer) diseases") does not exclude cancer from the policy
    in_excl_part = re.search(r"exclusion", where, re.I)
    has_code = re.search(r"code\s*[-–]?\s*excl\s*(?:0?[4-9]|[1-9]\d)", doc, re.I)
    if not (in_excl_part or has_code):
        return False
    # the exclusion language must be in the same sentence as the word, or the clause heading just before it
    # ("Maternity: Code – Excl18: i. Medical treatment expenses ...") — a chapter title alone is not enough
    sents = re.split(r"(?<=[.;])\s+(?=[A-Z(\divx])", doc)
    for i, s in enumerate(sents):
        if word.lower() in s.lower() and EXCL_RE.search(" ".join(sents[max(0, i - 1): i + 2])[:600]):
            return True
    # inside a numbered exclusion item: "Sterility and Infertility: Code – Excl17: ... ii. ... such as IVF"
    code = re.compile(r"code\s*[-–]?\s*excl\s*(\d+)", re.I)
    for m in re.finditer(re.escape(word), doc, re.I):
        before = list(code.finditer(doc[max(0, m.start() - 600): m.start()]))
        if before and int(before[-1].group(1)) >= 4:
            return True
    return False


def exclusion_hits(words: list[str], policy_id: str, have: set[str], max_hits: int = 2) -> list[dict]:
    """Exclusion clauses that name one of the question's topic words.

    "Is maternity covered?" must see Code-Excl18 (maternity excluded) even when semantic search
    ranks a brochure add-on page ("Parenthood: covers maternity ... post 2 years") higher."""
    if not policy_id:
        return []
    _, col = _load()
    out: list[dict] = []
    for w in sorted(set(words), key=len, reverse=True)[:3]:
        for form in {w, w.lower(), w.capitalize(), w.upper()}:
            res = col.get(where={"policy_id": policy_id}, where_document={"$contains": form}, limit=12)
            for cid, doc, meta in zip(res["ids"], res["documents"], res["metadatas"]):
                if cid in have or not is_exclusion_for(doc, meta, form):
                    continue
                have.add(cid)
                out.append({"id": cid, "text": doc, "score": None, "keyword": w, "exclusion": True, **meta})
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
    for h in hybrid(a.query, a.policy, a.k):
        print(f"[{h['policy_id']} p{h['page']} cos {h['score']} dense#{h.get('dense_rank', '-')} bm25#{h.get('lex_rank', '-')}] {h['section']}")
        print(h["text"][:400].replace("\n", " "), "\n")
