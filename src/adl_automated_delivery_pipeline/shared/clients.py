"""
Singleton connection pool for all external service clients.

All tools and agents import from here instead of constructing fresh clients.
Uses @lru_cache to guarantee one connection per process — eliminates the
~200ms TCP/auth overhead on every tool call.
"""

from __future__ import annotations

import os
from typing import Any
from functools import lru_cache
from typing import TYPE_CHECKING

from jira import JIRA

if TYPE_CHECKING:
    import httpx


@lru_cache(maxsize=1)
def jira_client() -> Any:
    """Return the singleton JIRA connection, creating it on first call."""
    return JIRA(
        server=_require("JIRA_INSTANCE_URL"),
        basic_auth=(_require("JIRA_USERNAME"), _require("JIRA_API_TOKEN")),
        options={"verify": True},
    )


@lru_cache(maxsize=1)
def dremio_http_client() -> "httpx.Client":
    """Return a persistent httpx.Client for Dremio REST API calls."""
    import httpx  # lazy import — not required if Dremio is unused

    token = _require("DREMIO_TOKEN")
    base_url = _require("dremio_url")
    return httpx.Client(
        base_url=base_url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )


@lru_cache(maxsize=1)
def qlik_http_client() -> "httpx.Client":
    """Return a persistent httpx.Client for Qlik Cloud REST API calls."""
    import httpx

    api_key = _require("QLIK_API_KEY")
    tenant = _require("QLIK_TENANT").rstrip("/")
    return httpx.Client(
        base_url=f"{tenant}/api/v1",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )


@lru_cache(maxsize=1)
def memory_client() -> Any:
    """Singleton memory_sdk client for the centralized Memory Platform.

    Raises if enabled-but-unconfigured; the Memory wrapper catches that and degrades
    (logging a clear error) so delivery is never blocked.
    """
    from memory_sdk import MemoryClient, MemoryClientConfig

    from adl_automated_delivery_pipeline.config import settings

    if not settings.MEMORY_API_KEY:
        raise RuntimeError(
            "MEMORY_API_KEY is not set. Provision a key on the platform: "
            "scripts/create_api_key.py --tenant adl"
        )
    return MemoryClient(MemoryClientConfig(
        base_url=settings.MEMORY_URL, api_key=settings.MEMORY_API_KEY,
        timeout=settings.MEMORY_TIMEOUT_S))


def invalidate_jira_client() -> None:
    """Force a fresh JIRA connection on the next call (e.g., after credential rotation)."""
    jira_client.cache_clear()


def invalidate_all() -> None:
    """Clear every cached client — use during testing or after credential rotation."""
    jira_client.cache_clear()
    dremio_http_client.cache_clear()
    qlik_http_client.cache_clear()
    memory_client.cache_clear()


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(
            f"Required environment variable '{key}' is not set. "
            "Ensure config.env is loaded before initialising any client."
        )
    return val
