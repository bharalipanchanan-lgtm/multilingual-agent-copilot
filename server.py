"""FastAPI service for the Agent Copilot prototype.

Run:  python server.py          then open http://localhost:8000
Env:  COPILOT_BACKEND=mlx|ollama|claude|extractive   (default from config.GEN_BACKEND)

Endpoints
  GET  /api/policies          loaded policies (+ agent uploads)
  GET  /api/status            backend and warm-up state
  POST /api/ask               {"question", "policy_id"} -> server-sent events (meta, token, final)
  GET  /api/compare?q=...     comparison from the fact table
  POST /api/upload            multipart PDF -> hybrid RAG index (target <10s when warm)
  GET  /api/uploads           list agent-uploaded wordings
  GET  /pdf/{policy_id}       the policy PDF (cards link to #page=N)
"""
import csv
import json
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import MANIFEST, POLICY_DIR, ROOT
from generate import get_generator

app = FastAPI(title="Claviq Agent Copilot (prototype)")

# One worker thread owns the embedding model and the LLM (MLX is not thread safe across threads).
WORKER = ThreadPoolExecutor(max_workers=1)
STATE = {"ready": False, "backend": None, "error": None}
GEN = {"gen": None}


def _manifest_policies() -> list[dict]:
    rows = list(csv.DictReader(open(MANIFEST, encoding="utf-8")))
    return [{"policy_id": r["policy_id"], "insurer": r["insurer"], "product": r["product"], "source": "catalogue"}
            for r in rows if (POLICY_DIR / r["file"]).exists()]


def _policies() -> list[dict]:
    from upload_index import list_uploads
    out = _manifest_policies()
    for u in list_uploads():
        out.append({
            "policy_id": u["policy_id"],
            "insurer": u.get("insurer") or "Uploaded",
            "product": u.get("product") or u.get("filename"),
            "source": "upload",
            "n_pages": u.get("n_pages"),
            "ms": u.get("ms"),
        })
    return out


def _warm():
    try:
        gen = get_generator()
        GEN["gen"] = gen
        STATE["backend"] = gen.name
        from retrieve import search
        pols = _manifest_policies()
        if pols:
            search("room rent limit", pols[0]["policy_id"], 1)  # loads bge-m3 and Chroma
        if hasattr(gen, "_load"):
            gen._load()
            for _ in gen.stream("Reply with OK.", "OK?"):
                break
        STATE["ready"] = True
    except Exception as e:  # surface in /api/status rather than crash
        STATE["error"] = repr(e)
        print("[warm] failed:", e)


@app.on_event("startup")
def startup():
    WORKER.submit(_warm)


class Ask(BaseModel):
    question: str
    policy_id: str


@app.get("/api/policies")
def policies():
    return _policies()


@app.get("/api/status")
def status():
    return STATE


@app.get("/api/uploads")
def uploads():
    from upload_index import list_uploads, product_card
    return [product_card(u) for u in list_uploads()]


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    product: str | None = Form(None),
    insurer: str | None = Form(None),
):
    """Agent drops a policy PDF. Hybrid-index it into Chroma and return a product card.

    Runs on the same worker that owns the embedding model so it shares the warm bge-m3.
    Target: under 10 seconds once the server is ready.
    """
    if not STATE["ready"]:
        raise HTTPException(503, "Models still warming up — try again in a few seconds.")
    name = file.filename or "wording.pdf"
    if not name.lower().endswith(".pdf"):
        raise HTTPException(400, "Upload a PDF policy wording.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file.")

    result: dict = {}
    err: list = []

    def job():
        try:
            from upload_index import ingest_upload, product_card
            meta = ingest_upload(
                data,
                name,
                product=product,
                insurer=(insurer or "Uploaded").strip() or "Uploaded",
            )
            result["meta"] = meta
            result["product"] = product_card(meta)
        except Exception as e:
            err.append(e)

    fut = WORKER.submit(job)
    fut.result()  # block this request until the index write finishes
    if err:
        raise HTTPException(400, str(err[0]))
    meta = result["meta"]
    return {
        "ok": True,
        "under_10s": meta["ms"] < 10000,
        "ms": meta["ms"],
        "policy_id": meta["policy_id"],
        "n_pages": meta["n_pages"],
        "n_chunks": meta["n_chunks"],
        "product": result["product"],
        "message": (
            f"Scanned {meta['n_pages']} pages into hybrid RAG in {meta['ms']} ms. "
            "Ask in English, Hindi or Hinglish — answers cite page and clause."
        ),
    }


def _audit(req: Ask, ev: dict) -> None:
    try:
        log_path = ROOT / "data" / "audit.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "policy_id": req.policy_id,
                "question": req.question.strip(),
                "status": ev.get("status"),
                "backend": ev.get("backend"),
                "ms": ev.get("ms"),
                "cached": bool(ev.get("cached")),
                "citations": [
                    {"page": c.get("page"), "printed_page": c.get("printed_page"), "section": c.get("section")}
                    for c in (ev.get("citations") or [])
                ],
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass


@app.post("/api/ask")
def ask(req: Ask):
    if not req.question.strip():
        raise HTTPException(400, "empty question")
    sse = lambda ev: f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

    if GEN["gen"]:
        from answer import cached_final
        hit = cached_final(req.question.strip(), req.policy_id, GEN["gen"].name)
        if hit:
            hit["ms"] = 0
            _audit(req, hit)
            meta = {"type": "meta", "lang": hit.get("lang"), "route": "cache", "backend": GEN["gen"].name}
            return StreamingResponse(iter([sse(meta), sse(hit)]), media_type="text/event-stream", headers=headers)

    q: queue.Queue = queue.Queue()
    done = object()

    def job():
        from answer import ask_stream
        try:
            for ev in ask_stream(req.question.strip(), req.policy_id, GEN["gen"] or get_generator()):
                if ev.get("type") == "final":
                    _audit(req, ev)
                q.put(ev)
        except Exception as e:
            q.put({"type": "final", "status": "error", "answer": f"Something went wrong: {e}", "citations": []})
        finally:
            q.put(done)

    WORKER.submit(job)

    def events():
        while True:
            ev = q.get()
            if ev is done:
                break
            yield sse(ev)

    return StreamingResponse(events(), media_type="text/event-stream", headers=headers)


@app.get("/api/compare")
def compare(q: str):
    from answer import detect_lang
    from compare import compare_answer
    return compare_answer(q, detect_lang(q))


@app.get("/pdf/{policy_id}")
def pdf(policy_id: str):
    from upload_index import pdf_path_for
    up = pdf_path_for(policy_id)
    if up is not None:
        return FileResponse(up, media_type="application/pdf", filename=up.name)
    for r in csv.DictReader(open(MANIFEST, encoding="utf-8")):
        if r["policy_id"] == policy_id:
            return FileResponse(POLICY_DIR / r["file"], media_type="application/pdf")
    raise HTTPException(404)


app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
