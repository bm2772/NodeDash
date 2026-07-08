import { api, getApiBase, setApiBase } from "./api.js";
import { ForceGraph } from "./graph.js";

const appEl = document.getElementById("app");

const state = {
  view: "start",
  sessionId: null,
  currentQuestion: null,
  progress: { answered: 0, total: 15 },
  workspaceId: null,
  adminToken: null,
  workspace: null,
  graphNodes: [],
  graphEdges: [],
  nodeAccess: {},   // node_key -> { access_code, name, type }
  tabs: [],         // { node_key, name, type, token, data, chat: [] }
  activeTab: null,
  fg: null,
};

const DEMO_ANSWERS = {
  q_industry_output: "Custom Furniture Manufacturing",
  q_global_objective: "Deliver custom furniture within 14 days.",
  q_operational_stages: "sourcing, assembly, quality assurance, distribution",
  q_bottlenecks: "vendor delays on raw materials",
  q_internal_teams: "Procurement, Finance, Assembly",
  q_external_partners: "Oakline Timber",
  q_capacity_constraints: "Finance needs 48h to approve; vendors juggle multiple clients",
  q_people_to_seats: "alice@acme.test, bob@acme.test",
  q_trigger: "New Client Contract Signed",
  q_approval_chains: "Procurement proposes, Finance approves, Vendor executes",
  q_data_handoffs: "Purchase Order, Vendor Details",
  q_autonomy_level: "Finance can execute standard; Procurement suggests only",
  q_external_visibility: "strict isolation - only assigned deadlines",
  q_exception_handling: "auto-renegotiate then alert the human",
  q_communication_tone: "professional and concise",
};

// --------------------------------------------------------------------------- //
// helpers
// --------------------------------------------------------------------------- //
const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
const pretty = (o) => (typeof o === "string" ? o : JSON.stringify(o, null, 2));

function showLoading(msg, sub) {
  hideLoading();
  const el = document.createElement("div");
  el.className = "loading-overlay";
  el.id = "loading-root";
  el.innerHTML = `<div class="spinner"></div><div>${esc(msg)}</div>${
    sub ? `<div class="muted">${esc(sub)}</div>` : ""
  }`;
  document.body.appendChild(el);
}
function hideLoading() {
  document.getElementById("loading-root")?.remove();
}

function normalizeGraph(raw) {
  return {
    workspace: raw.workspace,
    nodes: (raw.nodes || []).map((n) => ({
      id: n.node_id || n.node_key,
      name: n.name,
      type: n.type,
    })),
    edges: (raw.edges || []).map((e) => ({
      source: e.source_node_id,
      target: e.target_node_id,
      action_type: e.action_type,
    })),
  };
}

