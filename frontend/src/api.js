// Thin fetch wrapper around the NodeDash FastAPI backend.

const DEFAULT_BASE = `${location.protocol}//${location.hostname || "localhost"}:8000`;

export function getApiBase() {
  // priority: user override (localStorage) → deploy config (config.js) → local default
  return localStorage.getItem("nd_api_base") || window.__ND_API_BASE__ || DEFAULT_BASE;
}
export function setApiBase(url) {
  localStorage.setItem("nd_api_base", url.replace(/\/+$/, ""));
}

async function req(method, path, { body, token, _retries = 2 } = {}) {
  // Only set Content-Type when there is a body — a bodyless POST with no custom
  // headers is a "simple" CORS request and skips the preflight entirely.
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let resp;
  try {
    resp = await fetch(getApiBase() + path, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    // Transient network blip — retry, but only for idempotent GETs so we never
    // duplicate a side effect (e.g. creating two workspaces).
    if (_retries > 0 && method === "GET") {
      await new Promise((r) => setTimeout(r, 300));
      return req(method, path, { body, token, _retries: _retries - 1 });
    }
    throw new Error(`Cannot reach backend at ${getApiBase()} — is it running?`);
  }
  let data = null;
  const text = await resp.text();
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }
  if (!resp.ok) {
    const detail = data && data.detail !== undefined ? data.detail : data;
    const msg = typeof detail === "string" ? detail : JSON.stringify(detail);
    throw new Error(msg || `${resp.status} ${resp.statusText}`);
  }
  return data;
}

export const api = {
  health: () => req("GET", "/health"),

  // Interview
  questionnaire: () => req("GET", "/interview/questionnaire"),
  startInterview: (admin_email, admin_password) =>
    req("POST", "/interview/start", { body: { admin_email, admin_password } }),
  getSession: (id) => req("GET", `/interview/${id}`),
  answer: (id, question_id, answer) =>
    req("POST", `/interview/${id}/answer`, { body: { question_id, answer } }),
  generate: (id) => req("POST", `/interview/${id}/generate`),

  // Workspace / graph
  publicGraph: (wsId) => req("GET", `/workspace/${wsId}/public`),
  fullGraph: (wsId, token) => req("GET", `/workspace/${wsId}/graph`, { token }),

  // Auth
  login: (email, password) => req("POST", "/auth/login", { body: { email, password } }),
  nodeLogin: (workspace_id, node_key, access_code, email, password) =>
    req("POST", "/auth/node-login", {
      body: { workspace_id, node_key, access_code, email, password },
    }),

  // Node window (scoped)
  nodeWindow: (wsId, nodeKey, token) =>
    req("GET", `/workspace/${wsId}/nodes/${nodeKey}`, { token }),
  invokeAgent: (wsId, nodeKey, token, message, emit_handoffs = false) =>
    req("POST", `/workspace/${wsId}/nodes/${nodeKey}/agent/invoke`, {
      token,
      body: { message, emit_handoffs },
    }),

  // Admin Actions
  addNode: (wsId, token, data) => req("POST", `/workspace/${wsId}/nodes`, { token, body: data }),
  addEdge: (wsId, token, data) => req("POST", `/workspace/${wsId}/edges`, { token, body: data }),
  addEmployee: (wsId, nodeKey, token, email, password) =>
    req("POST", `/workspace/${wsId}/nodes/${nodeKey}/users`, { token, body: { email, password } }),
};
