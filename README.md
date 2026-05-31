# ADL Automated Delivery Pipeline

A **Claude-native**, LangGraph multi-agent pipeline that takes an ASL Airlines ADL
Jira ticket and drives it through requirement extraction, technical documentation,
Dremio Virtual Dataset (VDS) creation, and an optional Qlik Sense dashboard — with a
human-in-the-loop approval gate and a full audit trail.

> Migrated from a Google Antigravity / Gemini-first setup to run primarily on
> **Claude (Anthropic)**. Gemini and OpenAI remain available as optional fallbacks.

## Pipeline

```
Jira ticket
   │  Jira Agent      → structured requirements (text + image attachments)
   ▼
Documentation Agent  → Technical Implementation Document (.docx)
   ▼
Dremio Agent         → optimised Calcite SQL → Virtual Dataset
   ▼
Qlik Agent (opt.)    → Qlik Sense dashboard from the VDS
```

A FastAPI service additionally listens for Jira webhooks and routes events through a
**supervisor graph** (intent classification → specialised agent → approval gate →
mutation execution → audit commit).

## Quick start

```powershell
# 1. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies (editable install adds the src/ package to the path)
pip install -r requirements.txt
pip install -e .

# 3. Configure credentials
Copy-Item config.env.example config.env
#   ...then edit config.env and set at minimum:
#   JIRA_INSTANCE_URL, JIRA_USERNAME, JIRA_API_TOKEN, ANTHROPIC_API_KEY

# 4a. Run the interactive end-to-end workflow
adl-pipeline

# 4b. Or start the API server (webhooks + approvals)
uvicorn adl_automated_delivery_pipeline.api.main:app --reload --port 8000
```

The package uses a **src layout** (`src/adl_automated_delivery_pipeline/`). The
`pip install -e .` step exposes these console commands (without it, set `PYTHONPATH=src`):

| Command        | What it does                                                                 |
| -------------- | ---------------------------------------------------------------------------- |
| `adl-pipeline` | Interactive end-to-end workflow (Jira → Doc → Dremio → Qlik)                 |
| `adl-jira`     | Standalone Claude Jira assistant (single-query or interactive)               |
| `adl-doc`      | Generate a Technical Implementation Document for one ticket (read-only)      |

```powershell
adl-doc ADL-1721   # writes Project Documentation/ADL-1721_<timestamp>.docx
```

## LLM configuration

Claude is the default. Provider selection is centralized in
`adl_automated_delivery_pipeline/llm.py`:

| Setting             | Default                        | Notes                                   |
| ------------------- | ------------------------------ | --------------------------------------- |
| `PRIMARY_LLM`       | `claude`                       | `claude` \| `gemini` \| `openai`        |
| `ANTHROPIC_API_KEY` | —                              | required for the primary path           |
| `CLAUDE_MODEL`      | `claude-haiku-4-5-20251001`    | any current Claude model id             |
| `OPENAI_API_KEY`    | — (optional fallback)          | enables OpenAI fallback when set        |
| `GOOGLE_API_KEY`    | — (optional fallback)          | enables Gemini fallback when set        |

Fallback provider packages are imported lazily — with only `ANTHROPIC_API_KEY` set you
can uninstall `langchain-openai` / `langchain-google-genai` and the app still runs.

## Health & config endpoints

- `GET /health` — liveness
- `GET /ready` — checks Jira connectivity and which LLM provider is configured
- `GET /config` — non-sensitive configuration (primary LLM, models, providers configured)

## Security

`config.env`, `.env`, and `agents/config.env` hold live credentials and are **git-ignored**.
Commit only `config.env.example`. Never paste real tokens into source, docs, or commits.

## Development

- `black` (line length 100), `ruff`, `pyright`
- `pytest` — `-m unit` for fast tests, `-m integration` for service-touching tests

See [CLAUDE.md](./CLAUDE.md) for the architecture map and coding conventions.