// --------------------------------------------------------------------------- //
// START view
// --------------------------------------------------------------------------- //
function renderStart() {
  state.fg?.destroy();
  state.fg = null;
  appEl.innerHTML = `
    <div class="center-wrap">
      <div class="card">
        <div class="brand"><div class="dot"></div><h1>NodeDash</h1></div>
        
        <div class="tabs" style="display:flex;gap:12px;margin-bottom:20px;border-bottom:1px solid var(--border);padding-bottom:12px;">
          <button class="ghost ${!localStorage.getItem("nd_has_workspace") ? 'active' : ''}" id="tab-new">New Workspace</button>
          <button class="ghost ${localStorage.getItem("nd_has_workspace") ? 'active' : ''}" id="tab-emp">Employee Login</button>
          <button class="ghost" id="tab-admin">Admin Login</button>
        </div>
        
        <div id="pane-new" style="${localStorage.getItem("nd_has_workspace") ? 'display:none;' : ''}">
          <div class="subtitle">Describe your company in a short interview to generate an operating graph.</div>
          <label>Backend URL</label>
          <input id="s-api" value="${esc(getApiBase())}" />
          <div class="row">
            <div><label>Admin email</label><input id="s-email" value="admin@acme.test" /></div>
            <div><label>Admin password</label><input id="s-pass" type="password" value="admin123" /></div>
          </div>
          <div class="actions">
            <button class="primary" id="s-begin">Begin interview</button>
            <button id="s-demo">⚡ Quick demo</button>
          </div>
          <div class="muted" style="margin-top:14px">Quick demo auto-answers the interview and generates the graph instantly.</div>
        </div>

        <div id="pane-emp" style="${!localStorage.getItem("nd_has_workspace") ? 'display:none;' : ''}">
          <div class="subtitle">Log in to your department to view your organizational dependencies.</div>
          <div class="row">
            <div><label>Employee Email</label><input id="e-email" placeholder="you@acme.test" /></div>
            <div><label>Password</label><input id="e-pass" type="password" placeholder="••••••••" /></div>
          </div>
          <div class="actions">
            <button class="primary" id="e-login">Login as Employee</button>
          </div>
        </div>

        <div id="pane-admin" style="display:none;">
          <div class="subtitle">Log in to an existing workspace with your admin credentials.</div>
          <div class="row">
            <div><label>Admin email</label><input id="a-email" value="admin@acme.test" /></div>
            <div><label>Admin password</label><input id="a-pass" type="password" value="admin123" /></div>
          </div>
          <div class="actions">
            <button class="primary" id="a-login">Login as Admin</button>
          </div>
        </div>

        <div class="error" id="s-err"></div>
      </div>
    </div>`;

  const err = document.getElementById("s-err");
  
  // Tab switching logic
  const tabs = ["new", "emp", "admin"];
  tabs.forEach(t => {
    const btn = document.getElementById(`tab-${t}`);
    if (!btn) return;
    btn.onclick = () => {
      tabs.forEach(x => {
        const b = document.getElementById(`tab-${x}`);
        const p = document.getElementById(`pane-${x}`);
        if (b) b.classList.toggle("active", x === t);
        if (p) p.style.display = (x === t) ? "block" : "none";
      });
      err.textContent = "";
    };
  });

  const readCreds = () => {
    const apiBase = document.getElementById("s-api");
    if (apiBase) setApiBase(apiBase.value.trim());
    return {
      email: document.getElementById("s-email").value.trim(),
      password: document.getElementById("s-pass").value,
    };
  };

  document.getElementById("s-begin").onclick = async () => {
    const { email, password } = readCreds();
    err.textContent = "";
    try {
      const r = await api.startInterview(email, password);
      state.sessionId = r.session_id;
      state.currentQuestion = r.next_question;
      state.progress = { answered: 0, total: r.total_questions };
      state.view = "interview";
      render();
    } catch (e) {
      err.textContent = e.message;
    }
  };

  document.getElementById("s-demo").onclick = async () => {
    const { password } = readCreds();
    const email = `admin+${Date.now().toString(36)}@acme.test`;
    err.textContent = "";
    showLoading("Running the demo interview…", "answering 15 questions");
    try {
      const r = await api.startInterview(email, password);
      state.sessionId = r.session_id;
      for (const [qid, ans] of Object.entries(DEMO_ANSWERS)) {
        await api.answer(state.sessionId, qid, ans);
      }
      await doGenerate();
    } catch (e) {
      hideLoading();
      err.textContent = e.message;
    }
  };

  document.getElementById("a-login").onclick = async () => {
    err.textContent = "";
    showLoading("Logging in...", "");
    try {
      const email = document.getElementById("a-email").value.trim();
      const password = document.getElementById("a-pass").value;
      const r = await api.login(email, password);
      localStorage.setItem("nd_has_workspace", "true");
      state.adminToken = r.access_token;
      state.workspaceId = r.workspace_id;
      const g = normalizeGraph(await api.fullGraph(r.workspace_id, r.access_token));
      state.workspace = g.workspace;
      state.graphNodes = g.nodes;
      state.graphEdges = g.edges;
      state.nodeAccess = {};
      state.tabs = [];
      state.activeTab = null;
      state.view = "graph";
      hideLoading();
      render();
    } catch (e) {
      hideLoading();
      err.textContent = e.message;
    }
  };

  const btnEmpLogin = document.getElementById("e-login");
  if (btnEmpLogin) {
    btnEmpLogin.onclick = async () => {
      err.textContent = "";
      showLoading("Logging in...", "");
      try {
        const email = document.getElementById("e-email").value.trim();
        const password = document.getElementById("e-pass").value;
        const r = await api.login(email, password);
        localStorage.setItem("nd_has_workspace", "true");
        state.workspaceId = r.workspace_id;
        state.adminToken = null; // Ensure not admin
        state.employeeToken = r.access_token;
        state.employeeNodeKey = r.node_key;
        
        const g = normalizeGraph(await api.publicGraph(r.workspace_id));
        state.workspace = g.workspace;
        state.graphNodes = g.nodes;
        state.graphEdges = g.edges;
        state.nodeAccess = {};
        state.tabs = [];
        state.activeTab = null;
        state.view = "graph";
        hideLoading();
        render();
      } catch (e) {
        hideLoading();
        err.textContent = e.message;
      }
    };
  }
}

