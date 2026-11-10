"""Index an agent-uploaded policy PDF into the same hybrid RAG store.

Uses the already-warmed bge-m3 + Chroma collection from retrieve._load(),
so a typical 10–40 page wording lands in a few seconds once the server is hot.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from config import (
    COLLECTION,
    MIN_CHARS_PER_PAGE,
    UPLOAD_DIR,
    UPLOAD_EMBED_CHARS,
    UPLOAD_MAX_CHUNKS,
    UPLOAD_MAX_MB,
    UPLOAD_MAX_PAGES,
    UPLOAD_REGISTRY,
)
from parse import build_chunks

# Prefer exclusion waiting periods, never the PED *definition* lookback
# ("diagnosed … within 36 months prior to the effective date").
PED_PATTERNS = [
    re.compile(
        r"(?:pre[- ]?existing(?:\s+disease)?|PED).{0,160}?"
        r"(?:excluded until|shall be excluded until|waiting period).{0,80}?"
        r"(?:expiry of\s+)?(\d+)\s*(months?|years?)",
        re.I | re.S,
    ),
    re.compile(
        r"(?:excluded until|shall be excluded until).{0,80}?"
        r"(?:expiry of\s+)?(\d+)\s*(months?|years?).{0,60}?continuous coverage",
        re.I | re.S,
    ),
]
ROOM_PATTERNS = [
    re.compile(
        r"room\s+rent.{0,80}?(?:rs\.?|₹|inr)?\s*([\d,]+)\s*(?:/?\s*day|per\s+day)?",
        re.I | re.S,
    ),
    re.compile(
        r"(single\s+private(?:\s+a/?c)?\s+room|any\s+room(?:\s+category)?|"
        r"no\s+(?:separate\s+)?(?:sub-?)?limit.{0,40}room)",
        re.I | re.S,
    ),
]
ENTRY_PATTERNS = [
    re.compile(
        r"(?:entry\s+age|maximum\s+age|max(?:imum)?\s+entry).{0,40}?(\d{2})\s*years?",
        re.I | re.S,
    ),
]


def parse_pdf_fast(path) -> dict:
    """Upload-oriented parse: plain text only (skip table detection — that is the slow path)."""
    import fitz

    doc = fitz.open(path)
    pages_lines, sparse = [], []
    for i, page in enumerate(doc):
        raw = page.get_text("text") or ""
        if len(raw.strip()) < MIN_CHARS_PER_PAGE:
            sparse.append(i + 1)
        pages_lines.append([ln.strip() for ln in raw.splitlines()])
    chunks = build_chunks(pages_lines, None, frozenset())
    return {"n_pages": len(doc), "sparse_pages": sparse, "chunks": chunks}


def _pack_chunks(chunks: list[dict]) -> list[dict]:
    """Merge adjacent same-section chunks so CPU embedding stays under the 10s target."""
    if len(chunks) <= UPLOAD_MAX_CHUNKS:
        return chunks
    packed: list[dict] = []
    buf = None
    for c in chunks:
        if buf is None:
            buf = dict(c)
            continue
        same = buf.get("section") == c.get("section") and buf.get("page") == c.get("page")
        if same and len(buf["text"]) + 1 + len(c["text"]) <= 2200:
            buf["text"] = buf["text"] + "\n" + c["text"]
        else:
            packed.append(buf)
            buf = dict(c)
    if buf:
        packed.append(buf)
    if len(packed) <= UPLOAD_MAX_CHUNKS:
        return packed
    # keep head + tail so early definitions and late schedules both survive
    head = UPLOAD_MAX_CHUNKS * 2 // 3
    tail = UPLOAD_MAX_CHUNKS - head
    return packed[:head] + packed[-tail:]


def _load_registry() -> dict:
    if not UPLOAD_REGISTRY.exists():
        return {"uploads": {}}
    try:
        return json.loads(UPLOAD_REGISTRY.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"uploads": {}}


def _save_registry(reg: dict) -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")


def list_uploads() -> list[dict]:
    reg = _load_registry()
    rows = list(reg.get("uploads", {}).values())
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return rows


def get_upload(policy_id: str) -> dict | None:
    return _load_registry().get("uploads", {}).get(policy_id)


def pdf_path_for(policy_id: str) -> Path | None:
    meta = get_upload(policy_id)
    if not meta:
        return None
    p = Path(meta["path"])
    return p if p.exists() else None


def _months(value: str, unit: str) -> int:
    n = int(value)
    return n * 12 if unit.lower().startswith("year") else n


def _snippet(text: str, start: int, end: int, pad: int = 40) -> str:
    a = max(0, start - pad)
    b = min(len(text), end + pad)
    return re.sub(r"\s+", " ", text[a:b]).strip()


def extract_quick_facts(chunks: list[dict], product: str) -> dict:
    """Best-effort facts so feature 3/4 can answer waiting / room / age without the LLM."""
    facts: dict = {
        "premium_inr": {
            "stated": False,
            "note": "Premium is not taken from an uploaded wording — use the rate card.",
        },
        "copay": {"stated": False, "note": "No co-pay clause extracted automatically."},
    }
    blob_parts = []
    for c in chunks[:120]:
        blob_parts.append((c, f"{c.get('section', '')}\n{c.get('text', '')}"))

    for c, text in blob_parts:
        if "ped_wait_months" not in facts:
            sec = (c.get("section") or "").lower()
            # skip pure definitions / unrelated overseas rider text
            if re.search(r"means any condition|prior to the effective date|overseas travel", text + " " + sec, re.I) and not re.search(
                r"excluded until|shall be excluded until", text, re.I
            ):
                continue
            for pat in PED_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                months = _months(m.group(1), m.group(2) if m.lastindex >= 2 else "months")
                if not (3 <= months <= 60):
                    continue
                # require a real waiting/exclusion cue next to the number
                window = text[max(0, m.start() - 40) : m.end() + 40]
                if not re.search(r"exclud|waiting|continuous coverage", window, re.I):
                    continue
                facts["ped_wait_months"] = {
                    "stated": True,
                    "value": months,
                    "section": c.get("section") or "Waiting period",
                    "pdf_page": c["page"],
                    "printed_page": c["page"],
                    "quote": _snippet(text, m.start(), m.end(), 80),
                }
                break
        if "room_rent" not in facts:
            for pat in ROOM_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                if m.lastindex and m.group(1) and m.group(1)[0].isdigit():
                    amt = int(m.group(1).replace(",", ""))
                    facts["room_rent"] = {
                        "stated": True,
                        "value": f"Rs {amt:,}/day",
                        "max_per_day": amt,
                        "section": c.get("section") or "Room rent",
                        "pdf_page": c["page"],
                        "printed_page": c["page"],
                        "quote": _snippet(text, m.start(), m.end(), 60),
                    }
                else:
                    facts["room_rent"] = {
                        "stated": True,
                        "value": m.group(0).strip()[:120],
                        "section": c.get("section") or "Room rent",
                        "pdf_page": c["page"],
                        "printed_page": c["page"],
                        "quote": _snippet(text, m.start(), m.end(), 60),
                    }
                break
        if "entry_age_max" not in facts:
            for pat in ENTRY_PATTERNS:
                m = pat.search(text)
                if m:
                    age = int(m.group(1))
                    if 18 <= age <= 99:
                        facts["entry_age_max"] = {
                            "stated": True,
                            "value": age,
                            "section": c.get("section") or "Entry age",
                            "pdf_page": c["page"],
                            "printed_page": c["page"],
                            "quote": _snippet(text, m.start(), m.end(), 40),
                        }
                        break

    for key, note in (
        ("ped_wait_months", "No PED waiting period number found automatically — ask and the hybrid RAG will search the wording."),
        ("room_rent", "No room-rent figure found automatically — ask and the hybrid RAG will search the wording."),
        ("entry_age_max", "No entry-age figure found automatically — ask and the hybrid RAG will search the wording."),
        ("ayush", "Ask to search the uploaded wording."),
        ("cataract", "Ask to search the uploaded wording."),
        ("robotic_surgery", "Ask to search the uploaded wording."),
        ("specified_disease_wait_months", "Ask to search the uploaded wording."),
    ):
        facts.setdefault(key, {"stated": False, "note": note})

    return facts


def product_card(meta: dict, facts: dict | None = None) -> dict:
    """Shape an upload like a catalogue product so the 5-feature UI can pin and ask."""
    facts = facts if facts is not None else meta.get("facts") or {}
    return {
        "id": meta["policy_id"],
        "policy_id": meta["policy_id"],
        "insurer": meta.get("insurer") or "Uploaded",
        "name": meta.get("product") or meta.get("filename") or "Uploaded wording",
        "variant": "",
        "uin": meta.get("uin") or "UPLOAD",
        "status": "active",
        "source": "upload",
        "differentiator": (
            f"Your upload · {meta.get('n_pages', '?')} pages · "
            f"indexed in {meta.get('ms', '?')} ms"
        ),
        "facts": facts,
        "uploaded": True,
        "filename": meta.get("filename"),
    }


def ingest_upload(
    pdf_bytes: bytes,
    filename: str,
    *,
    product: str | None = None,
    insurer: str = "Uploaded",
) -> dict:
    t0 = time.time()
    if len(pdf_bytes) > UPLOAD_MAX_MB * 1024 * 1024:
        raise ValueError(f"PDF larger than {UPLOAD_MAX_MB} MB")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    policy_id = f"upload_{uuid.uuid4().hex[:12]}"
    stem = re.sub(r"[^\w.\-]+", "_", Path(filename).stem)[:60] or "wording"
    dest = UPLOAD_DIR / f"{policy_id}__{stem}.pdf"
    dest.write_bytes(pdf_bytes)

    parsed = parse_pdf_fast(dest)
    if parsed["n_pages"] > UPLOAD_MAX_PAGES:
        dest.unlink(missing_ok=True)
        raise ValueError(
            f"PDF has {parsed['n_pages']} pages; max for a fast scan is {UPLOAD_MAX_PAGES}. "
            "Split the wording or raise COPILOT_UPLOAD_MAX_PAGES."
        )
    if parsed["sparse_pages"] and len(parsed["sparse_pages"]) > parsed["n_pages"] / 2:
        dest.unlink(missing_ok=True)
        raise ValueError("Most pages look scanned with no text layer. Need a text PDF or OCR first.")
    chunks = _pack_chunks(parsed["chunks"])
    if not chunks:
        dest.unlink(missing_ok=True)
        raise ValueError("No text extracted from this PDF.")

    product_name = (product or stem.replace("_", " ")).strip()[:80] or "Uploaded wording"

    # Reuse the warm embedding model + Chroma collection (hybrid RAG store).
    from retrieve import _load

    model, col = _load()
    try:
        col.delete(where={"policy_id": policy_id})
    except Exception:
        pass

    embed_in = [
        f"{product_name} | {c.get('part', '')} | {c['section']}\n{c['text'][:UPLOAD_EMBED_CHARS]}"
        for c in chunks
    ]
    vecs = model.encode(embed_in, batch_size=64, normalize_embeddings=True, show_progress_bar=False).tolist()
    ids = [f"{policy_id}-p{c['page']}-{i}" for i, c in enumerate(chunks)]
    metas = [
        {
            "policy_id": policy_id,
            "insurer": insurer,
            "product": product_name,
            "page": c["page"],
            "printed_page": c["page"],
            "section": c["section"],
            "type": c["type"],
            "chunk_idx": i,
            "part": c.get("part", ""),
        }
        for i, c in enumerate(chunks)
    ]
    docs = [c["text"] for c in chunks]
    for s in range(0, len(ids), 256):
        e = s + 256
        col.add(ids=ids[s:e], documents=docs[s:e], embeddings=vecs[s:e], metadatas=metas[s:e])

    facts = extract_quick_facts(chunks, product_name)
    ms = int((time.time() - t0) * 1000)
    meta = {
        "policy_id": policy_id,
        "filename": Path(filename).name,
        "product": product_name,
        "insurer": insurer,
        "uin": "UPLOAD",
        "n_pages": parsed["n_pages"],
        "n_chunks": len(chunks),
        "sparse_pages": parsed["sparse_pages"],
        "ms": ms,
        "path": str(dest),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "facts": facts,
        "collection": COLLECTION,
    }
    reg = _load_registry()
    reg.setdefault("uploads", {})[policy_id] = meta
    _save_registry(reg)
    return meta
