# NodeDash — Concept & Onboarding Specification

*Working title: NodeDash (alt: NodeSync AI) · Version 0.1 — hackathon spec*

---

## 1. Concept

### 1.1 Elevator pitch

A node-based, interactive workspace that visually maps a company's operational workflows. Every node is a human role or department paired with a dedicated, context-aware AI agent. The agents communicate across the graph to optimize timelines, manage dependencies, and automate cross-team coordination — so the operation runs itself *between* the deadlines, not just *at* them.

### 1.2 System model

The workspace is a directed graph, **G = (V, E)**, with three primitives:

- **The canvas** — the visual surface where operations (procurement, manufacturing, logistics) are laid out and edited in real time, Figma-style.
- **The nodes (V)** — a workspace for one role: Procurement Manager, Finance, External Vendor. Each node pairs a *human* with an *AI agent* that acts as the role's **Chief of Staff**. The agent owns local tasks, juggles that role's concurrent jobs (e.g. a vendor serving multiple clients), and represents the node in cross-team coordination.
- **The edges (E)** — typed connections carrying approvals, materials, or data between nodes. Agents negotiate and communicate along edges. Example: the Procurement agent automatically updates the Finance agent on shifting invoice timelines when the Vendor agent reports a delay.

### 1.3 Coordination principle

Each agent optimizes locally, but because agents exchange messages along their edges, a change at one node propagates outward and the system converges toward a globally consistent schedule. A slip at one node surfaces as *renegotiation that ripples through the graph*, rather than as a surprise discovered at the deadline.

---

## 2. Onboarding — extracting the company's DNA

Standing up a workspace begins with a **guided, adaptive AI interview** with the admin (the person deploying the platform for the company). The answers are not stored as prose — they are compiled into the artifacts that define the workspace: node placement, edge definitions, and the system prompt + guardrails for every agent.

The interview is organized into four tiers, each defining one layer of the graph. It asks follow-ups based on prior answers, and can ingest existing data (org-chart CSV, HR export) to pre-fill anything it can rather than asking for it.

### Tier 1 — Macro: defining the graph

| Question | What it generates |
|---|---|
| **Industry & output** — what is the primary product or service you deliver? | Domain context injected into every agent prompt; shared vocabulary across the board |
| **Core operational stages** — break your delivery process into 3–5 major phases | The top-level structure of the graph (clusters / swimlanes) |
| **Bottlenecks** — where does friction, delay, or communication breakdown historically occur? | High-risk edges flagged for extra monitoring; priority alerting at the agents sitting on them |

### Tier 2 — Micro: defining the nodes (actors)

| Question | What it generates |
|---|---|
| **Internal teams** — key departments in the operational lifecycle | Internal nodes |
| **External partners** — outside entities that need access | External nodes (restricted visibility by default) |
| **Capacity & constraints** — per role (e.g. vendors juggle clients; Finance needs 48h to approve) | Each node's constraint model, consumed by its agent for scheduling |
| **People-to-seats** — who fills each role? | Individual employee provisioning (scoped logins) — the layer that makes each person's platform their own |

### Tier 3 — Workflow & dependencies: defining the edges

| Question | What it generates |
|---|---|
| **The trigger** — what action kicks off a new operational cycle? (contract signed, inventory below threshold) | The entry event/edge that instantiates a workflow |
| **Approval chains** — who proposes an action, who approves it, who executes it? | Directed edges with approval semantics |
| **Data handoffs** — when Team A hands to Team B, what documents/data must accompany it? | The required-payload schema on each edge |

### Tier 4 — AI agency & guardrails: defining the agents

| Question | What it generates |
|---|---|
| **Autonomy level** — may the agent auto-approve standard requests, or only draft for human approval? | Per-agent permission setting |
| **External visibility** — how much internal data can an external agent see? (only its assigned deadlines, or your internal ones too?) | Per-agent data-scope / visibility policy |
| **Exception handling** — protocol when a deadline is missed? (auto-renegotiate, alert the human, halt downstream) | Per-agent exception routine |

---

## 3. Generation — from answers to a live workspace

The compiled interview produces a single **graph specification**. That one object drives three things at once: the canvas UI, the database schema, and the initialization of every agent.