// --------------------------------------------------------------------------- //
// INTERVIEW view
// --------------------------------------------------------------------------- //
function renderInterview() {
  const q = state.currentQuestion;
  const pct = Math.round((state.progress.answered / state.progress.total) * 100);
  const complete = !q;

  appEl.innerHTML = `
    <div class="center-wrap">
      <div class="card">
        <div class="brand"><div class="dot"></div><h1>NodeDash</h1></div>
        <div class="progress"><div style="width:${pct}%"></div></div>
        <div class="muted" style="margin-bottom:18px">${state.progress.answered} / ${state.progress.total} answered</div>
        ${
          complete
            ? `<div class="q-text">All set.</div>
               <div class="subtitle">Your answers are ready to compile into a company graph.</div>
               <div class="actions"><button class="primary" id="i-generate">Generate workspace →</button></div>`
            : `<div class="tier-tag">${esc(q.tier_title || "")}</div>
               <div class="q-text">${esc(q.question)}</div>
               <div class="q-generates">Generates: ${esc(q.generates || "")}</div>
               ${
                 q.allowed_values
                   ? `<div class="chips" id="i-chips">${q.allowed_values
                       .map((v) => `<span class="chip" data-v="${esc(v)}">${esc(v)}</span>`)
                       .join("")}</div>`
                   : ""
               }
               <label>Your answer</label>
               <textarea id="i-answer" placeholder="Type your answer…"></textarea>
               <div class="actions"><button class="primary" id="i-next">Submit answer →</button></div>`
        }
        <div class="error" id="i-err"></div>
      </div>
    </div>`;

  const err = document.getElementById("i-err");

  if (complete) {
    document.getElementById("i-generate").onclick = () => doGenerate();
    return;
  }

  const ta = document.getElementById("i-answer");
  ta.focus();
  document.querySelectorAll("#i-chips .chip").forEach((c) => {
    c.onclick = () => {
      ta.value = c.dataset.v;
      document.querySelectorAll("#i-chips .chip").forEach((x) => x.classList.remove("active"));
      c.classList.add("active");
    };
  });

  document.getElementById("i-next").onclick = async () => {
    const answer = ta.value.trim();
    if (!answer) { err.textContent = "Please enter an answer."; return; }
    err.textContent = "";
    try {
      const r = await api.answer(state.sessionId, q.question_id, answer);
      state.progress = r.progress;
      state.currentQuestion = r.next_question;
      render();
    } catch (e) {
      err.textContent = e.message;
    }
  };
}

async function doGenerate() {
  showLoading("Compiling your company graph…", "nodes · edges · agent guardrails");
  try {
    const r = await api.generate(state.sessionId);
    const g = normalizeGraph(r.graph);
    localStorage.setItem("nd_has_workspace", "true");
    state.workspaceId = r.workspace_id;
    state.adminToken = r.admin_token;
    state.workspace = g.workspace;
    state.graphNodes = g.nodes;
    state.graphEdges = g.edges;
    state.nodeAccess = {};
    (r.node_access || []).forEach((n) => {
      state.nodeAccess[n.node_key] = { access_code: n.access_code, name: n.name, type: n.type };
    });
    state.tabs = [];
    state.activeTab = null;
    state.view = "graph";
    hideLoading();
    render();
  } catch (e) {
    hideLoading();
    alert("Generation failed: " + e.message);
  }
}

