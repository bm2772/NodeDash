# NodeDash — Frontend

A **zero-build** single-page app (vanilla JS + Canvas, no Node/npm). Serve it with any
static server and it drives the [backend](../backend): admin interview → Obsidian-style
company graph → login-gated department windows with live agent chat.

## Run it

The backend must be running first (see [../backend/README.md](../backend/README.md)).

```bash
cd frontend
python3 -m http.server 5173
# open http://localhost:5173
```

The backend URL defaults to `http://<host>:8000` and is editable on the start screen
(stored in `localStorage`).

## The flow

1. **Start** — New Workspace (admin interview or **⚡ Quick demo**), Employee Login, or Admin Login.
2. **Interview** — one question per screen, tier by tier, sourced from the backend's `questions.json`.
3. **Graph** — the compiled workspace as a force-directed graph: departments are glowing dots (internal vs external), workflows are edges. Drag to pan, scroll to zoom, drag a dot to reposition, hover to highlight.
4. **Node window** — click a dot → log in (access code for a scoped seat, or Open as admin) → the department opens as a **tab**; open several and they dock.
5. **Department tab** — responsibilities, constraints, workflows (upstream/downstream + payloads), documents, the **AI Chief of Staff** system prompt, and a live agent chat.
6. **RAG recall** — when the agent reuses a similar past exchange, the chat shows a *"↳ recalled N past exchanges"* chip; hover it for the matched questions and similarity scores.

## Files

| File | Role |
|---|---|
| `index.html` | Shell; loads `src/app.js` as an ES module |
| `styles.css` | Dark theme |
| `src/api.js` | Fetch wrapper for the backend (base URL, retries idempotent GETs) |
| `src/graph.js` | `ForceGraph` — hand-rolled Canvas physics + pan/zoom/drag/hover |
| `src/app.js` | Views (start / interview / graph), login modal, department tabs, agent chat + memory recall |

## Notes

- Access codes are pre-filled in the login modal **for the demo**; in production the admin distributes each node's code.
- Access control is enforced server-side: a seat token is scoped to one node, so a Finance member is 403'd from any other node's window (admins see all).
- `window.__fg` exposes the running graph instance for console debugging.
