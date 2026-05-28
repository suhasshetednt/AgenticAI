"""Central configuration — reads from config.env or .env."""

from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load env file once at import time — check multiple locations, load all that exist
_ROOT = Path(__file__).resolve().parent.parent
_LG_ROOT = Path(__file__).resolve().parent
for _candidate in [
    _ROOT / "config.env",
    _ROOT / ".env",
    _LG_ROOT / "agents" / "config.env",
]:
    if _candidate.exists():
        load_dotenv(_candidate, override=False)


class Settings(BaseSettings):
    # Jira
    JIRA_INSTANCE_URL: str
    JIRA_USERNAME: str
    JIRA_API_TOKEN: str
    DEFAULT_PROJECT: str = "ADL"

    # Anthropic
    ANTHROPIC_API_KEY: str = ""

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"

    # Dremio
    DREMIO_CATALOG_NAME: str = "dremio-db"
    DREMIO_PROJECT_ID: str = ""

    # Google (fallback LLM)
    GOOGLE_API_KEY: str = ""

    # Redis (optional — falls back to file-based store)
    REDIS_URL: str = "redis://localhost:6379/0"

    # PostgreSQL (optional — falls back to MemorySaver)
    POSTGRES_DSN: str = ""

    # Qdrant (optional — falls back to in-memory dedup)
    QDRANT_URL: str = "http://localhost:6333"

    # Approval settings
    APPROVAL_TTL_HOURS: int = 24
    APPROVAL_STORE_DIR: str = str(_ROOT / "approval_store")

    # Audit
    AUDIT_LOG_FILE: str = str(_ROOT / "lg_audit.jsonl")

    # Webhook
    JIRA_WEBHOOK_SECRET: str = ""          # set this in config.env to enable HMAC verification
    WEBHOOK_AUTO_PROCESS: bool = True      # auto-trigger agents on incoming Jira events
    WEBHOOK_REQUIRE_APPROVAL: bool = True  # stage mutations even from auto-triggered events

    # Agent settings
    PRIMARY_LLM: str = "claude"          # claude | gemini
    CLAUDE_MODEL: str = "claude-haiku-4-5-20251001"
    GEMINI_MODEL: str = "gemini-2.0-flash"
    AGENT_TEMPERATURE: float = 0.2
    MAX_TOKENS: int = 8096

    # API security
    API_SECRET_KEY: str = ""          # set in config.env — required for approval auth in production
    ENV: str = "development"          # set to "production" to harden endpoints
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000,http://localhost:8501"

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