// --------------------------------------------------------------------------- //
// GRAPH view (Obsidian-style)
// --------------------------------------------------------------------------- //
function renderGraph() {
  const ws = state.workspace || {};
  appEl.innerHTML = `
    <div class="topbar" style="position: relative;">
      <div class="legend">
        <span><i style="background:#5c6bc0"></i> Internal</span>
        <span><i style="background:#66bb6a"></i> External</span>
      </div>
      
      <div style="position: absolute; left: 50%; transform: translateX(-50%); display: flex; align-items: center;">
        <span class="ws-name">${esc(ws.workspace_name || "Workspace")}</span>
      </div>

      <div class="spacer"></div>
      <button id="g-new" class="ghost">New workspace</button>
    </div>
    <div class="stage">
      <canvas id="graph-canvas"></canvas>
      ${state.adminToken ? `
      <div class="admin-controls" style="position:absolute; bottom:20px; right:20px; display:flex; gap:10px; z-index: 10;">
        <button class="primary" id="g-add-node">+ Add Node</button>
        <button class="primary" id="g-add-edge">+ Add Edge</button>
      </div>` : ""}
      <div class="hint">Drag to pan · scroll to zoom · click a department to open it</div>
      <div id="modal-root"></div>
      <div id="dept-root"></div>
    </div>`;

  document.getElementById("g-new").onclick = () => {
    localStorage.removeItem("nd_has_workspace");
    state.view = "start";
    render();
  };
  
  if (state.adminToken) {
    const an = document.getElementById("g-add-node");
    const ae = document.getElementById("g-add-edge");
    if (an) an.onclick = openAddNodeModal;
    if (ae) ae.onclick = openAddEdgeModal;
  }

  const canvas = document.getElementById("graph-canvas");
  state.fg = new ForceGraph(canvas, { onNodeClick: openLogin });
  let nodes = state.graphNodes || [];
  let edges = state.graphEdges || [];
  if (!state.adminToken && state.employeeNodeKey) {
    const key = state.employeeNodeKey;
    const validEdges = edges.filter(e => e.source === key || e.target === key);
    const validNodes = new Set([key]);
    validEdges.forEach(e => { validNodes.add(e.source); validNodes.add(e.target); });
    nodes = nodes.filter(n => validNodes.has(n.id));
    edges = validEdges;
  }
  state.fg.setData(nodes, edges);
  state.fg.start();
  window.__fg = state.fg;  // debug hook: inspect/drive the graph from the console

  renderDeptPanel();
}

// --------------------------------------------------------------------------- //
// Node login modal
// --------------------------------------------------------------------------- //
function openLogin(node) {
  if (state.adminToken) {
    return openDept(node, state.adminToken);
  }
  if (state.employeeNodeKey === node.id) {
    return openDept(node, state.employeeToken);
  }
  
  // If employee clicks a node they don't own
  const root = document.getElementById("modal-root");
  root.innerHTML = `
    <div class="modal-backdrop" id="m-backdrop">
      <div class="modal">
        <h3>Access Denied</h3>
        <div class="subtitle" style="margin:6px 0 4px">You do not have permission to view the internal data for ${esc(node.name)}.</div>
        <div class="actions">
          <button class="ghost" id="m-cancel">Close</button>
        </div>
      </div>
    </div>`;

  document.getElementById("m-backdrop").onclick = (e) => {
    if (e.target.id === "m-backdrop") closeModal();
  };
  document.getElementById("m-cancel").onclick = closeModal;
}

function closeModal() {
  const root = document.getElementById("modal-root");
  if (root) root.innerHTML = "";
}

// --------------------------------------------------------------------------- //
// Department tabs
// --------------------------------------------------------------------------- //
async function openDept(node, token) {
  const err = document.getElementById("m-err");
  try {
    let tab = state.tabs.find((t) => t.node_key === node.id);
    if (!tab) {
      const data = await api.nodeWindow(state.workspaceId, node.id, token);
      tab = { node_key: node.id, name: node.name, type: node.type, token, data, chat: [] };
      state.tabs.push(tab);
    }
    state.activeTab = node.id;
    closeModal();
    renderDeptPanel();
  } catch (e) {
    if (err) err.textContent = e.message;
  }
}

