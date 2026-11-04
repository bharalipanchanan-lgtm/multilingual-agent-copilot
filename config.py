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
EMBED_MODEL = "BAAI/bge-m3"  # multilingual, handles Hinglish queries against English text

CHUNK_TARGET = 1100       # characters, soft target per chunk
CHUNK_MAX = 1600          # characters, hard cap before splitting by sentence
MIN_CHARS_PER_PAGE = 150  # below this a page is treated as scanned or empty


def device() -> str:
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

RETRIEVE_K = 6            # clauses retrieved per question
NEIGHBOURS = 1            # also pull this many chunks either side of each hit (page spanning clauses)
FACTS_DIR = ROOT / "facts"
