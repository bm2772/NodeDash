# Deploying NodeDash (Option B: on-demand AMD GPU + tiered fallback)

The goal: **frontend + API always up (cheap), the expensive GPU idles to zero and
wakes on demand, and users never wait** — instant answers come from an always-on
fallback while the AMD MI300X warms in the background, then calls route to it.

```
Judge → Frontend (Vercel, static, always on)
         → Backend / FastAPI (always on, cheap, NOT a GPU)
              ├─ GPU ready?  → route to AMD MI300X (vLLM + ROCm)
              └─ GPU cold?   → answer from fallback NOW, wake the GPU in the background
         idle watchdog → destroys the GPU droplet after GPU_IDLE_MINUTES (stops billing)
```

Note: AMD Developer Cloud runs on **DigitalOcean**, so the MI300X is a DO **GPU
Droplet** and is controlled with the DO API. On DO a *powered-off* droplet still
bills — only **destroying** it stops the meter — so "idle → zero" means
destroy-on-idle and recreate-from-snapshot on demand.

---

## 1. Frontend → Vercel (static, free, always on)

The frontend is plain static files — no build step.

1. In Vercel: **New Project → import the repo → set Root Directory to `frontend`.**
   Framework preset: **Other**. No build command, no install command.
2. Point it at your backend: edit [`frontend/config.js`](frontend/config.js) before
   deploying —
   ```js
   window.__ND_API_BASE__ = "https://your-backend.example.com";
   ```
   (Users can still override it at runtime via the start screen's "Backend URL" field.)
3. Deploy. [`frontend/vercel.json`](frontend/vercel.json) sets clean URLs + no-cache.

Alternatives: DO App Platform static site, Cloudflare Pages, Netlify, GitHub Pages.

## 2. Backend → always-on, cheap (no GPU)

Runs anywhere that keeps a small container up. **DO App Platform** or a **$6–12/mo
Droplet** are both fine — this box holds the DB, auth, RAG, and orchestrates the GPU.

```bash
# on the host
git clone <repo> && cd NodeDash/backend
python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
# set env (see §4), then:
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Set `CORS_ORIGINS` to your Vercel URL. Use a real `DATABASE_URL` (Postgres) for
persistence, or SQLite for a demo.

**Always-on fallback model** (`LLM_*`): use **DO Gradient serverless** or **Fireworks**
— pay-per-token, `$0` idle, instant. This is what answers while the GPU warms.

## 3. On-demand AMD MI300X (the GPU tier)

**a) Bake a snapshot once** so waking is fast (boot, not download):

```bash
# on a MI300X GPU droplet (AMD Developer Cloud / DO), one time:
pip install vllm     # ROCm build
# create a systemd service that runs on boot, e.g.:
#   vllm serve Qwen/Qwen3-32B --host 0.0.0.0 --port 8000 --api-key $GPU_TOKEN
# pre-download the weights so they're in the image, then:
#   DO dashboard → this droplet → Snapshots → Take snapshot   (note the snapshot ID)
```

**b) Give the backend DO credentials + snapshot** (see §4). Then it manages the
lifecycle automatically:
- first chat while cold → `POST /v2/droplets` from the snapshot → poll `/v1/models` →
  route to it once healthy (fallback answers in the meantime)
- no chats for `GPU_IDLE_MINUTES` → `DELETE /v2/droplets/{id}` (billing stops)

**c) Endpoints/UI:** `GET /model/status` drives the top-right pill
(`ready` ● / `warming` ◌ / `off` ○); `POST /model/wake` pre-warms before a demo; each
reply carries `served_by` (shown as *"via AMD MI300X"* / *"via fallback"*).

> Stable address: point `GPU_BASE_URL` at a **DO Reserved IP** you re-assign on
> create, or let the manager use the new droplet's public IP automatically (default).

## 4. Environment reference (`backend/.env`)

```bash
# --- always-on fallback (instant) ---
LLM_PROVIDER=fireworks          # or a DO Gradient endpoint, or local ollama
LLM_BASE_URL=https://api.fireworks.ai/inference/v1
LLM_MODEL=accounts/fireworks/models/qwen3-...
LLM_API_KEY=fw_...
LLM_EMBED_MODEL=nomic-ai/nomic-embed-text-v1.5   # RAG embeddings

# --- on-demand AMD MI300X ---
GPU_MANAGE=true
GPU_MODEL=Qwen/Qwen3-32B
GPU_API_KEY=<vllm-token>
GPU_IDLE_MINUTES=15
GPU_VLLM_PORT=8000
# GPU_BASE_URL=http://<reserved-ip>:8000/v1   # optional; else resolved from the new droplet

# --- DigitalOcean droplet lifecycle ---
DO_API_TOKEN=dop_v1_...
DO_GPU_SNAPSHOT_ID=<snapshot id from §3a>
DO_GPU_SIZE=gpu-mi300x1-192gb
DO_REGION=atl1
DO_SSH_KEY_IDS=12345,67890

# --- misc ---
CORS_ORIGINS=https://your-frontend.vercel.app
JWT_SECRET=<random>
```

Leave `GPU_MANAGE=false` (default) and the app just uses the always-on model — handy
for local dev and as a safety net if the GPU tier misbehaves.

## Cost summary

| Component | When it costs |
|---|---|
| Frontend (Vercel) | free |
| Backend (App Platform / small droplet) | ~$6–12 / mo, always on |
| Fallback model (Gradient / Fireworks) | per token, `$0` idle |
| AMD MI300X | only while awake (~$2/hr); destroyed after idle → `$0` |