function closeTab(nodeKey) {
  state.tabs = state.tabs.filter((t) => t.node_key !== nodeKey);
  if (state.activeTab === nodeKey) state.activeTab = state.tabs.at(-1)?.node_key || null;
  renderDeptPanel();
}

function renderDeptPanel() {
  const root = document.getElementById("dept-root");
  if (!root) return;
  if (!state.tabs.length) { root.innerHTML = ""; return; }
  const active = state.tabs.find((t) => t.node_key === state.activeTab) || state.tabs[0];

  root.innerHTML = `
    <div class="dept-panel">
      <div class="tabstrip">
        ${state.tabs
          .map(
            (t) => `<div class="tab ${t.node_key === active.node_key ? "active" : ""}" data-k="${esc(t.node_key)}">
              <span>${esc(t.name)}</span>
              <button class="x" data-close="${esc(t.node_key)}">×</button>
            </div>`
          )
          .join("")}
        <button class="ghost panel-close" id="d-closeall">✕ Close</button>
      </div>
      <div class="dept-body">${deptBodyHTML(active)}</div>
    </div>`;

  root.querySelectorAll(".tab").forEach((el) => {
    el.onclick = (e) => {
      if (e.target.dataset.close !== undefined) return;
      state.activeTab = el.dataset.k;
      renderDeptPanel();
    };
  });
  root.querySelectorAll("[data-close]").forEach((b) => {
    b.onclick = (e) => { e.stopPropagation(); closeTab(b.dataset.close); };
  });
  document.getElementById("d-closeall").onclick = () => {
    state.tabs = [];
    state.activeTab = null;
    renderDeptPanel();
  };
  wireChat(active);
  
  if (state.adminToken) {
    const btnAddEmp = document.getElementById("d-add-emp");
    if (btnAddEmp) btnAddEmp.onclick = () => openAddEmployeeModal(active.node_key, active.name);
  }
}

function deptBodyHTML(tab) {
  const d = tab.data;
  const node = d.node;
  const g = d.guardrails || {};
  const nb = d.neighbours || { upstream: [], downstream: [] };

  const pills = (arr, empty) =>
    arr && arr.length
      ? `<div class="pill-list">${arr.map((x) => `<span class="pill">${esc(x)}</span>`).join("")}</div>`
      : `<div class="muted">${esc(empty)}</div>`;

  const neigh = (list, dir) =>
    list.length
      ? list
          .map(
            (n) => `<div class="neighbour">
              <span class="arrow">${dir === "down" ? "→" : "←"}</span>
              <strong>${esc(n.name || n.node_key)}</strong>
              <span class="muted">${esc(n.action_type)} · ${esc((n.required_data_payload || []).join(", "))}</span>
            </div>`
          )
          .join("")
      : `<div class="muted">none</div>`;

  const formatDocContent = (content) => {
    if (typeof content !== "object" || content === null) {
      return `<pre style="margin-top:8px">${esc(String(content))}</pre>`;
    }
    return `<div class="doc-props" style="display:flex;flex-direction:column;gap:6px;margin-top:8px;font-size:13px;font-family:'JetBrains Mono',monospace;">
      ${Object.entries(content).map(([k, v]) => `
        <div class="doc-prop" style="background:var(--bg);padding:8px 10px;border-radius:4px;border:1px solid var(--border);display:flex;flex-direction:column;">
          <strong style="color:#a5b4fc;margin-bottom:4px;">${esc(k)}</strong>
          <span style="color:var(--fg);white-space:pre-wrap;">${esc(typeof v === "object" ? JSON.stringify(v, null, 2) : String(v))}</span>
        </div>
      `).join("")}
    </div>`;
  };

  const docs = (d.documents || [])
    .map(
      (doc) => `<div class="doc-card">
        <div class="doc-title"><span>${esc(doc.title)}</span><span class="doc-type">${esc(doc.doc_type)}</span></div>
        ${formatDocContent(doc.content)}
      </div>`
    )
    .join("");

  const chatLog = tab.chat
    .map((m) => `<div class="msg ${esc(m.role)}">${esc(m.text)}</div>`)
    .join("");

  return `
    <div class="dept-header">
      <h2>${esc(node.name)}</h2>
      <div style="display:flex;gap:8px;align-items:center;">
        <span class="node-type ${esc(node.type)}">${esc(node.type)}</span>
        ${state.adminToken ? `<button class="ghost" id="d-add-emp" style="padding:2px 8px;font-size:12px;">+ Employee</button>` : ""}
      </div>
    </div>
    <div class="dept-sub">Autonomy: <strong>${esc(node.autonomy_level)}</strong> ·
      tone: ${esc(g.communication_tone || "—")} · delay policy: ${esc(g.delay_handling_protocol || "—")}</div>

    <div class="section-title">Responsibilities</div>
    ${pills(node.responsibilities, "—")}

    <div class="section-title">Constraints</div>
    ${pills(node.constraints, "none recorded")}

    <div class="section-title">Workflows</div>
    ${neigh(nb.upstream, "up")}
    ${neigh(nb.downstream, "down")}

    <div class="section-title">Documents (${(d.documents || []).length})</div>
    ${docs || `<div class="muted">no documents</div>`}

    <div class="section-title">AI Chief of Staff</div>
    <div class="prompt-box">${esc(node.agent_system_prompt)}</div>
    <div class="chat">
      <div class="chat-log" id="chat-log">${chatLog}</div>
      <label style="display:flex;align-items:center;gap:8px;margin:6px 0 0;font-size:12px">
        <input type="checkbox" id="chat-handoffs" style="width:auto" /> emit handoffs to downstream nodes
      </label>
      <div class="chat-input">
        <input id="chat-in" placeholder="Ask this department's agent…" />
        <button class="primary" id="chat-send">Send</button>
      </div>
    </div>`;
}

