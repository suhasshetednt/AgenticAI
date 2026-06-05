"""DocContext — a source-agnostic container of facts a document references."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocContext:
    """Facts the documentation agent writes about. Built by adapters; the agent
    itself never imports a specific source (Jira, etc.)."""

    title: str
    subtitle: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)

    def get(self, path: str, default: Any = "") -> Any:
        """Resolve a fact by path.

        - ``"title"`` / ``"subtitle"`` -> the attributes.
        - ``"metadata.x"`` / ``"data.y"`` -> dotted lookups into those dicts.
        - a bare key -> ``data`` first, then ``metadata``.
        Returns ``default`` if nothing matches.
        """
        if path == "title":
            return self.title
        if path == "subtitle":
            return self.subtitle

        parts = path.split(".")
        if len(parts) > 1 and parts[0] in ("metadata", "data"):
            cur: Any = getattr(self, parts[0])
            for key in parts[1:]:
                if isinstance(cur, dict) and key in cur:
                    cur = cur[key]
                else:
                    return default
            return cur

        if path in self.data:
            return self.data[path]
        if path in self.metadata:
            return self.metadata[path]
        return default
