---
paths:
  - "*.py"
  - "**/*.py"
---

# Engineering Standards — Python Jira Agent

## Auto-Reject Criteria

Reject code that:
1. Uses `print()` instead of `logging` in non-script code (scripts are OK)
2. Has bare `except:` clauses — always catch specific exceptions
3. Has empty `except` blocks that swallow errors silently
4. Creates a new `JIRA()` connection outside of a `@tool` or dedicated helper
5. Hardcodes credentials or API keys (use `os.getenv()`)
6. Missing type annotations on function signatures
7. Uses `datetime.utcnow()` — use `datetime.now(timezone.utc)` instead
8. Writes to `config.env` or `.env` files

## Required Patterns

- `load_dotenv()` before any `os.getenv()` calls
- Validate all required env vars at startup with clear error messages
- All `@tool` functions must return a `dict` with a `"status"` key
- Use `dataclasses` or typed dicts for structured data, not raw dicts
- Log with the module logger: `logger = logging.getLogger(__name__)`
