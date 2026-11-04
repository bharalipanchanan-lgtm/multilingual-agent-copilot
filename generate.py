"""Generation behind one interface so local models and Claude can be swapped by config.

Backends
  mlx        local, Apple Silicon, via mlx-lm (default; no server needed)
  ollama     local, needs the Ollama app running on localhost:11434
  claude     optional, paid per token, needs ANTHROPIC_API_KEY
  extractive no LLM at all: returns the best matching clauses verbatim (always works)

Pick with the COPILOT_BACKEND environment variable or config.GEN_BACKEND.
"""
import json
import os
import urllib.request
from typing import Iterator

from config import CLAUDE_MODEL, GEN_BACKEND, MLX_MODEL, MLX_MODELS, OLLAMA_MODEL, OLLAMA_URL


class Generator:
    name = "base"

    def stream(self, system: str, user: str) -> Iterator[str]:
        raise NotImplementedError

    def available(self) -> tuple[bool, str]:
        return True, ""


def _fully_cached(repo: str) -> bool:
    """True when every weight file of a Hugging Face repo is in the local cache."""
    try:
        from huggingface_hub import snapshot_download
        path = snapshot_download(repo, local_files_only=True)
    except Exception:
        return False
    from pathlib import Path
    p = Path(path)
    idx = p / "model.safetensors.index.json"
    if idx.exists():
        shards = set(json.load(open(idx))["weight_map"].values())
        return all((p / s).exists() for s in shards)
    return (p / "model.safetensors").exists() and (p / "tokenizer.json").exists()


class MLXGenerator(Generator):
    name = "mlx"

    def __init__(self, model: str | None = MLX_MODEL):
        self.model_id = model or next((m for m in MLX_MODELS if _fully_cached(m)), None)
        self._model = self._tok = None
        if self.model_id:
            self.name = "mlx:" + self.model_id.split("/")[-1]

    def available(self):
        try:
            import mlx_lm  # noqa: F401
        except Exception as e:  # pragma: no cover
            return False, f"mlx-lm not installed ({e})"
        if not self.model_id:
            return False, "no MLX model downloaded yet"
        return True, ""

    def _load(self):
        if self._model is None:
            from mlx_lm import load
            self._model, self._tok = load(self.model_id)
        return self._model, self._tok

    def stream(self, system, user):
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler
        model, tok = self._load()
        prompt = tok.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            add_generation_prompt=True, tokenize=False)
        for r in stream_generate(model, tok, prompt, max_tokens=500, sampler=make_sampler(temp=0.0)):
            yield r.text


class OllamaGenerator(Generator):
    name = "ollama"

    def __init__(self, model: str = OLLAMA_MODEL, url: str = OLLAMA_URL):
        self.model_id, self.url = model, url

    def available(self):
        try:
            urllib.request.urlopen(f"{self.url}/api/tags", timeout=1)
            return True, ""
        except Exception as e:
            return False, f"Ollama not reachable at {self.url} ({e})"

    def stream(self, system, user):
        body = json.dumps({"model": self.model_id, "stream": True, "options": {"temperature": 0},
                           "messages": [{"role": "system", "content": system},
                                        {"role": "user", "content": user}]}).encode()
        req = urllib.request.Request(f"{self.url}/api/chat", body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            for line in resp:
                if line.strip():
                    msg = json.loads(line)
                    yield msg.get("message", {}).get("content", "")


class ClaudeGenerator(Generator):
    """Optional. Paid per token; not covered by a claude.ai subscription."""
    name = "claude"

    def __init__(self, model: str = CLAUDE_MODEL):
        self.model_id = model
        self._client = None

    def available(self):
        try:
            import anthropic  # noqa: F401
        except Exception:
            return False, "anthropic package not installed (pip install anthropic)"
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            return False, "no ANTHROPIC_API_KEY set"
        return True, ""

    def stream(self, system, user):
        import anthropic
        if self._client is None:
            self._client = anthropic.Anthropic()
        with self._client.messages.stream(
            model=self.model_id,
            max_tokens=4000,
            system=system,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": user}],
        ) as stream:
            for text in stream.text_stream:
                yield text


class ExtractiveGenerator(Generator):
    """No model. The pipeline renders quoted clauses itself; this yields nothing."""
    name = "extractive"

    def stream(self, system, user):
        return iter(())


BACKENDS = {"mlx": MLXGenerator, "ollama": OllamaGenerator, "claude": ClaudeGenerator,
            "extractive": ExtractiveGenerator}


def get_generator(name: str | None = None) -> Generator:
    name = (name or os.environ.get("COPILOT_BACKEND") or GEN_BACKEND).lower()
    gen = BACKENDS[name]()
    ok, why = gen.available()
    if not ok:
        print(f"[generate] backend '{name}' unavailable: {why}. Falling back to extractive.")
        return ExtractiveGenerator()
    return gen
