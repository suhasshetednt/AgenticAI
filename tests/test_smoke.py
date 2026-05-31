"""Smoke tests: package imports cleanly and is Claude-native by default."""

from __future__ import annotations

import importlib

import pytest

CORE_MODULES = [
    "adl_automated_delivery_pipeline.config",
    "adl_automated_delivery_pipeline.llm",
    "adl_automated_delivery_pipeline.state",
    "adl_automated_delivery_pipeline.agents.base",
    "adl_automated_delivery_pipeline.agents.doc_agent",
    "adl_automated_delivery_pipeline.agents.jira_claude_agent",
    "adl_automated_delivery_pipeline.graphs.supervisor",
    "adl_automated_delivery_pipeline.api.main",
]


@pytest.mark.unit
@pytest.mark.parametrize("module", CORE_MODULES)
def test_module_imports(module: str) -> None:
    assert importlib.import_module(module) is not None


@pytest.mark.unit
def test_primary_llm_defaults_to_claude() -> None:
    from adl_automated_delivery_pipeline.config import settings

    assert settings.PRIMARY_LLM == "claude"
    assert settings.CLAUDE_MODEL.startswith("claude")


@pytest.mark.unit
def test_base_reexports_get_llm() -> None:
    from adl_automated_delivery_pipeline import llm
    from adl_automated_delivery_pipeline.agents.base import get_llm

    assert get_llm is llm.get_llm
