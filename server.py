"""FastAPI service for the Agent Copilot prototype.

Run:  python server.py          then open http://localhost:8000
Env:  COPILOT_BACKEND=mlx|ollama|claude|extractive   (default from config.GEN_BACKEND)

Endpoints
  GET  /api/policies          loaded policies
  GET  /api/status            backend and warm-up state
  POST /api/ask               {"question", "policy_id" or null} -> server-sent events (policy, meta, token, final)
                              The policy is chosen in the conversation (chat.py), not from a list.
  GET  /api/compare?q=...     comparison from the fact table
  GET  /api/voice             whether voice input is available (SARVAM_API_KEY set)
  POST /api/transcribe        multipart "audio" -> {"text"}; the key stays on the server (stt.py)
  GET  /pdf/{policy_id}       the policy PDF (cards link to #page=N)
"""
import csv
import json
import queue
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, File, HTTPException, UploadFile
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


def _policies() -> list[dict]:
    rows = list(csv.DictReader(open(MANIFEST, encoding="utf-8")))
    return [{"policy_id": r["policy_id"], "insurer": r["insurer"], "product": r["product"]}
            for r in rows if (POLICY_DIR / r["file"]).exists()]


def _warm():
    try:
        gen = get_generator()
        GEN["gen"] = gen
        STATE["backend"] = gen.name
        from retrieve import search
        pols = _policies()
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
    policy_id: str | None = None
    held: bool = False              # re-sent question that was held while the agent chose a policy
    prev_lang: str | None = None    # language of the conversation so far


@app.get("/api/policies")
def policies():
    from policy_select import options
    return options()


@app.get("/api/status")
def status():
    return STATE


@app.post("/api/ask")
def ask(req: Ask):
    if not req.question.strip():
        raise HTTPException(400, "empty question")
    q: queue.Queue = queue.Queue()
    done = object()

    def job():
        from chat import converse
        try:
            for ev in converse(req.question.strip(), req.policy_id, GEN["gen"] or get_generator(),
                               held=req.held, prev_lang=req.prev_lang):
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
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/voice")
def voice():
    import stt
    return stt.status()


@app.post("/api/transcribe")
def transcribe(audio: UploadFile = File(...)):
    import stt
    try:
        return stt.transcribe(audio.file.read(), audio.filename or "question.webm", audio.content_type or "")
    except stt.STTError as e:
        raise HTTPException(400, str(e))


@app.get("/api/compare")
def compare(q: str):
    from answer import detect_lang
    from compare import compare_answer
    return compare_answer(q, detect_lang(q))


@app.get("/pdf/{policy_id}")
def pdf(policy_id: str):
    for r in csv.DictReader(open(MANIFEST, encoding="utf-8")):
        if r["policy_id"] == policy_id:
            return FileResponse(POLICY_DIR / r["file"], media_type="application/pdf")
    raise HTTPException(404)


@app.middleware("http")
async def no_cache_page(request, call_next):
    # The chat page changes as the prototype changes; a cached copy showed the old dropdown page.
    resp = await call_next(request)
    if not request.url.path.startswith(("/api/", "/pdf/")):
        resp.headers["Cache-Control"] = "no-store"
    return resp


app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")

if __name__ == "__main__":
    import uvicorn
    import os
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("COPILOT_PORT", "8000")))
