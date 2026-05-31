"""QlikSense Cloud agent — builds dashboards from Dremio VDS data."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from typing import Any
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from adl_automated_delivery_pipeline.agents.base import get_llm

from adl_automated_delivery_pipeline.tools.qlik_tools import (
    create_apu_health_dashboard,
    list_qlik_apps,
    list_qlik_spaces,
    refresh_apu_dashboard,
)

logger = logging.getLogger(__name__)

_TOOLS = [create_apu_health_dashboard, list_qlik_apps, list_qlik_spaces, refresh_apu_dashboard]

_SYSTEM_PROMPT = """You are a QlikSense Cloud dashboard builder for ASL Airlines.

Your job is to create and refresh QlikSense dashboards that pull data live from Dremio VDS.

WORKFLOW:
1. When given a Dremio VDS path, call create_apu_health_dashboard with it.
2. Default space is 'development' unless the user says otherwise.
3. Use list_qlik_apps / list_qlik_spaces to inspect existing apps or spaces.
4. Use refresh_apu_dashboard to reload an existing app with fresh Dremio data.
5. READ the ticket requirements provided to you to determine the conditional formatting thresholds. Extract the `amber_threshold` and `red_threshold` from the requirements and pass them to `create_apu_health_dashboard`.

DASHBOARD STANDARDS:
- Columns (in order): APU P/n | APU S/n | PSN | Aircraft Reg. | Reference Date |
                      Trend Type | Workorder | CT5ATP value | Aircraft Type
- Always report the app_url from the tool result so the user can open it directly.

RESPONSE FORMAT:
  Status        : SUCCESS / FAILED
  Rows loaded   : <n>
  Connection    : Dremio_Cloud_EU (live REST connection — not embedded data)
  App URL       : <direct link to the sheet>
  Error (if any): <full message>
"""


class QlikAgent:
    def __init__(self) -> None:
        # parents[3] = project root (file is <root>/src/<pkg>/agents/<file>.py).
        env = Path(__file__).resolve().parents[3] / "config.env"
        if env.exists():
            load_dotenv(env)

        self._agent = create_react_agent(
            model=get_llm(),
            tools=_TOOLS,
            prompt=_SYSTEM_PROMPT,
        )

    def run(self, message: str) -> dict[str, Any]:
        try:
            result   = self._agent.invoke({"messages": [HumanMessage(content=message)]})
            messages = result.get("messages", [])
            output   = messages[-1].content if messages else ""
            return {"status": "SUCCESS", "output": output}
        except Exception as e:
            logger.exception("QlikAgent error")
            return {"status": "FAILED", "error": str(e)}
