"""Environment-driven settings. No pydantic-settings dependency — plain os.environ."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent      # backend/
REPO_ROOT = BASE_DIR.parent                            # NodeDash/


def _path(env_key: str, default: Path) -> Path:
    return Path(os.getenv(env_key, str(default)))


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no python-dotenv dependency). Real environment
    variables and anything on the command line take precedence via setdefault."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / ".env")


class Settings:
    def __init__(self) -> None:
        # Auth
        self.jwt_secret = os.getenv("JWT_SECRET", "dev-secret-change-me")
        self.jwt_exp_hours = int(os.getenv("JWT_EXP_HOURS", "12"))

        # Database
        self.database_url = os.getenv(
            "DATABASE_URL", f"sqlite:///{BASE_DIR / 'nodedash.db'}"
        )

        # Questionnaire / schema / seed live in the repo's questionnaire/ dir
        self.questionnaire_path = _path(
            "QUESTIONNAIRE_PATH", REPO_ROOT / "questionnaire" / "questions.json"
        )
        self.graph_schema_path = _path(
            "GRAPH_SCHEMA_PATH", REPO_ROOT / "questionnaire" / "graph-spec.schema.json"
        )
        self.seed_path = _path(
            "SEED_PATH", REPO_ROOT / "questionnaire" / "seed-acme-custom-furniture.json"
        )

        # LLM
        self.llm_provider = os.getenv("LLM_PROVIDER", "auto").lower()
        self.llm_base_url = os.getenv(
            "LLM_BASE_URL", "https://api.fireworks.ai/inference/v1"
        ).rstrip("/")
        self.llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("FIREWORKS_API_KEY", "")
        self.llm_model = os.getenv(
            "LLM_MODEL", "accounts/fireworks/models/qwen2p5-72b-instruct"
        )
        self.llm_timeout = float(os.getenv("LLM_TIMEOUT", "60"))
        # Qwen3 thinks by default (slow, verbose). Append the /no_think soft switch
        # to disable it for snappy replies. Set false for non-Qwen models.
        self.llm_no_think = os.getenv("LLM_NO_THINK", "true").lower() in ("1", "true", "yes")

        # Embeddings / RAG (semantic cache of past agent Q&A per node)
        # e.g. Ollama: "nomic-embed-text"; Fireworks: "nomic-ai/nomic-embed-text-v1.5"
        self.llm_embed_model = os.getenv("LLM_EMBED_MODEL", "")
        self.rag_enabled = os.getenv("RAG_ENABLED", "true").lower() in ("1", "true", "yes")
        self.rag_top_k = int(os.getenv("RAG_TOP_K", "3"))
        self.rag_threshold = float(os.getenv("RAG_THRESHOLD", "0.80"))

        # On-demand GPU (Option B): the always-on LLM_* above is the instant fallback;
        # GPU_* is the AMD MI300X (a DigitalOcean GPU Droplet) that wakes on demand.
        self.gpu_manage = os.getenv("GPU_MANAGE", "false").lower() in ("1", "true", "yes")
        self.gpu_base_url = os.getenv("GPU_BASE_URL", "").rstrip("/")
        self.gpu_model = os.getenv("GPU_MODEL", "")
        self.gpu_api_key = os.getenv("GPU_API_KEY", "")
        self.gpu_idle_minutes = int(os.getenv("GPU_IDLE_MINUTES", "15"))
        self.gpu_health_timeout = float(os.getenv("GPU_HEALTH_TIMEOUT", "3"))
        self.gpu_warm_timeout = float(os.getenv("GPU_WARM_TIMEOUT", "600"))
        # DigitalOcean droplet lifecycle (AMD Dev Cloud runs on DO)
        self.do_api_token = os.getenv("DO_API_TOKEN", "")
        self.do_gpu_snapshot_id = os.getenv("DO_GPU_SNAPSHOT_ID", "")
        self.do_gpu_size = os.getenv("DO_GPU_SIZE", "gpu-mi300x1-192gb")
        self.do_region = os.getenv("DO_REGION", "atl1")
        self.do_gpu_name = os.getenv("DO_GPU_NAME", "nodedash-mi300x")
        self.do_ssh_key_ids = [s.strip() for s in os.getenv("DO_SSH_KEY_IDS", "").split(",") if s.strip()]
        self.gpu_vllm_port = int(os.getenv("GPU_VLLM_PORT", "8000"))

        # CORS
        origins = os.getenv("CORS_ORIGINS", "*")
        self.cors_origins = ["*"] if origins.strip() == "*" else [
            o.strip() for o in origins.split(",") if o.strip()
        ]

    @property
    def llm_enabled(self) -> bool:
        """Whether a real LLM endpoint should be used (vs. the offline mock)."""
        if self.llm_provider == "mock":
            return False
        if self.llm_provider in ("fireworks", "amd"):
            return True
        # auto: use the endpoint only if we have an api key or a non-default base url
        return bool(self.llm_api_key) or "fireworks.ai" not in self.llm_base_url

    @property
    def embeddings_enabled(self) -> bool:
        """RAG only runs when enabled, an LLM endpoint is live, and an embed model is set."""
        return self.rag_enabled and self.llm_enabled and bool(self.llm_embed_model)

    @property
    def gpu_enabled(self) -> bool:
        """On-demand GPU routing is active only when managed + a target is configured."""
        return self.gpu_manage and bool(self.gpu_base_url) and bool(self.gpu_model)


settings = Settings()