### 3.1 Graph specification

A structured object the renderer and backend both consume:

```json
{
  "company": {
    "name": "Acme Custom Furniture",
    "industry": "custom furniture manufacturing",
    "stages": ["sourcing", "assembly", "quality assurance", "distribution"]
  },
  "nodes": [
    {
      "id": "procurement",
      "label": "Procurement",
      "type": "internal",
      "role": "Procurement Manager",
      "constraints": { "notes": "manages multiple concurrent vendors" },
      "agent": {
        "autonomy": "draft_only",
        "visibility": "full_internal",
        "exception_protocol": "alert_human"
      }
    },
    {
      "id": "finance",
      "label": "Finance",
      "type": "internal",
      "role": "Finance Team",
      "constraints": { "approval_sla_hours": 48 },
      "agent": {
        "autonomy": "auto_approve_standard",
        "visibility": "full_internal",
        "exception_protocol": "alert_human"
      }
    },
    {
      "id": "vendor_oak",
      "label": "Oakline Timber",
      "type": "external",
      "role": "Raw material vendor",
      "constraints": { "concurrent_clients": true },
      "agent": {
        "autonomy": "draft_only",
        "visibility": "assigned_deadlines_only",
        "exception_protocol": "auto_renegotiate"
      }
    }
  ],
  "edges": [
    {
      "id": "proc_finance_approval",
      "from": "procurement",
      "to": "finance",
      "type": "approval",
      "trigger": "proposal_submitted",
      "payload": ["purchase_order", "vendor_details"]
    },
    {
      "id": "proc_vendor_order",
      "from": "procurement",
      "to": "vendor_oak",
      "type": "material",
      "trigger": "finance_approved",
      "payload": ["purchase_order", "delivery_deadline"]
    },
    {
      "id": "vendor_proc_status",
      "from": "vendor_oak",
      "to": "procurement",
      "type": "data",
      "trigger": "checkpoint_reached",
      "payload": ["shipment_status", "revised_eta"]
    }
  ]
}
```

### 3.2 Agent initialization

Each node's answers fill a system-prompt template — this is the direct bridge from Tier 4 of the interview to a running agent:

```
You are the AI Chief of Staff for {label} ({role}).
Responsibilities: {responsibilities}.
You coordinate with — upstream: {upstream_nodes}; downstream: {downstream_nodes}.
Artifacts you own: {artifacts}.
Constraints: {constraints}.
Autonomy: {autonomy}.            // draft_only | auto_approve_standard
Data visibility: {visibility}.   // full_internal | assigned_deadlines_only | ...
On exceptions (missed deadline, blocked handoff): {exception_protocol}.

When a neighbouring agent's timeline shifts, update your own plan,
re-balance your role's other active jobs, and notify affected downstream agents.
```

### 3.3 Provisioning

The same spec seeds the database (`nodes`, `edges`, `documents`, `agent_configs`) and generates **each employee's scoped view** — a filter over the graph centered on their node, showing their tasks and deadlines, their upstream/downstream neighbors, and the document templates their edges require. A procurement seat opens to proposals, POs, and its finance/vendor edges; a finance seat opens to approvals and budget context.

---

## 4. Runtime (after generation)

Once live, agents operate continuously on the graph: monitoring their node's state, drafting and routing the artifacts their edges require, managing their role's concurrent jobs, and negotiating along edges when timelines change. The admin can keep editing the canvas at any time; structural changes reconfigure the affected agents.

---

## 5. MVP scope for the hackathon

Keep the demo to the spine that proves the concept:

- **Interview** capped at 5–8 questions → LLM emits the JSON graph spec, constrained to a fixed schema so parsing is reliable.
- **Render** live in React Flow; real-time collaboration via Liveblocks or Yjs.
- **Agents** — one LLM-backed agent per node, with a shared message bus for edge communication.
- **Depth in one place** — fully build out a single node's provisioned view and one live exception scenario (a vendor slips a checkpoint → agents renegotiate → downstream schedules update).

**Demo beat:** *"Describe your company in a sentence, watch its operating graph assemble itself, then watch it re-plan when a vendor slips."*
