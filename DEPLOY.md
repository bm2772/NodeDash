# Running NodeDash on the AMD Developer Cloud

The whole app — **model + backend + frontend** — runs on the AMD GPU box, exposed to
the public with Cloudflare tunnels. The model runs locally via Ollama (which uses the
AMD ROCm GPU); the FastAPI backend and static frontend sit in front of it.

```
Your browser ──▶ Cloudflare tunnel ──▶ frontend (:5173, static)
                 Cloudflare tunnel ──▶ backend  (:8000, FastAPI)
                                          └──▶ Ollama (:11434, model on the AMD GPU)
```

These blocks are copy-paste for the box's terminal. It's a minimal container, so we fix
certs first. Run each block in order.

> **Shortcut:** after the one-time setup in steps 1–3 (certs, deps, Ollama installed),
> **[`run.sh`](run.sh)** automates the rest — start `bash run.sh` and it launches Ollama,
> the backend, the frontend, both Cloudflare tunnels, writes `config.js`, and prints the
> URL to open. `bash run.sh stop` tears it all down. The manual steps below are the same
> thing, spelled out.

## 1. Certificates + system deps

The container ships without a CA bundle, which breaks `git`/`curl`/`pip`:
```bash
apt-get update && apt-get install -y ca-certificates zstd tmux && update-ca-certificates
```
If it still complains about certificates, add a bypass: `echo insecure >> ~/.curlrc`
(and for git, prefix commands with `GIT_SSL_NO_VERIFY=true`).

## 2. Get the code

```bash
cd /workspace
git clone https://github.com/bm2772/NodeDash || (cd NodeDash && git pull)
cd NodeDash
tmux new -s nodedash        # keeps servers alive after you disconnect (Ctrl-b d to detach)
```

## 3. Model server (Ollama — auto-detects the AMD ROCm GPU)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve > /tmp/ollama.log 2>&1 &
sleep 3
ollama pull qwen3:8b            # or qwen3:32b — the MI300X (192GB) handles it
ollama pull nomic-embed-text    # embeddings for RAG
```

## 4. Backend (port 8000)

```bash
cd /workspace/NodeDash/backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cat > .env <<'EOF'
LLM_PROVIDER=auto
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen3:8b
LLM_API_KEY=ollama
LLM_EMBED_MODEL=nomic-embed-text
LLM_NO_THINK=true
JWT_SECRET=change-me-to-something-random
CORS_ORIGINS=*
EOF
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/backend.log 2>&1 &
sleep 2 && curl -s http://localhost:8000/health      # expect {"status":"ok",...}
```

## 5. Frontend (port 5173)

```bash
cd /workspace/NodeDash/frontend
nohup python3 -m http.server 5173 > /tmp/frontend.log 2>&1 &
```

## 6. Public URLs via Cloudflare tunnels

The box's `10.x` IP is private and not reachable from your browser, so tunnel both
ports. Download the **arch-correct** binary and verify it runs (a segfault means the
wrong arch or a truncated download):

```bash
ARCH=$(uname -m); [ "$ARCH" = "aarch64" ] && CF=cloudflared-linux-arm64 || CF=cloudflared-linux-amd64
curl -fsSL -o /usr/local/bin/cloudflared "https://github.com/cloudflare/cloudflared/releases/latest/download/$CF"
chmod +x /usr/local/bin/cloudflared
cloudflared --version        # MUST print a version, not "Segmentation fault"

# backend tunnel → write its URL into config.js so the UI talks to it
cloudflared tunnel --url http://localhost:8000 > /tmp/cf-back.log 2>&1 &
sleep 8
BACK=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/cf-back.log | head -1)
echo "backend  = $BACK"
echo "window.__ND_API_BASE__ = \"$BACK\";" > /workspace/NodeDash/frontend/config.js

# frontend tunnel → OPEN THIS URL IN YOUR BROWSER
cloudflared tunnel --url http://localhost:5173 > /tmp/cf-front.log 2>&1 &
sleep 8
echo "frontend = $(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /tmp/cf-front.log | head -1)"
```

## 7. Open the app

Open the **frontend** URL from step 6 in your browser → click **⚡ Quick demo**.

Ports: `11434` Ollama · `8000` backend · `5173` frontend. `CORS_ORIGINS=*` allows the
cross-tunnel call.

> **Important:** cloudflared assigns a **new random URL every restart**. If you restart
> the backend tunnel, re-run the `BACK=...` + `echo ... > config.js` line and reload the
> page — the URL inside `config.js` must always match the current backend tunnel.

## Stop everything

```bash
pkill -f uvicorn; pkill -f http.server; pkill -f cloudflared; pkill -f "ollama serve"; pkill ollama
```

## Logs (if something fails)

```bash
tail /tmp/backend.log /tmp/ollama.log /tmp/cf-back.log /tmp/cf-front.log
```

---

## Container image

For a containerized submission, the [Dockerfile](Dockerfile) builds the backend image
(Python 3.12, copies `backend/` + `questionnaire/`, runs uvicorn on `$PORT`):

```bash
docker build -t nodedash-api .
docker run -p 8000:8080 --env-file backend/.env nodedash-api
```

Serve the static `frontend/` with any web server (or `python3 -m http.server`) and point
its `config.js` at the backend URL.
