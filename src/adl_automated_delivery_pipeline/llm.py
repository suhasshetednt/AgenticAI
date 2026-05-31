"""Centralized, Claude-native LLM provider factory.

This is the single place where chat models are constructed. Claude (Anthropic)
is the primary provider; Gemini and OpenAI are optional fallbacks that are only
imported when actually selected, so the pipeline runs without ``google`` or
``openai`` packages installed as long as ``ANTHROPIC_API_KEY`` is set.

Selection order:
  1. ``PRIMARY_LLM`` preference, if its API key is configured.
  2. Claude (Anthropic) — the project default.
  3. OpenAI, then Gemini, as last-resort fallbacks.

All other modules should call :func:`get_llm` rather than constructing a
provider client directly.
"""

from __future__ import annotations

import logging
from typing import Any

from adl_automated_delivery_pipeline.config import settings

logger = logging.getLogger(__name__)

# Provider identifiers accepted by ``PRIMARY_LLM`` / :func:`get_llm`.
CLAUDE = "claude"
GEMINI = "gemini"
OPENAI = "openai"


def make_claude(model: str | None = None, temperature: float | None = None) -> Any:
    """Construct an Anthropic Claude chat model (the primary provider)."""
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=model or settings.CLAUDE_MODEL,
        temperature=settings.AGENT_TEMPERATURE if temperature is None else temperature,
        api_key=settings.ANTHROPIC_API_KEY,
        max_tokens=settings.MAX_TOKENS,
    )


def make_openai(model: str | None = None, temperature: float | None = None) -> Any:
    """Construct an OpenAI chat model (optional fallback)."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model or settings.OPENAI_MODEL,
        temperature=settings.AGENT_TEMPERATURE if temperature is None else temperature,
        api_key=settings.OPENAI_API_KEY,
    )


def make_gemini(model: str | None = None, temperature: float | None = None) -> Any:
    """Construct a Google Gemini chat model (optional fallback)."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=model or settings.GEMINI_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        temperature=settings.AGENT_TEMPERATURE if temperature is None else temperature,
    )


# Provider name -> (api-key-present predicate, factory)
_PROVIDERS: dict[str, tuple[Any, Any]] = {
    CLAUDE: (lambda: bool(settings.ANTHROPIC_API_KEY), make_claude),
    OPENAI: (lambda: bool(settings.OPENAI_API_KEY), make_openai),
    GEMINI: (lambda: bool(settings.GOOGLE_API_KEY), make_gemini),
}

# Fallback order once the explicit preference has been considered.
_FALLBACK_ORDER = (CLAUDE, OPENAI, GEMINI)


def get_llm() -> Any:
    """Return a chat model, preferring Claude.

    Honours ``settings.PRIMARY_LLM`` when that provider's API key is set,
    otherwise falls back to Claude, then OpenAI, then Gemini.

    Raises:
        RuntimeError: if no provider has an API key configured.
    """
    primary = (settings.PRIMARY_LLM or CLAUDE).lower()

    # 1. Honour explicit preference when its key is available.
    if primary in _PROVIDERS:
        has_key, factory = _PROVIDERS[primary]
        if has_key():
            logger.debug("get_llm: using preferred provider %r", primary)
            return factory()
        logger.warning(
            "get_llm: PRIMARY_LLM=%r but no API key configured — falling back.",
            primary,
        )

    # 2. Fall back in Claude-first order.
    for name in _FALLBACK_ORDER:
        has_key, factory = _PROVIDERS[name]
        if has_key():
            logger.info("get_llm: falling back to provider %r", name)
            return factory()

    raise RuntimeError(
        "No LLM API key configured. Set ANTHROPIC_API_KEY (preferred), "
        "OPENAI_API_KEY, or GOOGLE_API_KEY in config.env."
    )
