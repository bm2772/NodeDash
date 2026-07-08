# AgentGraph — Build Lifecycle & Delivery Plan

*Companion to the AgentGraph concept spec · Version 0.1 — hackathon delivery plan*

---

## 0. How to read this

There are two lifecycles in play, and this plan covers both:

- **The build lifecycle** — how your team makes the platform. This is Sections 1–6 and is the spine of the plan.
- **The runtime lifecycle** — what the platform does once built (setup → generate → provision → operate → adapt). This is Section 7.

The build plan is organized by **phase**, not by clock hours, so it maps onto whatever timebox the hackathon gives you — a weekend or a multi-week challenge. A rough effort split is noted so you can scale it.

**Scope assumption:** a 5-person team building the MVP spine, not the full product.

---

## 1. Guiding principles (hackathon discipline)

These are the rules that keep a 5-person team from thrashing:

1. **Build the contract first, freeze it, parallelize around it.** The graph-spec schema is the one artifact everything depends on. Lock it early; change it only by team decision.
2. **One vertical slice, deep — not the whole factory, shallow.** A single procurement → finance → vendor flow that works end-to-end beats ten half-built node types.
3. **Seed data unblocks everyone.** A hand-written example graph lets frontend, backend, and AI all work in parallel before anything is integrated.
4. **Protect integration and demo-polish time.** Teams always underestimate these. Front-load the risk by getting a "walking skeleton" (even a faked end-to-end path) working early.
5. **Always have a fallback.** A pre-generated graph, a recorded demo video, and a hosted-API failover mean one live failure doesn't kill the presentation.

---

## 2. Team & roles (5 people)

| Role | Owns | Also covers |
|---|---|---|
| **Product / Demo lead (PM)** | Scope discipline, the demo scenario, the pitch, track mapping | Floats to wherever integration is stuck |
| **Frontend / Canvas** | React Flow graph, node dashboards, real-time collab, document blocks | Demo legibility (animations, message log) |
| **Backend / Orchestration** | State store, event system, agent message bus, API, DB | Deployment / wiring |
| **AI — Generation & Infra** | Onboarding interview, graph-generation LLM, ROCm + vLLM + Qwen serving, JSON reliability | Model fallbacks |
| **AI — Agents & Coordination** | Agent design, prompt templating, tool-calling, negotiation / propagation logic | Exception handling |

The PM role is not optional in a hackathon — someone must guard scope and own the demo, or the team over-builds and under-rehearses.

---

## 3. The lifecycle at a glance

`Foundations → Graph-spec contract → [Canvas ∥ Backend ∥ AI layer] → Integration → Demo slice → Ship & pitch`

Rough effort split (scale to your timebox):

| Phase | Share of effort |
|---|---|
| 0 · Foundations | ~10% |
| 1 · Contract | ~10% |
| 2 · Parallel build | ~35% |
| 3 · Integration | ~20% |
| 4 · Demo slice | ~15% |
| 5 · Ship & pitch | ~10% |

Integration + demo slice together are a third of the work — plan for that up front.

---

## 4. Phase by phase

### Phase 0 — Foundations

**Goal:** everything needed before anyone writes feature code.

- Repo, scaffolding, task board, and the agreed MVP scope + demo beat (in writing).
- Stand up infra: spin up the AMD GPU, ROCm + vLLM, serve one Qwen model (35B-A3B MoE or 14B dense), and verify an OpenAI-compatible endpoint returns a working **tool call** end to end.
- Design tokens / UI shell so the frontend isn't styling from zero later.

**Exit criteria:** a request to the model returns a valid tool call; the repo runs; scope and the demo scenario are written down and agreed.

**Main risk:** infra setup eats a whole day. Mitigate by having the Infra owner on it from minute zero, with a hosted-API fallback ready if the GPU is delayed.

### Phase 1 — The contract (graph spec + data model)

**Goal:** the shared contract every workstream keys off.

- Finalize the **graph-spec JSON schema** (nodes, edges, per-node agent config) from the concept spec.
- Define the **DB schema**: `nodes`, `edges`, `documents`, `agent_configs`.
- Write **one realistic example graph** (procurement → finance → vendor) as committed seed data.
- Add schema validation so malformed graphs fail loudly.

**Exit criteria:** schema frozen and committed; the example graph loads and validates; the team agrees not to change the schema without a group decision.

**Main risk:** schema churn later breaks all three lanes at once. Freeze early, version it, require sign-off to change.

### Phase 2 — Parallel build (three lanes off the contract)

All three lanes code against the frozen schema and the seed graph, so nobody is blocked on anyone else.

**Lane A — Canvas / frontend**
- Render the graph from the spec in React Flow.
- Build the per-node dashboard view.
- Real-time collaboration (Liveblocks or Yjs).
- Document blocks attached to nodes/edges.
- Hooks for edge highlighting / animation (used later for demo legibility).

**Lane B — Backend / orchestration**
- Load and serve the graph.
- State store for node/edge state.
- Event system (an event = something happened at a node or along an edge).
- Agent message bus (agent-to-agent communication).
- The API/WebSocket layer the frontend consumes.

