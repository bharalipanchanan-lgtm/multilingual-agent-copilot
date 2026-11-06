"""The hosted model backend (generate.APIGenerator) against a stand-in chat completions server:
streaming, hidden reasoning not shown, one retry, and the clause fallback when the model fails."""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generate import APIGenerator, Generator  # noqa: E402

SEEN = []
MODE = {"fail_first": 0}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append({"body": body, "auth": self.headers.get("Authorization"), "sarvam": self.headers.get("api-subscription-key")})
        if MODE["fail_first"] > 0:
            MODE["fail_first"] -= 1
            self.send_response(503)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        chunks = [{"choices": [{"delta": {"role": "assistant"}}]},
                  {"choices": [{"delta": {"reasoning_content": "thinking out loud"}}]},
                  {"choices": [{"delta": {"content": "Room rent is 1% "}}]},
                  {"choices": [{"delta": {"content": "of the sum insured [1]."}}]},
                  {"choices": [], "usage": {"total_tokens": 9}}]
        for c in chunks:
            self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/v1/chat/completions"
    srv.shutdown()


def test_streams_content_only(server, monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "test-key")
    monkeypatch.setenv("COPILOT_LLM_URL", server)
    g = APIGenerator("sarvam")
    assert g.available() == (True, "")
    out = "".join(g.stream("system", "user"))
    assert out == "Room rent is 1% of the sum insured [1]."
    sent = SEEN[-1]
    assert sent["auth"] == "Bearer test-key" and sent["sarvam"] == "test-key"
    assert sent["body"]["temperature"] == 0 and sent["body"]["stream"] is True
    assert sent["body"]["reasoning_effort"] is None  # Sarvam: reasoning off
    assert sent["body"]["messages"][0] == {"role": "system", "content": "system"}


def test_retries_once_on_503(server, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("COPILOT_LLM_URL", server)
    MODE["fail_first"] = 1
    n = len(SEEN)
    assert "1%" in "".join(APIGenerator("groq").stream("s", "u"))
    assert len(SEEN) == n + 2
    assert SEEN[-1]["sarvam"] is None  # only Sarvam gets its own header


def test_no_key_means_unavailable(monkeypatch):
    for k in ("SARVAM_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    ok, why = APIGenerator("gemini").available()
    assert not ok and "GEMINI_API_KEY" in why


class Broken(Generator):
    name = "api:test"

    def stream(self, system, user):
        raise TimeoutError("read timed out")
        yield  # pragma: no cover


def test_model_failure_falls_back_to_clauses():
    from answer import ask_stream
    events = list(ask_stream("What is the room rent limit?", "national_mediclaim", Broken()))
    final = events[-1]
    assert final["status"] == "answered" and final["citations"]
    assert "did not respond in time" in final["answer"]
    assert final["backend"].startswith("extractive (fallback")
