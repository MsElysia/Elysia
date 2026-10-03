# project_guardian/brain/memory_module.py

from __future__ import annotations

import logging
from pathlib import Path
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


class MemoryIntelligenceBrainBridge:
    """Read memory-intelligence artifacts through the ordinary Brain memory API.

    The source-linked store is strictly read-only here. Existing Brain memory
    behavior, including any explicit writes, remains owned by ``primary``.
    """

    def __init__(self, primary: Any, intelligence_dir: Path) -> None:
        self._primary = primary
        self._intelligence_dir = Path(intelligence_dir)
        self._last_recall: List[dict[str, Any]] = []

    def retrieve(self, query: str, *, limit: int = 12) -> List[str]:
        primary_rows = list(self._primary.retrieve(query, limit=limit) or [])
        remaining = max(0, limit - len(primary_rows))
        self._last_recall = []
        if remaining:
            from project_guardian.local_ingestion.memory_intelligence import (
                query_memory_intelligence,
            )

            self._last_recall = query_memory_intelligence(
                self._intelligence_dir,
                query,
                limit=remaining,
            )
        linked = [self._format_snippet(item) for item in self._last_recall]
        return (primary_rows + linked)[:limit]

    @staticmethod
    def _format_snippet(item: dict[str, Any]) -> str:
        highlights = item.get("highlights") or []
        text = ""
        if highlights and isinstance(highlights[0], dict):
            text = str(highlights[0].get("surrounding_context") or "")
        if not text:
            text = str(item.get("summary") or "")
        reason_types = [
            str(reason.get("type"))
            for reason in item.get("recall_reasons") or []
            if isinstance(reason, dict) and reason.get("type")
        ]
        return (
            f"[source_id={item.get('source_id')} chunk_id={item.get('chunk_id')} "
            f"recall={','.join(reason_types)}] {text}"
        ).strip()

    def recall_evidence(self) -> List[dict[str, Any]]:
        """Return detached machine-readable evidence for the latest retrieval."""
        import copy

        return copy.deepcopy(self._last_recall)

    def expand_highlight(self, highlight_id: str, *, context_bytes: int = 240) -> dict[str, str]:
        from project_guardian.local_ingestion.memory_intelligence import (
            expand_persisted_highlight,
        )

        return expand_persisted_highlight(
            self._intelligence_dir,
            highlight_id,
            context_bytes=context_bytes,
        )

    def remember(self, thought: str, **kwargs: Any) -> None:
        self._primary.remember(thought, **kwargs)

    def search(self, keyword: str, limit: int = 8) -> List[str]:
        return self.retrieve(keyword, limit=limit)
