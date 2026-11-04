#!/bin/zsh
# Start the copilot for a demo. Works offline once models are downloaded.
cd "$(dirname "$0")"
source .venv/bin/activate
export HF_HUB_OFFLINE=1            # no network calls at load time
export COPILOT_BACKEND=${COPILOT_BACKEND:-mlx}
echo "Backend: $COPILOT_BACKEND   Open http://localhost:8000"
python -W ignore server.py
