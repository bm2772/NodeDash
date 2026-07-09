"""On-demand AMD MI300X (a DigitalOcean GPU Droplet) with a tiered fallback.

Option B: the always-on LLM_* endpoint answers instantly, while this manager wakes
the GPU in the background. Once the GPU's vLLM is healthy, agent calls route to it.
After an idle period the droplet is DESTROYED (on DigitalOcean a powered-off droplet
still bills — only destroying stops the meter), so idle cost is zero.

State machine: off → warming → ready → (idle) → off.

Everything is inert unless settings.gpu_enabled, so local/mock runs are unaffected.
"""
import threading
import time
from typing import Optional

import httpx

from .config import settings

DO_API = "https://api.digitalocean.com/v2"
_PROBE_CACHE_SECONDS = 5.0


class GpuManager:
    def __init__(self) -> None:
        self._state = "off"          # off | warming | ready
        self._droplet_id: Optional[int] = None
        self._base_url: Optional[str] = None   # resolved http://<ip>:<port>/v1 after create
        self._last_activity = time.time()
        self._error: Optional[str] = None
        self._lock = threading.Lock()
        self._probe_at = 0.0
        self._probe_ok = False

    # ------------------------------------------------------------------ #
    def touch(self) -> None:
        self._last_activity = time.time()

    def target_base_url(self) -> str:
        return self._base_url or settings.gpu_base_url

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {settings.gpu_api_key}"} if settings.gpu_api_key else {}

    def _probe(self) -> bool:
        """Is the GPU's vLLM serving? Cached briefly to avoid per-call latency."""
        now = time.time()
        if now - self._probe_at < _PROBE_CACHE_SECONDS:
            return self._probe_ok
        ok = False
        base = self.target_base_url()
        if base:
            try:
                r = httpx.get(f"{base}/models", timeout=settings.gpu_health_timeout, headers=self._auth())
                ok = r.status_code < 400
            except httpx.HTTPError:
                ok = False
        self._probe_at, self._probe_ok = now, ok
        return ok

    def is_ready(self) -> bool:
        """True if agent calls should route to the GPU right now."""
        if not settings.gpu_enabled:
            return False
        if self._probe():
            self._state = "ready"
            return True
        if self._state == "ready":
            self._state = "off"
        return False

    def status(self) -> dict:
        if not settings.gpu_enabled:
            return {"state": "disabled", "gpu_model": None, "fallback_model": settings.llm_model}
        # refresh state via a (cached) probe
        self.is_ready()
        return {
            "state": self._state,
            "gpu_model": settings.gpu_model,
            "fallback_model": settings.llm_model,
            "idle_seconds": int(time.time() - self._last_activity),
            "error": self._error,
        }

    # ------------------------------------------------------------------ #
    def request_wake(self) -> None:
        """Non-blocking: start warming the GPU if it's off. Safe to call every chat."""
        if not settings.gpu_enabled:
            return
        with self._lock:
            if self._state != "off":
                return
            self._state = "warming"
            self._error = None
        threading.Thread(target=self._wake_worker, daemon=True).start()

    def _wake_worker(self) -> None:
        try:
            if self._probe():                 # already up (fixed endpoint / pre-warmed)
                self._state = "ready"
                return
            self._droplet_id, ip = self._create_droplet()
            self._base_url = f"http://{ip}:{settings.gpu_vllm_port}/v1"
            deadline = time.time() + settings.gpu_warm_timeout
            while time.time() < deadline:
                self._probe_at = 0.0          # bypass cache while waiting
                if self._probe():
                    self._state = "ready"
                    self.touch()
                    return
                time.sleep(5)
            self._error = "warm timeout — GPU did not become healthy"
            self._state = "off"
        except Exception as exc:  # noqa: BLE001
            self._error = f"wake failed: {exc}"
            self._state = "off"

    def reap_if_idle(self) -> None:
        """Destroy the droplet after the idle window to stop billing."""
        if not settings.gpu_enabled or self._state != "ready" or not self._droplet_id:
            return
        if time.time() - self._last_activity > settings.gpu_idle_minutes * 60:
            try:
                self._destroy_droplet(self._droplet_id)
            finally:
                self._droplet_id = None
                self._base_url = None
                self._state = "off"

    # ------------------------------------------------------------------ #
    # DigitalOcean droplet lifecycle
    # ------------------------------------------------------------------ #
    def _do_headers(self) -> dict:
        if not settings.do_api_token:
            raise RuntimeError("DO_API_TOKEN not configured")
        return {"Authorization": f"Bearer {settings.do_api_token}", "Content-Type": "application/json"}

    def _create_droplet(self) -> tuple[int, str]:
        """Create a GPU droplet from the prebaked snapshot; return (id, public_ip)."""
        if not settings.do_gpu_snapshot_id:
            raise RuntimeError("DO_GPU_SNAPSHOT_ID not configured (bake ROCm+vLLM+weights)")
        body = {
            "name": settings.do_gpu_name,
            "region": settings.do_region,
            "size": settings.do_gpu_size,
            "image": int(settings.do_gpu_snapshot_id) if settings.do_gpu_snapshot_id.isdigit()
            else settings.do_gpu_snapshot_id,
            "tags": ["nodedash-gpu"],
        }
        if settings.do_ssh_key_ids:
            body["ssh_keys"] = settings.do_ssh_key_ids
        r = httpx.post(f"{DO_API}/droplets", json=body, headers=self._do_headers(), timeout=30)
        r.raise_for_status()
        did = r.json()["droplet"]["id"]
        # poll for the assigned public IP
        deadline = time.time() + 180
        while time.time() < deadline:
            time.sleep(5)
            d = httpx.get(f"{DO_API}/droplets/{did}", headers=self._do_headers(), timeout=30).json()["droplet"]
            for net in d.get("networks", {}).get("v4", []):
                if net.get("type") == "public":
                    return did, net["ip_address"]
        raise RuntimeError("droplet created but no public IP assigned in time")

    def _destroy_droplet(self, droplet_id: int) -> None:
        httpx.delete(f"{DO_API}/droplets/{droplet_id}", headers=self._do_headers(), timeout=30)


manager = GpuManager()


def start_idle_reaper() -> None:
    """Background loop that reaps the GPU when idle. Started from the app lifespan."""
    def _loop():
        while True:
            time.sleep(60)
            try:
                manager.reap_if_idle()
            except Exception:  # noqa: BLE001
                pass
    if settings.gpu_manage:
        threading.Thread(target=_loop, daemon=True).start()
