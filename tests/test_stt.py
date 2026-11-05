"""stt.py without the network: requests.post is replaced, so no key or credit is used."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stt  # noqa: E402


class Resp:
    def __init__(self, code, body=None):
        self.status_code, self._b = code, body or {}

    def json(self):
        return self._b


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "k")
    monkeypatch.delenv("SARVAM_STT_MODE", raising=False)
    monkeypatch.delenv("SARVAM_STT_MODEL", raising=False)


def test_no_key_means_voice_off(monkeypatch):
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    assert stt.status()["enabled"] is False
    with pytest.raises(stt.STTError, match="SARVAM_API_KEY"):
        stt.transcribe(b"x", "q.webm", "audio/webm")


def test_request_carries_key_model_mode_and_audio(monkeypatch, key):
    seen = {}

    def fake_post(url, headers, data, files, timeout):
        seen.update(url=url, headers=headers, data=data, files=files)
        return Resp(200, {"transcript": " diabetes ka waiting period kitna hai ", "language_code": "hi-IN"})
    monkeypatch.setattr(stt.requests, "post", fake_post)
    out = stt.transcribe(b"\x1a\x45\xdf\xa3audio", "q.webm", "audio/webm")
    assert out["text"] == "diabetes ka waiting period kitna hai"
    assert seen["url"] == "https://api.sarvam.ai/speech-to-text"
    assert seen["headers"] == {"api-subscription-key": "k"}
    assert seen["data"] == {"model": "saaras:v3", "language_code": "unknown", "mode": "translit"}
    assert seen["files"]["file"][0] == "q.webm" and seen["files"]["file"][2] == "audio/webm"


def test_mode_is_not_sent_to_models_without_modes(monkeypatch, key):
    monkeypatch.setenv("SARVAM_STT_MODEL", "saaras:v4")
    seen = {}
    monkeypatch.setattr(stt.requests, "post", lambda url, headers, data, files, timeout: (
        seen.update(data=data), Resp(200, {"transcript": "hi"}))[1])
    stt.transcribe(b"a", "q.webm", "audio/webm")
    assert "mode" not in seen["data"]


@pytest.mark.parametrize("code,msg", [(401, "rejected the API key"), (403, "rejected the API key"),
                                      (429, "out of credit"), (500, "error \\(500\\)")])
def test_service_errors_are_plain_messages(monkeypatch, key, code, msg):
    monkeypatch.setattr(stt.requests, "post", lambda *a, **k: Resp(code))
    with pytest.raises(stt.STTError, match=msg):
        stt.transcribe(b"a", "q.webm", "audio/webm")


def test_empty_transcript_and_empty_or_huge_audio(monkeypatch, key):
    monkeypatch.setattr(stt.requests, "post", lambda *a, **k: Resp(200, {"transcript": "  "}))
    with pytest.raises(stt.STTError, match="could not hear"):
        stt.transcribe(b"a", "q.webm", "audio/webm")
    with pytest.raises(stt.STTError, match="No audio"):
        stt.transcribe(b"", "q.webm", "audio/webm")
    with pytest.raises(stt.STTError, match="too long"):
        stt.transcribe(b"0" * (stt.MAX_BYTES + 1), "q.webm", "audio/webm")


def test_network_failure(monkeypatch, key):
    def boom(*a, **k):
        raise stt.requests.ConnectionError("down")
    monkeypatch.setattr(stt.requests, "post", boom)
    with pytest.raises(stt.STTError, match="Could not reach"):
        stt.transcribe(b"a", "q.webm", "audio/webm")
