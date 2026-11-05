#!/bin/zsh
# Start the copilot for a demo. Works offline once models are downloaded.
cd "$(dirname "$0")"
source .venv/bin/activate
export HF_HUB_OFFLINE=1            # no network calls at load time
# Voice input (optional): SARVAM_API_KEY from the environment or a gitignored .env file
if [ -f .env ]; then set -a; source ./.env; set +a; fi
if [ -n "$SARVAM_API_KEY" ]; then echo "Voice input: on (Sarvam)"; else echo "Voice input: off (no SARVAM_API_KEY), typing works"; fi
export COPILOT_BACKEND=${COPILOT_BACKEND:-mlx}
echo "Backend: $COPILOT_BACKEND   Open http://localhost:8000"
python -W ignore server.py
