"""Environment-driven settings. No pydantic-settings dependency — plain os.environ."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent      # backend/
REPO_ROOT = BASE_DIR.parent                            # NodeDash/


def _path(env_key: str, default: Path) -> Path:
    return Path(os.getenv(env_key, str(default)))


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


settings = Settings()