function wireChat(tab) {
  const input = document.getElementById("chat-in");
  const send = document.getElementById("chat-send");
  const log = document.getElementById("chat-log");
  if (!input || !send) return;

  const doSend = async () => {
    const text = input.value.trim();
    if (!text) return;
    const emit = document.getElementById("chat-handoffs").checked;
    input.value = "";
    tab.chat.push({ role: "user", text });
    log.innerHTML += `<div class="msg user">${esc(text)}</div>`;
    log.scrollTop = log.scrollHeight;
    const thinking = document.createElement("div");
    thinking.className = "msg agent";
    thinking.innerHTML = `<span class="spinner"></span>`;
    log.appendChild(thinking);
    try {
      const r = await api.invokeAgent(state.workspaceId, tab.node_key, tab.token, text, emit);
      thinking.remove();
      const reply = r.reply.body;
      tab.chat.push({ role: "agent", text: reply });
      log.innerHTML += `<div class="msg agent">${esc(reply)}</div>`;
      (r.handoffs || []).forEach((h) => {
        tab.chat.push({ role: "handoff", text: `↪ ${h.action_type} → ${h.to}` });
        log.innerHTML += `<div class="msg handoff">↪ ${esc(h.action_type)} → ${esc(h.to)}</div>`;
      });
      log.scrollTop = log.scrollHeight;
    } catch (e) {
      thinking.remove();
      log.innerHTML += `<div class="msg handoff">error: ${esc(e.message)}</div>`;
    }
  };

  send.onclick = doSend;
  input.onkeydown = (e) => { if (e.key === "Enter") doSend(); };
}

// --------------------------------------------------------------------------- //
// Admin Modals
// --------------------------------------------------------------------------- //
function openAddEmployeeModal(nodeKey, nodeName) {
  const root = document.getElementById("modal-root");
  root.innerHTML = `
    <div class="modal-backdrop" id="m-backdrop">
      <div class="modal">
        <h3>Add Employee to ${esc(nodeName)}</h3>
        <label>Employee Email</label>
        <input id="me-email" placeholder="emp@acme.test" />
        <label>Password</label>
        <input id="me-pass" type="password" />
        <div class="error" id="me-err"></div>
        <div class="actions">
          <button class="ghost" id="me-cancel">Cancel</button>
          <button class="primary" id="me-enter">Add</button>
        </div>
      </div>
    </div>`;
  
  document.getElementById("me-cancel").onclick = closeModal;
  document.getElementById("m-backdrop").onclick = (e) => { if (e.target.id === "m-backdrop") closeModal(); };
  document.getElementById("me-enter").onclick = async () => {
    const err = document.getElementById("me-err");
    try {
      const email = document.getElementById("me-email").value.trim();
      const pass = document.getElementById("me-pass").value;
      await api.addEmployee(state.workspaceId, nodeKey, state.adminToken, email, pass);
      closeModal();
      alert("Employee added successfully!");
    } catch(e) { err.textContent = e.message; }
  };
}

