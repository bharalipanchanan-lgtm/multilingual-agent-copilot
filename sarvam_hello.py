"""One Sarvam chat completion call, to confirm the SDK and key work.

  python sarvam_hello.py

Reads SARVAM_API_KEY from the environment, or from the gitignored .env file in this folder.
The key is never printed.
"""
import os
from pathlib import Path

from sarvamai import SarvamAI

env = Path(__file__).resolve().parent / ".env"
if not os.environ.get("SARVAM_API_KEY") and env.exists():
    for line in env.read_text().splitlines():
        if line.strip().startswith("SARVAM_API_KEY="):
            os.environ["SARVAM_API_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")

key = os.environ.get("SARVAM_API_KEY")
if not key:
    raise SystemExit("SARVAM_API_KEY is not set. Paste it into .env as SARVAM_API_KEY=your_key")

client = SarvamAI(api_subscription_key=key)
response = client.chat.completions(
    model="sarvam-105b-conversations",
    messages=[{"role": "user", "content": "Say hello in Hindi and English in one short line."}],
)
print(response.choices[0].message.content)
