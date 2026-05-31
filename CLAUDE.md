# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

The **ADL Automated Delivery Pipeline** — a Claude-native, LangGraph multi-agent
system for the ASL Airlines ADL data-lake project (DnT Infotech). It turns a Jira
ticket into delivered work across three phases:

1. **Jira Agent** — fetch a ticket, extract structured requirements (incl. image attachments).
2. **Documentation Agent** — generate a Technical Implementation Document (`.docx`).
3. **Dremio Agent** — generate optimised Dremio (Calcite) SQL, pick a folder, create a Virtual Dataset.
4. **Qlik Agent** — (optional) build a Qlik Sense dashboard from the VDS.

A FastAPI service also auto-processes Jira webhooks through a supervisor graph with a
human-in-the-loop approval gate.

> This project was migrated from a Google Antigravity / Gemini-first setup to be
> **Claude-native**. Claude (Anthropic) is the primary LLM; Gemini and OpenAI remain
> as optional fallbacks. See "LLM providers" below.

## Layout

Uses the **src layout** — the package lives under `src/` so the project root is two
levels above `config.py`.

```
adl_automated_delivery_pipeline/        <- project root
  src/adl_automated_delivery_pipeline/  <- the importable package
    config.py          # pydantic-settings; env discovery; Claude-native defaults
    llm.py             # SINGLE source of LLM clients — get_llm(), make_claude/openai/gemini
    state.py           # AgentState TypedDict + make_initial_state()
    audit.py           # AuditLogger (JSONL audit trail)
    approval.py        # human-in-the-loop approval store
    rbac.py, memory.py, events.py, webhook_processor.py
    agents/            # BaseJiraAgent + specialised ReAct agents (sprint, ticket, dremio, qlik, doc, ...)
    graphs/            # supervisor.py — intent classifier + StateGraph wiring
    nodes/             # approval / execute / audit / error graph nodes
    tools/             # @tool functions: jira_read/write, dremio, qlik, github, analysis, report
    workflows/         # adl_automated_delivery_pipeline.py (interactive CLI), jira_to_dremio.py
    api/               # main.py (FastAPI factory), app.py (websocket dashboard), routes/
    prompts/, rules/   # system prompts and the Dremio SQL rules doc
  tests/               # pytest suite (offline unit tests)
  config.env           # real secrets (git-ignored) — single source at project root
  config.env.example, requirements.txt, pyproject.toml, pyrightconfig.json
  README.md, CLAUDE.md, .gitignore
  .claude/settings.json
```

## LLM providers (important)

- **Always construct models through `adl_automated_delivery_pipeline.llm`.** Do not call
  `ChatAnthropic(...)` / `ChatOpenAI(...)` / `ChatGoogleGenerativeAI(...)` directly elsewhere.
  - `get_llm()` — returns the configured chat model (Claude-first selection).
  - `make_claude()`, `make_openai()`, `make_gemini()` — explicit constructors with lazy imports.
- `get_llm()` is also re-exported from `agents.base` for backwards compatibility.
- Selection: honour `PRIMARY_LLM` if its key is set, else Claude → OpenAI → Gemini.
- Fallback provider packages are imported lazily, so the app runs with only
  `langchain-anthropic` installed as long as `ANTHROPIC_API_KEY` is set.

## Configuration & secrets

- Settings come from environment variables, loaded by `config.py` from the first existing
  of: `config.env` / `.env` at the project root, the package dir, or `agents/config.env`.
- **Never read, edit, commit, or print the real secret files** (`config.env`, `.env`,
  `agents/config.env`). They are git-ignored and denied in `.claude/settings.json`.
- When documenting or adding config, update `config.env.example` (placeholders only).

## Running

```powershell
# Install (editable install puts the src/ package on the path)
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .

# Interactive end-to-end workflow (Jira -> Doc -> Dremio -> Qlik)
adl-pipeline
#   or: python -m adl_automated_delivery_pipeline.workflows.adl_automated_delivery_pipeline

# Standalone Claude Jira assistant
adl-jira "Show blockers in ADL"
#   or: python -m adl_automated_delivery_pipeline.agents.jira_claude_agent "Show blockers in ADL"

# Generate a Technical Implementation Document for one ticket (read-only, no mutations)
adl-doc ADL-1721
#   or: python -m adl_automated_delivery_pipeline.workflows.generate_doc ADL-1721

# API server (webhooks + approvals)
uvicorn adl_automated_delivery_pipeline.api.main:app --reload --port 8000

# Tests (offline unit suite)
pytest -m unit
```

> Without an editable install, set `PYTHONPATH=src` so `import adl_automated_delivery_pipeline` resolves.

## Conventions (enforced — auto-reject violations)

- Use the module logger (`logger = logging.getLogger(__name__)`), **not `print()`**, in
  library code. `print()` is acceptable only in interactive CLI scripts (e.g. the
  `workflows/` menus, which intentionally print to the console / websocket bridge).
- Catch **specific** exceptions; never `except:` bare and never silently swallow errors.
- Every `@tool` function returns a `dict` with a `"status"` key (`"SUCCESS"` / `"FAILED"`).
- Full **type annotations** on function signatures.
- Use `datetime.now(timezone.utc)`, never `datetime.utcnow()`.
- Read credentials via settings / `os.getenv()` — never hardcode keys.
- Create Jira connections inside a `@tool` or a dedicated helper, not ad-hoc.

## Tooling

- Format with `black` (line length 100), lint with `ruff`, type-check with `pyright`.
- Tests with `pytest` (`-m unit` / `-m integration`).

## Gotchas

- Dremio uses Calcite SQL: no trailing semicolons, no `ORDER BY`/`LIMIT` in VDS definitions,
  reserved words must be quoted. The workflow has hardened regex fix-ups for this — preserve them.
- AMOS tables must use the `amos_postgres.amos.<table>` prefix; `aircraft` uses `ac_registr`
  (not `tail_number`). See `_AMOS_CATALOG_OVERRIDES` and `_fix_dremio_sql` in the workflow.
- The interactive dashboard (`docs/ai_dashboard_prototype.html`) is optional and lives
  outside the package; `api/app.py` degrades gracefully if `docs/` is absent.
