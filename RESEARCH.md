# Research Notes — ADL Automated Delivery Pipeline
> Auto-updated by Claude. Human-readable. Edit freely.
> Last updated: 2026-06-08

---

## How to use this file
- Claude reads this at the start of every session and updates it when new findings are made.
- Add your own notes freely — Claude will not overwrite manual entries.
- Organised by topic. Most recent findings at the top of each section.

---

## Architecture Decisions
- LLM provider: always via `get_llm()` from `adl_automated_delivery_pipeline.llm` — never direct instantiation
- MCP transport: stdio locally, never HTTP
- DB migrations: Alembic (not drop-and-recreate)
- Agent pattern: follow `doc_agent.py` exactly for new agents

## Known Bugs & Fixes
- **audit not defined (line 1332)**: `audit()` was undefined — replaced with `AuditLogger.log_action(trace_id="interactive", session_id=ticket, agent="dremio_agent")`

## Dremio Agent (In Progress)
- Goal: NL → Dremio SQL → VDS creation
- Auth: PAT-based from credentials.conf
- Catalog: dremio-db (Nessie branch)
- SQL dialect: Calcite — no trailing semicolons, no ORDER BY/LIMIT in VDS

## Test Suite
- 49/49 tests passing (Doc Agent)
- Run: `pytest -m unit -x -q`
- Test location: `tests/`

## Environment
- Config: loaded from `config.env` at project root
- Never read/edit/commit `config.env` or `.env`
- Editable install required: `pip install -e .`

---
<!-- Claude appends new findings below this line -->

## Doc Agent
- **"no style with name 'List Bullet'" error**: The ASL branded template does NOT include the "List Bullet" built-in style. `brand.add_bullet` already handles this via `_try_paragraph_style` fallback chain. Root cause was `brand.add_heading` had no style-error guard, and `_render_tokens` had no per-token try-except, so any unexpected `KeyError` from python-docx style lookup (e.g. LLM output triggering an untested code path) crashed the whole render and propagated out of `_doc_phase`. Fix: wrapped `add_heading` with `(KeyError, ValueError)` handler + added per-token guard in `_render_tokens`. Stale `.pyc` cache in the documentation module was also cleared.
