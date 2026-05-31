"""Provider-selection tests for the centralized LLM factory.

These are fully offline — the real provider constructors are monkeypatched with
sentinels so no network calls or API keys are required.
"""

from __future__ import annotations

import pytest

from adl_automated_delivery_pipeline import llm


@pytest.fixture
def patched_factories(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Replace each provider constructor with a sentinel-returning stub."""
    sentinels = {llm.CLAUDE: "CLAUDE_MODEL", llm.OPENAI: "OPENAI_MODEL", llm.GEMINI: "GEMINI_MODEL"}
    monkeypatch.setattr(llm, "make_claude", lambda *a, **k: sentinels[llm.CLAUDE])
    monkeypatch.setattr(llm, "make_openai", lambda *a, **k: sentinels[llm.OPENAI])
    monkeypatch.setattr(llm, "make_gemini", lambda *a, **k: sentinels[llm.GEMINI])
    # Rebuild the provider table so it references the patched callables.
    monkeypatch.setattr(
        llm,
        "_PROVIDERS",
        {
            llm.CLAUDE: (lambda: bool(llm.settings.ANTHROPIC_API_KEY), llm.make_claude),
            llm.OPENAI: (lambda: bool(llm.settings.OPENAI_API_KEY), llm.make_openai),
            llm.GEMINI: (lambda: bool(llm.settings.GOOGLE_API_KEY), llm.make_gemini),
        },
    )
    return sentinels


def _set_keys(monkeypatch: pytest.MonkeyPatch, *, anthropic="", openai="", google="", primary="claude") -> None:
    monkeypatch.setattr(llm.settings, "ANTHROPIC_API_KEY", anthropic)
    monkeypatch.setattr(llm.settings, "OPENAI_API_KEY", openai)
    monkeypatch.setattr(llm.settings, "GOOGLE_API_KEY", google)
    monkeypatch.setattr(llm.settings, "PRIMARY_LLM", primary)


@pytest.mark.unit
def test_prefers_claude_when_key_present(monkeypatch, patched_factories) -> None:
    _set_keys(monkeypatch, anthropic="x", openai="y", google="z", primary="claude")
    assert llm.get_llm() == patched_factories[llm.CLAUDE]


@pytest.mark.unit
def test_falls_back_to_claude_when_primary_key_missing(monkeypatch, patched_factories) -> None:
    # PRIMARY_LLM=gemini but only the Claude key is set -> Claude wins.
    _set_keys(monkeypatch, anthropic="x", primary="gemini")
    assert llm.get_llm() == patched_factories[llm.CLAUDE]


@pytest.mark.unit
def test_honours_explicit_gemini_preference(monkeypatch, patched_factories) -> None:
    _set_keys(monkeypatch, anthropic="x", google="z", primary="gemini")
    assert llm.get_llm() == patched_factories[llm.GEMINI]


@pytest.mark.unit
def test_openai_fallback_when_no_claude(monkeypatch, patched_factories) -> None:
    _set_keys(monkeypatch, openai="y", primary="claude")
    assert llm.get_llm() == patched_factories[llm.OPENAI]


@pytest.mark.unit
def test_raises_when_no_provider_configured(monkeypatch, patched_factories) -> None:
    _set_keys(monkeypatch, primary="claude")
    with pytest.raises(RuntimeError, match="No LLM API key configured"):
        llm.get_llm()
