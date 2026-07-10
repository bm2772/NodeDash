// Deployment config, loaded before the app.
// When the frontend and backend are on different hosts (e.g. served over Cloudflare
// tunnels), set this to the backend's URL:
//   window.__ND_API_BASE__ = "https://<backend-tunnel>.trycloudflare.com";
// Leave empty for local/same-host (defaults to http://<host>:8000). The start screen's
// "Backend URL" field still overrides this at runtime (stored in localStorage).
window.__ND_API_BASE__ = "";
