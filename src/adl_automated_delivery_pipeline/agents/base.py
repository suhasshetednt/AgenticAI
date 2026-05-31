"""Base agent class shared by all specialized agents."""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, cast

from adl_automated_delivery_pipeline.audit import AuditLogger
from adl_automated_delivery_pipeline.llm import get_llm
from adl_automated_delivery_pipeline.state import AgentState

logger = logging.getLogger(__name__)

# ``get_llm`` is re-exported here for backwards compatibility — agents and
# workflows import it from this module. The Claude-native provider selection
# logic now lives in ``adl_automated_delivery_pipeline.llm``.


class BaseJiraAgent(ABC):
    """Abstract base for all specialized JIRA agents.

    Subclasses must implement:
    - ``name``: a class-level string identifier used in audit logs.
    - ``_register_tools()``: return the list of LangChain tools to bind.
    - ``_system_prompt()``: return the system prompt string for the ReAct agent.

    The ``run()`` method drives the full ReAct loop, logs timing and errors to
    the AuditLogger, and always returns an updated AgentState.
    """

    name: str = "base_agent"

    def __init__(self) -> None:
        from langgraph.prebuilt import create_react_agent

        self.llm = get_llm()
        self.tools = self._register_tools()
        self._react_agent = create_react_agent(
            model=self.llm,
            tools=self.tools,
            prompt=self._system_prompt(),
        )
        # Cap iterations to limit message-history growth (each tool call re-sends
        # the full thread, burning through the per-minute token budget).
        self._invoke_config = {"recursion_limit": 6}

    @abstractmethod
    def _register_tools(self) -> list:
        """Return the list of bound LangChain tools for this agent."""
        ...

    @abstractmethod
    def _system_prompt(self) -> str:
        """Return the system prompt string used to initialise the ReAct agent."""
        ...

    def run(self, state: AgentState) -> AgentState:
        """Invoke the ReAct agent and return an updated AgentState.

        Measures wall-clock latency, writes a SUCCESS or FAILED audit entry,
        and returns a merged state dict.  On exception the state is annotated
        with ``error`` and ``fallback_triggered=True`` so the supervisor graph
        can route to error recovery.

        Args:
            state: The current AgentState for this session.

        Returns:
            A new AgentState with updated messages, agent_output, and current_agent.
        """
        start = time.monotonic()
        result = {}
        try:
            _retry_delays = [15, 30, 60]
            for _attempt, _delay in enumerate(_retry_delays, start=1):
                try:
                    result = self._react_agent.invoke(
                        {"messages": state["messages"]},
                        config=self._invoke_config,
                    )
                    break
                except Exception as _exc:
                    if _attempt == len(_retry_delays):
                        raise
                    if "rate_limit" in str(_exc).lower() or "429" in str(_exc):
                        logger.warning(
                            "Agent %s rate-limited on attempt %d/%d — retrying in %ds",
                            self.name, _attempt, len(_retry_delays), _delay,
                        )
                        time.sleep(_delay)
                    else:
                        raise
            latency = int((time.monotonic() - start) * 1000)
            last_msg = result["messages"][-1]
            raw_content = last_msg.content if hasattr(last_msg, "content") else last_msg
            # Claude returns list[dict] content blocks when using tools — flatten to str
            if isinstance(raw_content, list):
                output = " ".join(
                    part.get("text", "") if isinstance(part, dict) else str(cast(Any, part))
                    for part in raw_content
                ).strip()
            else:
                output = str(cast(Any, raw_content))
            AuditLogger.log_action(
                trace_id=state["trace_id"],
                session_id=state["session_id"],
                agent=self.name,
                action="run",
                user_id=state["user_id"],
                role=state["role"],
                project_key=state["project_key"],
                input_summary=str(cast(Any, state["messages"][-1]))[:300],
                output_summary=output[:300],
                latency_ms=latency,
                status="SUCCESS",
            )
            return {
                **state,
                "messages": result["messages"],
                "agent_output": output,
                "current_agent": self.name,
            }
        except Exception as exc:
            logger.exception("Agent %s failed: %s", self.name, exc)
            AuditLogger.log_action(
                trace_id=state["trace_id"],
                session_id=state["session_id"],
                agent=self.name,
                action="run",
                user_id=state["user_id"],
                role=state["role"],
                project_key=state["project_key"],
                input_summary="",
                output_summary="",
                status="FAILED",
                error=str(exc),
            )
            return {
                **state,
                "error": str(exc),
                "fallback_triggered": True,
                "current_agent": self.name,
            }

