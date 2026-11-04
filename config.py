from pathlib import Path

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