**Lane C — AI layer**
- *Generation:* the onboarding interview (5–8 questions) → LLM emits graph JSON constrained to the schema, using guided/structured decoding for reliability.
- *Agents:* system-prompt template filled from each node's config; a tool set (read node state, message a neighbor, update timeline/ETA, flag an exception); coordination logic (on a change → recompute → notify downstream → renegotiate).

**Exit criteria per lane:** A renders the seed graph plus one dashboard; B propagates a test event between two nodes; C generates a valid graph from a text description *and* has one agent complete one action plus one hand-off message.

**Main risk:** lanes drift from the contract. Mitigate with a daily 10-minute sync and a mid-phase integration checkpoint.

### Phase 3 — Integration

**Goal:** the full loop working for the one flow.

- Wire onboarding → generated graph → canvas render → agents live on the graph → events propagate → canvas updates.
- Swap seed data for the live-generated graph (keep the seed path as a fallback).

**Exit criteria:** describe a company → a graph appears → trigger the procurement cycle → an agent acts → a hand-off fires → the canvas reflects it.

**Main risk:** this is the crunch phase and the usual failure point. Budget generously, and keep the seed-graph path available so a flaky generator doesn't block the rest.

### Phase 4 — Demo slice (the vertical slice, deep)

**Goal:** the one scenario that wins the room.

- Build the cascade: a vendor slips a checkpoint → its agent recomputes ETA and rebalances its other jobs → renegotiates with the procurement agent → finance/production schedules visibly update on the canvas.
- Fully provision **one** node's dashboard.
- Make it **legible**: edges light up, timelines shift, agent messages post to a visible log. A judge who's never seen it must be able to *watch* the cascade happen.

**Exit criteria:** the scenario runs start-to-finish, reliably, and reads clearly to a first-time viewer.

**Main risk:** the cascade is too subtle to read. Invest in visual legibility — the propagation is the whole point, so it must be seen, not explained.

### Phase 5 — Ship & pitch

**Goal:** a rehearsed, fail-safe presentation.

- Lock the demo path; add fallbacks (pre-generated graph, recorded backup video, hosted-API failover if the GPU dies).
- Write and rehearse the pitch, mapping it explicitly to **track 2 and track 3**.
- Build slides; run the demo 3+ times; assign who drives and who narrates.

**Exit criteria:** rehearsed demo + backup video + deck; every teammate can run the happy path.

### Phase 6 — Present & next steps

Present, then close with a short "if we kept going" roadmap for the judges — auth/roles/permissions, more node types, real integrations (email/ERP), multi-company scale, agent memory/RAG, evaluation of agent decisions. It signals vision beyond the demo.

---

## 5. Critical path & dependencies

- **The graph spec is the bottleneck resource.** Phase 1 gates everything downstream — treat it as the critical path.
- **Seed/mock data is the decoupler.** It's what lets the three lanes run in parallel instead of in series.
- **Test the end-to-end skeleton early.** Aim for a "walking skeleton" — even a faked cascade on the seed graph — by the end of Phase 2. Finding the integration seams early is worth more than any single polished feature.

---

## 6. Risk register

| Risk | Mitigation |
|---|---|
| Schema churn breaks all lanes | Freeze early; version it; changes need team sign-off |
| Live graph-gen emits invalid JSON | Constrained decoding + schema validation + retry; seed-graph fallback |
| GPU / infra flakiness | Hosted-API failover; keep the model instance monitored |
| Integration crunch | Walking skeleton early; PM guards the timeline |
| Demo cascade illegible | Invest in canvas animation + a visible message log |
| Scope creep | PM enforces the one-slice rule; park extras in a backlog |
| Agents over-message each other | Cap negotiation rounds; use deterministic tie-breakers |

---

## 7. The runtime lifecycle the platform executes

This is the *other* meaning of "lifecycle" — what the product does once built. Phases 1–4 above are literally the implementation of this loop.

1. **Setup** — a guided AI interview with the admin, across the four tiers (macro / micro / workflow / AI agency).
2. **Generation** — the interview compiles into the graph spec: nodes, edges, and per-node agent configs.
3. **Provisioning** — the database is seeded, the canvas rendered, per-employee scoped views created, and each agent initialized with its system prompt and guardrails.
4. **Operation** — a cycle triggers (a contract is signed, inventory drops); work flows along the edges; each agent manages its node and juggles that role's concurrent jobs; agents coordinate along edges; exceptions are handled per guardrail (auto-renegotiate / alert human / halt downstream).
5. **Adaptation** — the admin edits the canvas; affected agents reconfigure; the graph evolves as the company changes.

The build plan and this runtime loop are two views of the same system: you are building the machine that runs this cycle.

---

## 8. Definition of done (the demo)

A single checklist the whole team aligns on:

- [ ] Describe a company in plain language → a valid graph generates
- [ ] At least one node's dashboard is fully provisioned
- [ ] Trigger an operational cycle → an agent takes an action
- [ ] A hand-off fires along an edge with the right payload
- [ ] A vendor slips → the cascade propagates visibly across the canvas
- [ ] The system recovers (renegotiated timeline, updated downstream)
- [ ] The pitch maps clearly to track 2 and track 3
- [ ] A backup video and fallback graph exist
