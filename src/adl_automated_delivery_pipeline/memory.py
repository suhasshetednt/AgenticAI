"""In-memory + file-based memory manager with graceful Qdrant degradation."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from adl_automated_delivery_pipeline.config import settings
from adl_automated_delivery_pipeline.shared.memory import Memory

logger = logging.getLogger(__name__)

# Characters to strip when tokenising text for similarity matching
_PUNCTUATION_RE = re.compile(r"[^\w\s]")

# Common English stop-words to exclude from overlap scoring
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
        "as", "it", "its", "this", "that", "these", "those", "not", "no",
        "can", "will", "may", "have", "has", "had", "do", "does", "did",
        "so", "if", "up", "my", "we", "i", "you", "he", "she", "they",
    }
)


def _tokenise(text: str) -> set[str]:
    """Lower-case, strip punctuation, split on whitespace, remove stop-words."""
    cleaned = _PUNCTUATION_RE.sub(" ", text.lower())
    tokens = {t for t in cleaned.split() if t and t not in _STOP_WORDS and len(t) > 1}
    return tokens


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity: |intersection| / |union|.  Returns 0.0 if both empty."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


class MemoryManager:
    """Lightweight memory manager for the LangGraph JIRA agent.

    Provides:
    - In-memory per-session cache (dict keyed by session_id).
    - File-backed ticket index for duplicate detection (``ticket_index.json``).
    - File-backed outcomes log (``agent_outcomes.jsonl``).

    Qdrant / vector DB is not required; similarity is computed via Jaccard
    word-overlap, which is adequate for JIRA ticket deduplication.
    """

    def __init__(self, memory: Memory | None = None) -> None:
        self._session_cache: dict[str, dict] = {}
        # Centralized Memory Platform (best-effort). Outcomes route here as primary;
        # the local jsonl is kept only as an offline fallback (see store_outcome).
        self._memory = memory or Memory()

        # Derive storage paths relative to the approval store dir's parent
        base_dir = Path(settings.APPROVAL_STORE_DIR).parent
        base_dir.mkdir(parents=True, exist_ok=True)

        self._index_path: Path = base_dir / "ticket_index.json"
        self._outcomes_path: Path = base_dir / "agent_outcomes.jsonl"

        self._ticket_index: dict[str, dict] = self._load_index()

    # ── Ticket index persistence ──────────────────────────────────────

    def _load_index(self) -> dict[str, dict]:
        """Load the ticket index from disk.  Returns empty dict on first run."""
        if not self._index_path.exists():
            logger.debug("Ticket index not found — starting fresh: %s", self._index_path)
            return {}
        try:
            raw = self._index_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
            logger.warning("Ticket index has unexpected type %s — resetting.", type(data))
            return {}
        except json.JSONDecodeError as exc:
            logger.error("Ticket index JSON parse error: %s — resetting.", exc)
            return {}
        except OSError as exc:
            logger.error("Could not read ticket index: %s", exc)
            return {}

    def _save_index(self) -> None:
        """Persist the in-memory ticket index to disk (overwrite)."""
        tmp = self._index_path.with_suffix(".tmp")
        try:
            tmp.write_text(
                json.dumps(self._ticket_index, indent=2, default=str),
                encoding="utf-8",
            )
            tmp.replace(self._index_path)
        except OSError as exc:
            logger.error("Failed to save ticket index: %s", exc)

    # ── Public ticket API ─────────────────────────────────────────────

    def store_ticket(
        self,
        issue_key: str,
        summary: str,
        description: str = "",
    ) -> None:
        """Add or update a ticket in the local index for deduplication.

        Args:
            issue_key: Jira issue key, e.g. "ADL-123".
            summary: Issue summary line.
            description: Optional issue description (used in similarity matching).
        """
        self._ticket_index[issue_key] = {
            "issue_key": issue_key,
            "summary": summary,
            "description": description,
            "indexed_at": datetime.now(timezone.utc).isoformat(),
            # Pre-compute token set for fast repeated searches
            "_tokens": list(_tokenise(f"{summary} {description}")),
        }
        self._save_index()
        logger.debug("Ticket indexed: %s", issue_key)

    def find_similar_tickets(
        self,
        query: str,
        threshold: float = 0.6,
    ) -> list[dict]:
        """Find tickets whose summary+description overlaps significantly with *query*.

        Uses Jaccard word-overlap similarity.  Results are sorted by score
        descending and filtered to >= *threshold*.

        Args:
            query: The text to search for (e.g. a new ticket's summary).
            threshold: Minimum Jaccard score to include in results (0.0–1.0).

        Returns:
            List of dicts with keys: issue_key, summary, score.
        """
        query_tokens = _tokenise(query)
        if not query_tokens:
            logger.debug("find_similar_tickets: empty query token set.")
            return []

        results: list[dict] = []
        for issue_key, record in self._ticket_index.items():
            stored_tokens = set(record.get("_tokens") or [])
            if not stored_tokens:
                stored_tokens = _tokenise(
                    f"{record.get('summary', '')} {record.get('description', '')}"
                )
            score = _jaccard(query_tokens, stored_tokens)
            if score >= threshold:
                results.append(
                    {
                        "issue_key": issue_key,
                        "summary": record.get("summary", ""),
                        "score": round(score, 4),
                    }
                )

        results.sort(key=lambda r: r["score"], reverse=True)
        logger.debug(
            "find_similar_tickets: query='%s...', found %d results above threshold %.2f",
            query[:60],
            len(results),
            threshold,
        )
        return results

    # ── Session cache ─────────────────────────────────────────────────

    def cache_session(self, session_id: str, data: dict) -> None:
        """Store *data* in the in-memory session cache under *session_id*.

        Args:
            session_id: The session identifier.
            data: Arbitrary dict of session data to cache.
        """
        self._session_cache[session_id] = data
        logger.debug("Session cached: session_id=%s keys=%s", session_id, list(data.keys()))

    def get_session(self, session_id: str) -> Optional[dict]:
        """Retrieve cached session data.

        Args:
            session_id: The session identifier to look up.

        Returns:
            The cached dict if present, otherwise None.
        """
        return self._session_cache.get(session_id)

    # ── Outcomes log ──────────────────────────────────────────────────

    def store_outcome(self, session_id: str, outcome: dict) -> None:
        """Append a session outcome record to the outcomes JSONL log.

        Args:
            session_id: The session the outcome belongs to.
            outcome: Arbitrary outcome dict (e.g. final agent output, metrics).
        """
        record = {
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **outcome,
        }
        # Primary: centralized Memory Platform (cross-session, searchable).
        memory_id = self._memory.remember(
            type="decision",
            content=str(outcome.get("summary") or outcome.get("agent_output") or session_id),
            scope="agent",
            payload={"session_id": session_id, **outcome},
            idempotency_key=f"{session_id}:outcome",
        )
        if memory_id is not None:
            logger.debug("Outcome stored to memory platform: %s (session=%s)", memory_id, session_id)
            return
        # Fallback (platform disabled/unreachable): append to the local outcomes log.
        try:
            with self._outcomes_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, default=str) + "\n")
            logger.debug("Outcome stored to local jsonl fallback for session_id=%s", session_id)
        except OSError as exc:
            logger.error(
                "Failed to store outcome for session_id=%s: %s", session_id, exc
            )