function openAddNodeModal() {
  const root = document.getElementById("modal-root");
  root.innerHTML = `
    <div class="modal-backdrop" id="m-backdrop">
      <div class="modal">
        <h3>Add Node</h3>
        <label>Name</label>
        <input id="mn-name" placeholder="e.g. QA Team" />
        <label>Type</label>
        <select id="mn-type"><option value="internal">internal</option><option value="external">external</option></select>
        <label>Responsibilities (comma separated)</label>
        <input id="mn-resp" placeholder="test software, report bugs" />
        <div class="error" id="mn-err"></div>
        <div class="actions">
          <button class="ghost" id="mn-cancel">Cancel</button>
          <button class="primary" id="mn-enter">Add</button>
        </div>
      </div>
    </div>`;

  document.getElementById("mn-cancel").onclick = closeModal;
  document.getElementById("m-backdrop").onclick = (e) => { if (e.target.id === "m-backdrop") closeModal(); };
  document.getElementById("mn-enter").onclick = async () => {
    const err = document.getElementById("mn-err");
    try {
      const name = document.getElementById("mn-name").value.trim();
      const type = document.getElementById("mn-type").value;
      const resp = document.getElementById("mn-resp").value.split(",").map(s=>s.trim()).filter(Boolean);
      await api.addNode(state.workspaceId, state.adminToken, { name, type, responsibilities: resp });
      closeModal();
      await refreshAdminGraph();
    } catch(e) { err.textContent = e.message; }
  };
}

function openAddEdgeModal() {
  const nodes = state.graphNodes || [];
  const options = nodes.map(n => `<option value="${esc(n.id)}">${esc(n.name)}</option>`).join("");
  const root = document.getElementById("modal-root");
  root.innerHTML = `
    <div class="modal-backdrop" id="m-backdrop">
      <div class="modal">
        <h3>Add Edge</h3>
        <label>Source Node</label>
        <select id="me-src">${options}</select>
        <label>Target Node</label>
        <select id="me-tgt">${options}</select>
        <label>Action Type</label>
        <input id="me-action" placeholder="e.g. approve_budget" />
        <div class="error" id="me-err"></div>
        <div class="actions">
          <button class="ghost" id="me-cancel">Cancel</button>
          <button class="primary" id="me-enter">Add</button>
        </div>
      </div>
    </div>`;

  document.getElementById("me-cancel").onclick = closeModal;
  document.getElementById("m-backdrop").onclick = (e) => { if (e.target.id === "m-backdrop") closeModal(); };
  document.getElementById("me-enter").onclick = async () => {
    const err = document.getElementById("me-err");
    try {
      const src = document.getElementById("me-src").value;
      const tgt = document.getElementById("me-tgt").value;
      const action = document.getElementById("me-action").value.trim();
      await api.addEdge(state.workspaceId, state.adminToken, { source_node_key: src, target_node_key: tgt, action_type: action });
      closeModal();
      await refreshAdminGraph();
    } catch(e) { err.textContent = e.message; }
  };
}

async function refreshAdminGraph() {
  showLoading("Refreshing graph...", "");
  try {
    const g = normalizeGraph(await api.fullGraph(state.workspaceId, state.adminToken));
    state.workspace = g.workspace;
    state.graphNodes = g.nodes;
    state.graphEdges = g.edges;
    state.view = "graph";
    hideLoading();
    render();
  } catch(e) {
    hideLoading();
    alert("Failed to refresh: " + e.message);
  }
}

// --------------------------------------------------------------------------- //
// router
// --------------------------------------------------------------------------- //
function render() {
  if (state.view === "start") renderStart();
  else if (state.view === "interview") renderInterview();
  else if (state.view === "graph") renderGraph();
}

render();
