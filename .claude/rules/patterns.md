---
paths:
  - "*.py"
  - "**/*.py"
---

# Common Patterns — Jira AI Agent Project

## Adding a New Jira Tool

```python
from langchain_core.tools import tool

@tool
def my_jira_tool(param: str) -> dict:
    """One-line description for the LLM.
    
    Args:
        param: What this parameter means
    
    Returns:
        Dict with status and result data
    """
    try:
        jira = JIRA(
            server=os.getenv("JIRA_INSTANCE_URL"),
            basic_auth=(os.getenv("JIRA_USERNAME"), os.getenv("JIRA_API_TOKEN"))
        )
        # ... do work
        return {"status": "SUCCESS", "data": result}
    except Exception as e:
        return {"status": "FAILED", "error": str(e)}
```

## Environment Loading Pattern

```python
from pathlib import Path
from dotenv import load_dotenv

def load_environment() -> dict[str, str]:
    script_dir = Path(__file__).resolve().parent
    for env_path in [script_dir / ".env", script_dir / "config.env"]:
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
            break
    
    required = ["JIRA_INSTANCE_URL", "JIRA_USERNAME", "JIRA_API_TOKEN", "GOOGLE_API_KEY"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"Missing env vars: {', '.join(missing)}")
    
    return {k: os.getenv(k) for k in required}
```

## Gemini LLM Initialization

```python
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=env_vars["GOOGLE_API_KEY"],
    temperature=0.2,
)

agent_executor = create_agent(
    model=llm,
    tools=[tool1, tool2],
    system_prompt="You are a Jira assistant for ADL project..."
)

response = agent_executor.invoke({"messages": [("human", user_query)]})
```

## Audit Logging

```python
from datetime import datetime, timezone

def log_operation(log_file: str, operation: str, status: str, details: dict) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "operation": operation,
        "status": status,
        "details": details,
    }
    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")
```

## Running the Agents

```powershell
# Activate venv first
.\venv\Scripts\Activate.ps1

# Master agent (interactive or with arg)
python master_jira_agent.py
python master_jira_agent.py "Show blockers in ADL"

# Standalone requirement analyzer
python jira_hybrid_agent.py ADL-123

# Basic analysis
python jira_agent.py ADL-456
```
