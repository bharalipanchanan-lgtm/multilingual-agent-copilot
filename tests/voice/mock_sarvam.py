"""A stand-in for Sarvam's speech-to-text endpoint, for tests only (no network, no key, no cost).

  python tests/voice/mock_sarvam.py PORT LOGFILE

Checks what a real call must carry (api-subscription-key header, a non-empty file, model and
mode fields), writes what it received to LOGFILE as JSON, and answers with the text in the file
MOCK_TRANSCRIPT_FILE (read on every request, so a test can change it between recordings).
"""
import json
import os
import sys

import uvicorn
from fastapi import FastAPI, File, Form, Header, UploadFile
from fastapi.responses import JSONResponse

app = FastAPI()
LOG = sys.argv[2] if len(sys.argv) > 2 else "mock_sarvam.json"


@app.post("/speech-to-text")
def stt(file: UploadFile = File(...), model: str = Form(None), mode: str = Form(None),
        language_code: str = Form(None), api_subscription_key: str = Header(None)):
    data = file.file.read()
    rec = {"key": api_subscription_key, "model": model, "mode": mode, "language_code": language_code,
           "filename": file.filename, "content_type": file.content_type, "bytes": len(data),
           "magic": data[:4].hex()}
    json.dump(rec, open(LOG, "w"))
    if api_subscription_key != "test-key":
        return JSONResponse({"error": "bad key"}, status_code=403)
    if not data:
        return JSONResponse({"error": "empty"}, status_code=400)
    # same rule as the real service: a codec parameter makes the type invalid
    allowed = {"audio/webm", "video/webm", "audio/mp4", "audio/x-m4a", "audio/wav", "audio/x-wav", "audio/mpeg",
               "audio/ogg", "audio/opus", "application/octet-stream"}
    if file.content_type not in allowed:
        return JSONResponse({"error": {"message": f"Invalid file type: {file.content_type}"}}, status_code=400)
    path = os.environ.get("MOCK_TRANSCRIPT_FILE")
    text = open(path, encoding="utf-8").read().strip() if path and os.path.exists(path) else "room rent kitna hai"
    return {"request_id": "mock", "transcript": text,
            "language_code": "hi-IN"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
