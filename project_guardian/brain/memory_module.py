# project_guardian/brain/memory_module.py

from __future__ import annotations

import logging
from typing import Any, List, Optional

from .contracts import MemoryModule, Observation

logger = logging.getLogger(__name__)


class GuardianMemoryFacade:
    """Read/write/search against GuardianCore.memory (MemoryCore)."""

    def __init__(self, memory: Any) -> None:
        self._memory = memory

    def retrieve(self, query: str, *, limit: int = 12) -> List[str]:
        if not self._memory:
            return []
        try:
            rows = self._memory.search_memories(query, limit)  # type: ignore[attr-defined]
        except Exception as e:
            logger.debug("brain.memory retrieve search_memories: %s", e)
            return []
        out: List[str] = []
        for row in rows or []:
            if isinstance(row, dict) and row.get("thought"):
                out.append(str(row["thought"]))
            elif isinstance(row, str):
                out.append(row)
        return out[:limit]

    def remember(self, thought: str, **kwargs: Any) -> None:
        if not self._memory or not thought:
            return
        try:
            self._memory.remember(thought, **kwargs)  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning("brain.memory remember failed: %s", e)

    def search(self, keyword: str, limit: int = 8) -> List[str]:
        return self.retrieve(keyword, limit=limit)


class InMemoryBrainStore:
    """Lightweight store for tests and diagnostics without Guardian."""

    def __init__(self) -> None:
        self.entries: List[dict] = []

    def retrieve(self, query: str, *, limit: int = 12) -> List[str]:
        q = (query or "").lower()
        hits = [e["thought"] for e in self.entries if q in str(e.get("thought", "")).lower()]
        return hits[-limit:]

    def remember(self, thought: str, **kwargs: Any) -> None:
        self.entries.append({"thought": thought, **kwargs})

    def search(self, keyword: str, limit: int = 8) -> List[str]:
        return self.retrieve(keyword, limit=limit)
