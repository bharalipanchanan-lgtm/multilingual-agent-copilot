"""Deploy the copilot to a Hugging Face Space (Docker), so anyone with the link can open the chat.

  HF_TOKEN=hf_...  python deploy_hf.py  your-hf-username/claviq-copilot

What it does:
  1. creates the Space (Docker SDK, public) if it does not exist yet
  2. stores the answer model key as a Space secret, from whichever of GROQ_API_KEY,
     GEMINI_API_KEY or SARVAM_API_KEY is set here (read from the environment or .env, never printed)
  3. uploads the files tracked by git (so .env, models/ and data/chroma never leave the laptop)
     plus a Space README; the Space then builds the Dockerfile: bge-m3 and the search index are
     built inside the image

The token needs write access (huggingface.co/settings/tokens). Voice stays off on the public
Space unless you also pass --voice, because every spoken question spends your Sarvam credit.
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")  # xet transfers stalled on this network

SPACE_README = """---
title: Claviq Agent Copilot
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: Health policy Q&A for insurance agents (prototype)
---

Prototype of the Claviq multilingual agent copilot. Answers come only from the policy document,
with the clause and page; when the document does not say, it says so. Demo only: no real
customer data. Source: https://github.com/bharalipanchanan-lgtm/multilingual-agent-copilot
"""


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("space", help="username/space-name")
    ap.add_argument("--private", action="store_true", help="only you can open it (default: public link)")
    ap.add_argument("--voice", action="store_true", help="turn voice on for visitors (spends your Sarvam credit)")
    a = ap.parse_args()
    load_env()
    token = os.environ.get("HF_TOKEN")
    if not token:
        sys.exit("Set HF_TOKEN (a write token from huggingface.co/settings/tokens).")

    from huggingface_hub import HfApi
    api = HfApi(token=token)
    api.create_repo(a.space, repo_type="space", space_sdk="docker", private=a.private, exist_ok=True)
    print("Space:", f"https://huggingface.co/spaces/{a.space}")

    llm = next((p for p, k in (("groq", "GROQ_API_KEY"), ("gemini", "GEMINI_API_KEY"), ("sarvam", "SARVAM_API_KEY"))
                if os.environ.get(k)), None)
    if llm:
        key = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY", "sarvam": "SARVAM_API_KEY"}[llm]
        api.add_space_secret(a.space, key, os.environ[key])
        api.add_space_variable(a.space, "COPILOT_LLM", llm)
        print(f"Answer model: {llm} (key stored as a Space secret)")
    else:
        print("No answer model key set: the Space will quote clauses verbatim (extractive).")
    if a.voice and os.environ.get("SARVAM_API_KEY"):
        api.add_space_secret(a.space, "SARVAM_API_KEY", os.environ["SARVAM_API_KEY"])
        api.add_space_variable(a.space, "COPILOT_PUBLIC_VOICE", "1")
        print("Voice: on (Sarvam)")

    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    files = [f for f in files if not f.startswith(("tests/voice/clips/", "handoff/")) and f != ".env"]
    with tempfile.TemporaryDirectory() as tmp:
        for f in files:
            src, dst = ROOT / f, Path(tmp) / f
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())
        (Path(tmp) / "README.md").write_text(SPACE_README, encoding="utf-8")
        api.upload_folder(folder_path=tmp, repo_id=a.space, repo_type="space",
                          commit_message="Deploy from the laptop (deploy_hf.py)")
    print(f"Uploaded {len(files)} files. The Space is building; first build takes about 10 minutes.")
    print(f"Open: https://{a.space.replace('/', '-').lower()}.hf.space")


if __name__ == "__main__":
    main()
