# Python Engineering & Coding Standards

This document consolidates the essential Python engineering rules reviewed from the external agent ruleset, adapted for universal application.

## 1. Core Engineering Rules
*   **Logging over Print:** Reject code that uses `print()` instead of the standard `logging` module in non-script production code.
*   **Exception Handling:** No bare `except:` clauses. Always catch specific exceptions. Never use empty `except` blocks that swallow errors silently.
*   **Credentials:** Never hardcode credentials or API keys. Always use `os.getenv()` backed by a `.env` file via `dotenv`. Do not write secrets to disk.
*   **Datetime:** Deprecate `datetime.utcnow()`. Use `datetime.now(timezone.utc)` instead.

## 2. Coding Style & Immutability
*   **PEP 8:** Follow PEP 8 conventions strictly.
*   **Type Annotations:** Enforce type annotations on all function signatures.
*   **Immutable Data Structures:** Prefer `dataclasses` with `frozen=True` or `NamedTuple` for data passing over raw dictionaries.
*   **Formatting:** Use `black` for formatting, `isort` for imports, and `ruff` for linting.

## 3. Security
*   **Secret Management:** Load environment variables explicitly via `load_dotenv()`. Validate all required environment variables at application startup, raising exceptions immediately if missing.
*   **Static Analysis:** Use `bandit -r src/` for static security analysis of Python code.
