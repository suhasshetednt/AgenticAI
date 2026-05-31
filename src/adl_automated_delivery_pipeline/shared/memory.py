"""Best-effort wrapper around the centralized Memory Platform SDK.

Memory is an *augmentation*, never a hard dependency: every call is guarded so a slow or
down platform degrades to a safe default (``""`` / ``None``) and the ADL pipeline always
completes. Disabled (``MEMORY_ENABLED=false``) → pure no-op. ADL depends only on ``memory_sdk``
(REST), never on memory_platform internals.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from adl_automated_delivery_pipeline.config import settings

logger = logging.getLogger(__name__)


class Memory:
    def __init__(self, *, client: Any = None, client_factory: Callable[[], Any] | None = None,
                 enabled: bool | None = None, auto_apply: bool | None = None,
                 domain: str | None = None):
        self.enabled = settings.MEMORY_ENABLED if enabled is None else enabled
        self.auto_apply = settings.MEMORY_AUTO_APPLY if auto_apply is None else auto_apply
        self.domain = domain or settings.MEMORY_DOMAIN
        self._client = client
        self._factory = client_factory

    # ---- client lifecycle ----
    def _client_or_none(self):
        if not self.enabled:
            return None
        if self._client is not None:
            return self._client
        try:
            factory = self._factory
            if factory is None:
                from .clients import memory_client
                factory = memory_client
            self._client = factory()
            return self._client
        except Exception as exc:  # misconfig (e.g. MEMORY_API_KEY unset) — loud, but degrade
            logger.error("MEMORY_ENABLED but client unavailable (%s) — disabling memory", exc)
            self.enabled = False
            return None

    def _safe(self, fn, default):
        client = self._client_or_none()
        if client is None:
            return default
        try:
            return fn(client)
        except Exception as exc:  # any memory failure is non-fatal to delivery
            logger.warning("memory call failed (%s) — degrading to default", exc)
            return default

    # ---- operations ----
    def recall(self, *, task: str, domain: str | None = None, is_error: bool = False) -> str:
        """Return injected_context for the task (or '' when unavailable)."""
        res = self._safe(
            lambda c: c.search(task=task, domain=domain or self.domain, is_error=is_error),
            default=None)
        return getattr(res, "injected_context", "") or "" if res is not None else ""

    def remember(self, *, type: str, content: str, scope: str = "agent",
                 domain: str | None = None, payload: dict | None = None,
                 idempotency_key: str | None = None) -> str | None:
        res = self._safe(
            lambda c: c.store(type=type, content=content, scope=scope,
                              domain=domain or self.domain, payload=payload,
                              idempotency_key=idempotency_key),
            default=None)
        return getattr(res, "memory_id", None) if res is not None else None

    def match(self, *, error: dict) -> dict | None:
        return self._safe(lambda c: c.match_error(error=error), default=None)

    def reflect(self, *, reflection_input: dict) -> dict | None:
        return self._safe(lambda c: c.reflect(reflection_input), default=None)

    def promote(self, *, memory_id: str, reflection_input: dict) -> dict | None:
        # Best-effort: if this fails (platform down/conflict), the memory simply stays at
        # raw/validated and is NOT auto-retried here. A platform-side periodic sweep that
        # re-evaluates pending validated memories is the proper long-term fix (see OPEN_ITEMS).
        out = self._safe(
            lambda c: c.promote(memory_id, reflection=reflection_input), default=None)
        if out is None:
            logger.info("promote(%s) skipped/failed — memory left pending for later sweep",
                        memory_id)
        return out
