# NodeDash / AgentGraph — Backend

FastAPI backend for the AgentGraph concept: run the onboarding **questionnaire**,
compile the answers into a company **operating graph**, and expose **each node as a
login-gated window** with its own AI Chief-of-Staff agent.

Built for the AMD hackathon: the LLM client is OpenAI-compatible, so it points at
**Fireworks AI** or an **AMD-cloud vLLM/ROCm** endpoint interchangeably — and a
`mock` provider builds the graph offline so nothing blocks on credits or the GPU.

## The four pieces you asked for

| Ask | Where it lives |
|---|---|
| Works off a **general JSON questionnaire** | [`app/questionnaire.py`](app/questionnaire.py) reads `questionnaire/questions.json` — the interview is *data*, swap the file and the questions change. |
| **Prompts the admin the questions** | `POST /interview/start`, `/answer`, walked tier by tier ([`routers/interview.py`](app/routers/interview.py)). |
| **Builds the company graph from answers** | [`app/generation.py`](app/generation.py) → LLM (or offline mock) → validated graph spec → [`app/provisioning.py`](app/provisioning.py) persists nodes/edges. |
| **Each node = a window requiring login to see its data** | Per-node access codes + node-scoped JWTs. `POST /auth/node-login` then `GET /workspace/{id}/nodes/{node_key}` ([`routers/nodes.py`](app/routers/nodes.py), [`deps.py`](app/deps.py)). |

## Architecture

```
Admin ──interview──▶ answers ──generate──▶ [ LLM | mock ] ──▶ graph spec
                                                                  │ validate + normalize (app/graph_spec.py)
                                                                  ▼
                                                          provision (DB)
                                          workspace · nodes · edges · documents
                                                                  │
                       ┌──────────────────────────────────────────┼───────────────────────────┐
                       ▼                                           ▼                           ▼
             public canvas (no auth)                    node window (scoped login)      agent bus (WS)
          GET /workspace/{id}/public              POST /auth/node-login → JWT(node)   invoke agent + messages
```

- **Auth is deliberately dependency-free**: stdlib PBKDF2 password hashing + HS256
  JWT ([`app/security.py`](app/security.py)). No passlib / jose / native crypto.
- **Graph validation is self-contained** ([`app/graph_spec.py`](app/graph_spec.py)) —
  no `jsonschema`. It also *normalizes* messy LLM output (adds `node_`/`edge_`
  prefixes, coerces strings→lists, fixes edge references) before validating.
- **Node scoping**: a member JWT carries a single `node_key`; `require_node_access`
  lets that seat (or the workspace admin) through and 403s everyone else. A Finance
  seat sees Finance documents only.

## Run it

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Option A — provision the committed Acme graph directly (no LLM):
python seed.py           # prints workspace_id, admin login, per-node access codes

# Start the API (interactive docs at http://localhost:8000/docs):
uvicorn app.main:app --reload
```

### End-to-end offline test

```bash
python smoke_test.py     # 39 checks: interview → graph → node login → scoping → agent
```

## LLM configuration

Copy `.env.example` → `.env`. `LLM_PROVIDER` is `auto | fireworks | amd | mock`.

```bash
# Fireworks AI
LLM_PROVIDER=fireworks
LLM_BASE_URL=https://api.fireworks.ai/inference/v1
LLM_MODEL=accounts/fireworks/models/qwen2p5-72b-instruct
LLM_API_KEY=fw_...

# AMD cloud (vLLM + ROCm, OpenAI-compatible)
LLM_PROVIDER=amd
LLM_BASE_URL=http://<amd-host>:8000/v1
LLM_MODEL=Qwen/Qwen2.5-32B-Instruct
LLM_API_KEY=EMPTY
```

`auto` uses the endpoint when an API key (or non-default base URL) is set, otherwise
falls back to the offline `mock` generator. Generation also self-heals: if the LLM
returns invalid JSON it gets one **repair round** with the exact validation errors,
then falls back to `mock` so a demo never dies on a flaky model.

## API surface

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | – | Status + which LLM is wired |
| GET | `/interview/questionnaire` | – | The questionnaire definition |
| POST | `/interview/start` | – | Begin an interview (admin creds) |
| POST | `/interview/{id}/answer` | – | Submit one answer, get the next question |
| POST | `/interview/{id}/generate` | – | Compile → provision → returns graph + admin token + node access codes |
| GET | `/workspace/{id}/public` | – | Canvas data (labels + edges, no secrets) |
| GET | `/workspace/{id}/graph` | member | Full graph spec |
| POST | `/auth/login` | – | Admin/member login |
| POST | `/auth/node-login` | – | Claim/authenticate a **node-scoped** seat via access code |
| GET | `/auth/me` | any | Current token's scope |
| GET | `/workspace/{id}/nodes/{node_key}` | **node** | The node window: config, neighbours, documents |
| GET | `/workspace/{id}/nodes/{node_key}/documents` | **node** | Scoped documents |
| POST | `/workspace/{id}/nodes/{node_key}/agent/invoke` | **node** | Run the node's agent (+ optional edge handoffs) |
| GET | `/workspace/{id}/messages` | member | Agent message-bus log |
| WS | `/workspace/{id}/ws?token=…` | member | Live message-bus feed |

## Data model

`workspaces · nodes · edges · documents · messages · interview_sessions · users`
([`app/models.py`](app/models.py)). SQLite by default; set `DATABASE_URL` for Postgres.

## Notes / next steps

- Tables auto-create on startup (`lifespan` in [`app/main.py`](app/main.py)); for
  real deployments add Alembic migrations.
- The agent runtime is a single LLM call per invoke plus edge-handoff messages — the
  seed of the negotiation loop. Phase 4's cascade (vendor slips → renegotiate →
  downstream updates) builds on top of the message bus here.
