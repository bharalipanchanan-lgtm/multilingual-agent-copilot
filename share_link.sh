#!/usr/bin/env bash
# Public demo link from this laptop, free and with no account: a Cloudflare quick tunnel to the
# copilot running here. Anyone with the link can open the chat while this script runs.
#
#   ./share_link.sh            prints https://<random-words>.trycloudflare.com ; Ctrl+C stops both
#
# Public mode: answers from Sarvam 105B (SARVAM_API_KEY in .env, uses your Sarvam credit),
# 30 questions per visitor per 10 minutes, voice off for visitors. The link changes on every run,
# and stops working when the laptop sleeps, loses internet or this script stops.
# Override the answer model with COPILOT_LLM=groq|gemini (and its key in .env), or
# COPILOT_BACKEND=mlx to use the local model (slower, about 5 s per answer).
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] && { set -a; source ./.env; set +a; }
[ -x tools/cloudflared ] || { echo "tools/cloudflared missing. Download cloudflared-darwin-arm64.tgz from"
                              echo "https://github.com/cloudflare/cloudflared/releases into tools/"; exit 1; }
export COPILOT_BACKEND=${COPILOT_BACKEND:-api} COPILOT_LLM=${COPILOT_LLM:-sarvam} COPILOT_PUBLIC=1
PORT=${COPILOT_PORT:-8000}
LOG=eval/reports; mkdir -p "$LOG"

if [ "$COPILOT_BACKEND" = api ] && [ "$COPILOT_LLM" = sarvam ] && [ -z "${SARVAM_API_KEY:-}" ]; then
  echo "No SARVAM_API_KEY in .env: answers will be verbatim clause quotes (extractive)."
fi

# a copilot already on the port may be in laptop mode (no rate limit): replace it
if lsof -ti tcp:"$PORT" >/dev/null 2>&1; then
  echo "Stopping the copilot already on port $PORT"; lsof -ti tcp:"$PORT" | xargs kill; sleep 2
fi
source .venv/bin/activate
COPILOT_PORT=$PORT python -W ignore server.py > "$LOG/share_server.log" 2>&1 &
SERVER=$!
TUNNEL=""
trap 'echo; echo "Stopping"; kill $SERVER ${TUNNEL:-} 2>/dev/null; rm -f share_url.txt' EXIT INT TERM

echo -n "Starting the copilot (public mode, $COPILOT_BACKEND ${COPILOT_LLM}) "
for _ in $(seq 1 120); do
  curl -s "localhost:$PORT/api/status" | grep -q '"ready":true' && break
  kill -0 $SERVER 2>/dev/null || { echo; echo "Server failed, see $LOG/share_server.log"; exit 1; }
  echo -n "."; sleep 1
done
echo " ready: $(curl -s "localhost:$PORT/api/status")"

# http2, not the default QUIC: QUIC connections dropped on this network mid answer
tools/cloudflared tunnel --no-autoupdate --protocol http2 --url "http://localhost:$PORT" > "$LOG/share_tunnel.log" 2>&1 &
TUNNEL=$!
URL=""
for _ in $(seq 1 60); do
  URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG/share_tunnel.log" | head -1 || true)
  [ -n "$URL" ] && break; sleep 1
done
[ -n "$URL" ] || { echo "No tunnel link, see $LOG/share_tunnel.log"; exit 1; }
# the name exists before the tunnel carries traffic (Cloudflare answers 530 until then)
echo -n "Waiting for the link to answer "
for _ in $(seq 1 60); do
  [ "$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$URL/api/status")" = 200 ] && break
  echo -n "."; sleep 2
done
echo
echo "$URL" > share_url.txt
echo
echo "Share this link: $URL"
echo "(valid while this keeps running and the laptop stays awake and online; Ctrl+C to stop)"
wait $TUNNEL
