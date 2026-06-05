"""Unit tests for the filler registry and SinglePassFiller (no real LLM)."""

from __future__ import annotations

import pytest

from adl_automated_delivery_pipeline.documentation.context import DocContext
from adl_automated_delivery_pipeline.documentation.fillers import base as fillers_base
from adl_automated_delivery_pipeline.documentation.fillers.single_pass import SinglePassFiller
from adl_automated_delivery_pipeline.documentation.template import Template


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    """Captures the prompt and returns canned markdown."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.last_messages = None

    def invoke(self, messages):  # noqa: ANN001
        self.last_messages = messages
        return _FakeResponse(self.reply)


@pytest.mark.unit
def test_single_pass_resolves_placeholders_and_returns_markdown() -> None:
    llm = _FakeLLM("# ADL-1729\n\n## Risks\n\n| Risk | Mitigation |\n|--|--|\n| x | y |")
    filler = SinglePassFiller(llm=llm)
    tpl = Template("# {{title}}\n\n## Risks\n<!-- list risks -->\n")
    ctx = DocContext(title="ADL-1729")

    out = filler.fill(tpl, ctx)

    assert out.startswith("# ADL-1729")
    # the prompt sent to the LLM had placeholders already resolved
    human = str(llm.last_messages[-1].content)
    assert "{{title}}" not in human
    assert "ADL-1729" in human


@pytest.mark.unit
def test_filler_registry_returns_single_pass() -> None:
    import adl_automated_delivery_pipeline.documentation.fillers  # noqa: F401
    assert isinstance(fillers_base.get_filler("single_pass"), SinglePassFiller)


@pytest.mark.unit
def test_get_filler_unknown_raises() -> None:
    with pytest.raises(ValueError):
        fillers_base.get_filler("nope")
