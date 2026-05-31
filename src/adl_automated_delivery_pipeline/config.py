"""Central configuration for the ADL Automated Delivery Pipeline.

Claude-native by default (``PRIMARY_LLM = "claude"``) with optional Gemini and
OpenAI fallbacks. Settings are read from environment variables, which are loaded
once at import time from the first set of ``config.env`` / ``.env`` files found
in the project root, the package directory, or the agents sub-package.
"""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Environment discovery ─────────────────────────────────────────────────────
# Load env files once at import time. With the ``src`` layout the package lives at
# ``<root>/src/adl_automated_delivery_pipeline`` so the project root is two levels up.
# We search the project root first, then fall back to package-local env files so the
# pipeline runs whether launched from the repo root, the package, or a packaged install.
# ``override=False`` means the real process environment always wins.
_PKG_DIR = Path(__file__).resolve().parent            # <root>/src/adl_automated_delivery_pipeline
_SRC_DIR = _PKG_DIR.parent                            # <root>/src
_ROOT = _SRC_DIR.parent                               # project root

_ENV_CANDIDATES = [
    _ROOT / "config.env",
    _ROOT / ".env",
    _PKG_DIR / "config.env",
    _PKG_DIR / ".env",
    _PKG_DIR / "agents" / "config.env",
]
for _candidate in _ENV_CANDIDATES:
    if _candidate.exists():
        load_dotenv(_candidate, override=False)


class Settings(BaseSettings):
    # ── Jira ──────────────────────────────────────────────────────────────────
    JIRA_INSTANCE_URL: str
    JIRA_USERNAME: str
    JIRA_API_TOKEN: str
    DEFAULT_PROJECT: str = "ADL"

    # ── LLM providers ─────────────────────────────────────────────────────────
    # Claude is the primary provider. Gemini and OpenAI are optional fallbacks
    # used only when their API key is set and Claude is unavailable.
    PRIMARY_LLM: str = "claude"          # claude | gemini | openai

    # Anthropic (primary)
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-haiku-4-5-20251001"

    # OpenAI (fallback)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # Google Gemini (fallback)
    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    # Shared generation settings
    AGENT_TEMPERATURE: float = 0.2
    MAX_TOKENS: int = 8096

    # ── Dremio ────────────────────────────────────────────────────────────────
    DREMIO_CATALOG_NAME: str = "dremio-db"
    DREMIO_PROJECT_ID: str = ""

    # Directory holding catalog_data.json / excel_master.json (used by the Dremio
    # agent to resolve exact table & column names). Defaults to the project root.
    CATALOG_DIR: str = str(_ROOT)

    # ── Optional infrastructure ─────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"        # falls back to file-based store
    POSTGRES_DSN: str = ""                              # falls back to MemorySaver
    QDRANT_URL: str = "http://localhost:6333"          # falls back to in-memory dedup

    # ── Approval settings ───────────────────────────────────────────────────────
    APPROVAL_TTL_HOURS: int = 24
    APPROVAL_STORE_DIR: str = str(_ROOT / "approval_store")

    # ── Audit ───────────────────────────────────────────────────────────────────
    AUDIT_LOG_FILE: str = str(_ROOT / "lg_audit.jsonl")

    # ── Webhook ───────────────────────────────────────────────────────────────
    JIRA_WEBHOOK_SECRET: str = ""          # set to enable HMAC verification
    WEBHOOK_AUTO_PROCESS: bool = True      # auto-trigger agents on incoming Jira events
    WEBHOOK_REQUIRE_APPROVAL: bool = True  # stage mutations even from auto-triggered events

    # ── API security ────────────────────────────────────────────────────────────
    API_SECRET_KEY: str = ""          # required for approval auth in production
    ENV: str = "development"          # set to "production" to harden endpoints
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000,http://localhost:8501"

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(**{})


settings = get_settings()
