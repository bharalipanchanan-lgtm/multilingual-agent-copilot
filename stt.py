"""Speech to text for voice questions, behind one small interface so providers can be swapped.

Default provider: Sarvam Saaras (cloud, the one exception to "everything local", allowed for the
demo only). The key is read from the SARVAM_API_KEY environment variable (or a gitignored .env
loaded by run_demo.sh) and is never sent to the browser or written to the repo. With no key,
voice is reported as unavailable and the app works by typing exactly as before.

Settings (environment):
  SARVAM_API_KEY     required for voice
  SARVAM_STT_MODEL   default saaras:v3 (the model that supports output modes)
  SARVAM_STT_MODE    default translit: Hindi and Hinglish come back in Roman script, which is how
                     agents type and what the Hinglish answer path and English policy terms suit.
                     Other values: transcribe (Devanagari for Hindi), codemix, translate, verbatim.
  SARVAM_STT_URL     default https://api.sarvam.ai/speech-to-text (a test points it at a mock)
"""
import os
import time

import requests

MAX_BYTES = 5 * 1024 * 1024        # about 30 seconds of compressed audio is far below this
TIMEOUT_S = 30


class STTError(Exception):
    pass


def _cfg():
    return {"key": os.environ.get("SARVAM_API_KEY", "").strip(),
            "model": os.environ.get("SARVAM_STT_MODEL", "saaras:v3"),
            "mode": os.environ.get("SARVAM_STT_MODE", "translit"),
            "url": os.environ.get("SARVAM_STT_URL", "https://api.sarvam.ai/speech-to-text")}


def status() -> dict:
    c = _cfg()
    return {"enabled": bool(c["key"]), "provider": "sarvam", "model": c["model"], "mode": c["mode"],
            "reason": None if c["key"] else "Voice needs SARVAM_API_KEY on the server. Typing works as usual."}


def transcribe(audio: bytes, filename: str, content_type: str) -> dict:
    """Audio from the browser recorder -> {"text", "language_code", "ms", "provider"}."""
    c = _cfg()
    if not c["key"]:
        raise STTError("Voice is not set up: SARVAM_API_KEY is missing on the server.")
    if not audio:
        raise STTError("No audio was recorded.")
    if len(audio) > MAX_BYTES:
        raise STTError("The recording is too long. Keep voice questions under 30 seconds.")
    data = {"model": c["model"], "language_code": "unknown"}
    if c["model"].startswith("saaras:v3"):
        data["mode"] = c["mode"]  # output modes exist on saaras:v3 only
    t0 = time.time()
    try:
        r = requests.post(c["url"], headers={"api-subscription-key": c["key"]}, data=data,
                          files={"file": (filename, audio, content_type or "application/octet-stream")},
                          timeout=TIMEOUT_S)
    except requests.RequestException as e:
        raise STTError(f"Could not reach the speech service ({type(e).__name__}). Please type the question.")
    if r.status_code in (401, 403):
        raise STTError("The speech service rejected the API key. Check SARVAM_API_KEY.")
    if r.status_code == 429:
        raise STTError("The speech service is rate limiting or out of credit. Please type the question.")
    if r.status_code >= 400:
        raise STTError(f"The speech service returned an error ({r.status_code}). Please type the question.")
    body = r.json()
    text = (body.get("transcript") or "").strip()
    if not text:
        raise STTError("I could not hear a question in that recording. Please try again or type it.")
    return {"text": text, "language_code": body.get("language_code"), "ms": int((time.time() - t0) * 1000),
            "provider": f"sarvam {c['model']} ({c['mode']})"}
