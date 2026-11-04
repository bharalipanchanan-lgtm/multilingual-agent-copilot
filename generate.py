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


def _fully_cached(repo: str) -> str | None:
    """Local path when every weight file of the model is on disk (models/ first, then the HF cache)."""
    from pathlib import Path
    from config import MODELS_DIR
    p = MODELS_DIR / repo.split("/")[-1]
    if (p / "config.json").exists() and not (p / ".fetched").exists():
        return None  # fetch_models.sh still downloading
    if not (p / "config.json").exists():
        try:
            from huggingface_hub import snapshot_download
            p = Path(snapshot_download(repo, local_files_only=True))
        except Exception:
            return None
    ok = _weights_complete(p)
    return str(p) if ok else None


def _weights_complete(p) -> bool:
    idx = p / "model.safetensors.index.json"
    if idx.exists():
        shards = set(json.load(open(idx))["weight_map"].values())
        return all((p / s).exists() for s in shards) and not any(p.glob("*.part"))
    return (p / "model.safetensors").exists() and (p / "tokenizer.json").exists()


class MLXGenerator(Generator):
    name = "mlx"

    def __init__(self, model: str | None = MLX_MODEL):
        self.model_id = model or next((path for m in MLX_MODELS if (path := _fully_cached(m))), None)
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
            self._cache, self._prefix, self._prefix_len = None, None, 0
        return self._model, self._tok

    def _prefill(self, prefix: str):
        """Keep the fixed system prompt pre-computed in the KV cache, so each question only
        pays for its own clauses. Rebuilt only if the system prompt changes."""
        import mlx.core as mx
        from mlx_lm.models.cache import make_prompt_cache
        if prefix == self._prefix and self._cache is not None:
            return
        ids = self._tok.encode(prefix, add_special_tokens=False)
        self._cache = make_prompt_cache(self._model)
        self._model(mx.array(ids)[None], cache=self._cache)
        mx.eval([c.state for c in self._cache])
        self._prefix, self._prefix_len = prefix, len(ids)

    def stream(self, system, user):
        from mlx_lm import stream_generate
        from mlx_lm.models.cache import trim_prompt_cache
        from mlx_lm.sample_utils import make_sampler
        model, tok = self._load()
        full = tok.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            add_generation_prompt=True, tokenize=False)
        cut = full.index(user)
        self._prefill(full[:cut])
        rest = tok.encode(full[cut:], add_special_tokens=False)
        try:
            for r in stream_generate(model, tok, rest, max_tokens=500, sampler=make_sampler(temp=0.0),
                                     prompt_cache=self._cache):
                yield r.text
        finally:
            extra = self._cache[0].offset - self._prefix_len
            if extra > 0:
                trim_prompt_cache(self._cache, extra)


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
