# NodeDash

Turn a short admin interview into a company's **operating graph**: one node per
department, each rendered as an Obsidian-style dot on a canvas and backed by its own
AI **Chief-of-Staff** agent. Click a node, log in, and you get that department's
scoped workspace — its data, its workflows, and a chat with its agent. Every agent
also has a **RAG memory** that recalls similar past exchanges for consistency.

Built for the **AMD Developer Hackathon (Act II)**. The LLM layer is
OpenAI-compatible, so it runs identically on a **local model (Ollama)**, **Fireworks
AI**, or an **AMD MI300X (vLLM + ROCm)** — a one-env-var switch — with an offline
`mock` mode so nothing blocks on credits or a GPU.

See [NodeDash-Spec.md](NodeDash-Spec.md) and
[NodeDash-Build-Lifecycle.md](NodeDash-Build-Lifecycle.md) for the concept.

## Layout

| Path | What |
|---|---|
| [`questionnaire/`](questionnaire) | The general interview definition (`questions.json`), graph-spec JSON schema, seed graph |
| [`backend/`](backend) | FastAPI: interview → LLM graph generation → provisioning → node-scoped auth → agents + RAG ([README](backend/README.md)) |
| [`frontend/`](frontend) | Zero-build SPA: admin interview + Obsidian-style graph + login-gated department windows ([README](frontend/README.md)) |

## What it does

1. **Admin interview** — a tiered questionnaire; answers compile (via LLM or offline mock) into a validated graph spec.
2. **Company graph** — departments as glowing dots, workflows as edges, in a live force layout (pan / zoom / drag).
3. **Per-node login windows** — click a dot, log in with its access code (a seat scoped to that node); its tab opens with only that node's data: responsibilities, constraints, workflows, documents, and a live agent chat.
4. **AI agents + RAG** — each node's agent answers in-character from its system prompt and guardrails, and recalls semantically similar past exchanges (shown in the chat as *"↳ recalled N past exchanges"*).

## Quickstart (fully local, no cloud)

**1. A local model via Ollama** (optional — skip for `mock` mode):
```bash
brew install ollama && ollama serve &
ollama pull qwen3:8b            # chat model
ollama pull nomic-embed-text    # embeddings for RAG
```

**2. Backend:**
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # defaults point at local Ollama; edit to taste
uvicorn app.main:app --port 8000
```

**3. Frontend** (static files, no Node needed):
```bash
cd frontend && python3 -m http.server 5173
# open http://localhost:5173  →  "⚡ Quick demo"
```

`curl localhost:8000/health` shows which model is active. For a pure offline run with
no model at all, start the backend with `LLM_PROVIDER=mock`.

## Model / provider config

One OpenAI-compatible client, switched by env vars (`backend/.env`). Nothing else changes.

```bash
# Local (Ollama)
LLM_PROVIDER=auto
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen3:8b
LLM_EMBED_MODEL=nomic-embed-text
LLM_API_KEY=ollama

# Fireworks AI (managed, pay-per-token, $0 idle)
LLM_PROVIDER=fireworks
LLM_BASE_URL=https://api.fireworks.ai/inference/v1
LLM_MODEL=accounts/fireworks/models/qwen3-...   # pick from Fireworks' catalog
LLM_API_KEY=fw_...

# AMD MI300X (vLLM + ROCm) — on AMD Developer Cloud or a DO GPU droplet
LLM_PROVIDER=amd
LLM_BASE_URL=http://<amd-host>:8000/v1
LLM_MODEL=Qwen/Qwen3-32B
# on the GPU box:  vllm serve Qwen/Qwen3-32B --port 8000 --api-key <token>
```

Qwen3 notes: its `<think>` reasoning is stripped from replies, and `LLM_NO_THINK=true`
(default) sends the `/no_think` switch for fast, clean output. `LLM_EMBED_MODEL` enables
the RAG cache; leave it unset (or use `mock`) to disable RAG cleanly.

## Deploying cost-efficiently (DigitalOcean)

The FastAPI backend is **not** the GPU — it's a tiny always-on service. Keep it (and the
static frontend) up cheaply on **DO App Platform**, and make the *model* pay-per-call so
there's **no idle GPU cost**:

- **Frontend** → App Platform static site (always on, ~free)
- **Backend** → App Platform service (always on, ~$5/mo, no GPU)
- **Model** → serverless inference (**DO Gradient** or **Fireworks**) — $0 when idle, active on call
- **AMD scoring** → spin up an **MI300X** (AMD Developer Cloud / DO GPU droplet) *only* to record the demo + benchmarks, then shut it down

A raw GPU droplet can't scale to zero (per-hour billing + minutes of cold start), so
serverless is the "idle→active" model path. See [DEPLOY.md](DEPLOY.md) for exact steps —
including **section 0: running the whole stack on the AMD Developer Cloud Jupyter box**.

## Verify

```bash
cd backend
python smoke_test.py     # 39 checks: interview → graph → node login → scoping → agent (offline)
python rag_test.py       # RAG: a reworded query recalls the prior exchange (needs an embed model)
```
