#!/usr/bin/env bash
# Run the whole NodeDash stack on one box (model + backend + frontend) and expose it
# with Cloudflare tunnels. Idempotent — re-running restarts the app servers cleanly.
#
#   bash run.sh          start / restart everything, print the public URL
#   bash run.sh stop     stop everything (including Ollama)
#
# Prerequisites (one-time, see DEPLOY.md §1-3):
#   apt-get install -y ca-certificates zstd
#   ollama installed  (curl -fsSL https://ollama.com/install.sh | sh)

set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL="${LLM_MODEL:-qwen3:8b}"
EMBED="${LLM_EMBED_MODEL:-nomic-embed-text}"
OLLAMA_PORT=11434
BACK_PORT=8000
FRONT_PORT=5173

log() { printf '\033[36m[run]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[run] ERROR:\033[0m %s\n' "$*"; exit 1; }

stop_app() {
  pkill -f "uvicorn app.main:app" 2>/dev/null || true
  pkill -f "http.server ${FRONT_PORT}" 2>/dev/null || true
  pkill -f "cloudflared tunnel" 2>/dev/null || true
}

if [ "${1:-}" = "stop" ]; then
  log "stopping everything…"; stop_app; pkill -f "ollama serve" 2>/dev/null || true
  log "stopped."; exit 0
fi

command -v ollama >/dev/null 2>&1 || die "ollama not installed — run: curl -fsSL https://ollama.com/install.sh | sh"

log "restarting app servers…"; stop_app; sleep 1

# ---------- 1. Model server (Ollama on the AMD GPU) ----------
if ! curl -s "http://localhost:${OLLAMA_PORT}/api/version" >/dev/null 2>&1; then
  log "starting ollama…"
  nohup ollama serve > /tmp/ollama.log 2>&1 &
  for _ in $(seq 1 20); do curl -s "http://localhost:${OLLAMA_PORT}/api/version" >/dev/null 2>&1 && break; sleep 1; done
fi
ollama list | grep -qF "$MODEL" || { log "pulling $MODEL…"; ollama pull "$MODEL"; }
ollama list | grep -qF "$EMBED" || { log "pulling $EMBED…"; ollama pull "$EMBED"; }

# ---------- 2. Backend ----------
cd "$ROOT/backend"
[ -d .venv ] || { log "creating venv…"; python3 -m venv .venv; }
# shellcheck disable=SC1091
. .venv/bin/activate
log "installing backend deps…"; pip install -q -r requirements.txt
if [ ! -f .env ]; then
  log "writing backend/.env…"
  cat > .env <<EOF
LLM_PROVIDER=auto
LLM_BASE_URL=http://localhost:${OLLAMA_PORT}/v1
LLM_MODEL=${MODEL}
LLM_API_KEY=ollama
LLM_EMBED_MODEL=${EMBED}
LLM_NO_THINK=true
JWT_SECRET=$(python3 -c 'import secrets;print(secrets.token_hex(32))')
CORS_ORIGINS=*
EOF
fi
log "starting backend on :${BACK_PORT}…"
nohup uvicorn app.main:app --host 0.0.0.0 --port "${BACK_PORT}" > /tmp/backend.log 2>&1 &
for _ in $(seq 1 30); do curl -s "http://localhost:${BACK_PORT}/health" >/dev/null 2>&1 && break; sleep 1; done
curl -s "http://localhost:${BACK_PORT}/health" >/dev/null 2>&1 || die "backend didn't come up — check /tmp/backend.log"

# ---------- 3. Frontend ----------
cd "$ROOT/frontend"
log "starting frontend on :${FRONT_PORT}…"
nohup python3 -m http.server "${FRONT_PORT}" > /tmp/frontend.log 2>&1 &

# ---------- 4. cloudflared ----------
if ! command -v cloudflared >/dev/null 2>&1; then
  log "installing cloudflared…"
  ARCH=$(uname -m); [ "$ARCH" = "aarch64" ] && CF=cloudflared-linux-arm64 || CF=cloudflared-linux-amd64
  curl -fsSL -o /usr/local/bin/cloudflared "https://github.com/cloudflare/cloudflared/releases/latest/download/$CF"
  chmod +x /usr/local/bin/cloudflared
fi
cloudflared --version >/dev/null 2>&1 || die "cloudflared won't run (wrong arch or bad download). Re-download and retry."

url_from() { grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$1" 2>/dev/null | head -1; }

log "opening backend tunnel…"; : > /tmp/cf-back.log
nohup cloudflared tunnel --url "http://localhost:${BACK_PORT}" > /tmp/cf-back.log 2>&1 &
for _ in $(seq 1 25); do BACK_URL="$(url_from /tmp/cf-back.log)"; [ -n "${BACK_URL:-}" ] && break; sleep 1; done
[ -n "${BACK_URL:-}" ] || die "no backend tunnel URL — check /tmp/cf-back.log"
printf 'window.__ND_API_BASE__ = "%s";\n' "$BACK_URL" > "$ROOT/frontend/config.js"

log "opening frontend tunnel…"; : > /tmp/cf-front.log
nohup cloudflared tunnel --url "http://localhost:${FRONT_PORT}" > /tmp/cf-front.log 2>&1 &
for _ in $(seq 1 25); do FRONT_URL="$(url_from /tmp/cf-front.log)"; [ -n "${FRONT_URL:-}" ] && break; sleep 1; done

echo
echo "================================================================"
echo "  OPEN IN YOUR BROWSER:  ${FRONT_URL:-<check /tmp/cf-front.log>}"
echo "  backend API:           $BACK_URL   (written to frontend/config.js)"
echo "================================================================"
echo "  logs: tail /tmp/{ollama,backend,cf-back,cf-front}.log"
echo "  stop: bash run.sh stop"
