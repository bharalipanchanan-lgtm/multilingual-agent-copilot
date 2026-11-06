import os
from pathlib import Path

# hf-xet transfers stalled on this network; plain HTTPS downloads work.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

ROOT = Path(__file__).parent
POLICY_DIR = ROOT / "data" / "policies"
MANIFEST = POLICY_DIR / "manifest.csv"
CHROMA_DIR = ROOT / "data" / "chroma"
GOLD_DIR = ROOT / "eval" / "gold"
REPORT_DIR = ROOT / "eval" / "reports"
QUESTIONS = ROOT / "eval" / "questions.yaml"

COLLECTION = "policies"
MODELS_DIR = ROOT / "models"   # local copies fetched with fetch_models.sh (preferred over the HF cache)


def local_or_hub(repo: str) -> str:
    p = MODELS_DIR / repo.split("/")[-1]
    return str(p) if (p / ".fetched").exists() else repo


EMBED_MODEL = local_or_hub("BAAI/bge-m3")  # multilingual, handles Hinglish queries against English text

CHUNK_TARGET = 1100       # characters, soft target per chunk
CHUNK_MAX = 1600          # characters, hard cap before splitting by sentence
MIN_CHARS_PER_PAGE = 150  # below this a page is treated as scanned or empty


def device() -> str:
    if os.environ.get("COPILOT_DEVICE"):  # "cpu" in the cloud container
        return os.environ["COPILOT_DEVICE"]
    import torch
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"

# Generation (see generate.py). Local by default; Claude is optional and paid per token.
GEN_BACKEND = "mlx"                                    # mlx | ollama | claude | extractive
MLX_MODELS = [                                         # first fully downloaded one is used
    "mlx-community/Qwen2.5-7B-Instruct-4bit",           # about 4.3 GB, better Hindi and reasoning
    "mlx-community/Qwen2.5-3B-Instruct-4bit",           # about 1.8 GB, fallback
]
MLX_MODEL = os.environ.get("COPILOT_MLX_MODEL") or None  # force one model
OLLAMA_MODEL = "qwen2.5:7b"
OLLAMA_URL = "http://localhost:11434"
CLAUDE_MODEL = "claude-opus-5-5"

RETRIEVE_K = 5            # clauses retrieved per question
MAX_CLAUSES = 6           # cap on clauses sent to the model (prefill time dominates latency)
CLAUSE_CHARS = 900        # per clause text sent to the model
NEIGHBOURS = 1            # also pull this many chunks either side of each hit (page spanning clauses)
FACTS_DIR = ROOT / "facts"
