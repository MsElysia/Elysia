"""Explicit, read-only access to the existing Issue #95 ingestion artifacts.

No ingestion, MemoryCore construction, embeddings, providers or persistence.
This bridge supplies evidence to the existing Brain planner; it grants no action
authority and never treats recalled text as a command or operator approval.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from project_guardian.local_ingestion.memory_intelligence import (
    MemoryIntelligenceError,
    expand_persisted_highlight,
    query_memory_intelligence,
)


class ReadOnlyMemoryIntelligenceBridge:
    """Memory retrieval protocol without a memory-write method or a second store."""

    def __init__(self, dest_dir: Path) -> None:
        self._dest = Path(dest_dir).expanduser().resolve()
        if not self._dest.is_dir():
            raise MemoryIntelligenceError("explicit ingestion destination must exist")
        self._query = ""
        self._limit = 0
        self._rows: list[dict[str, Any]] = []

    def retrieve(self, query: str, *, limit: int = 10) -> list[str]:
        # Clear old evidence before validation so a failed query cannot expose
        # a previous successful query as evidence for the failed request.
        self._query, self._limit, self._rows = "", 0, []
        if type(limit) is not int or not 0 <= limit <= 10:
            raise MemoryIntelligenceError("bridge limit must be an integer from 0 to 10")
        try:
            rows = query_memory_intelligence(self._dest, query, limit=limit, validate_summaries=True)
        except (OSError, TypeError, ValueError) as exc:
            raise MemoryIntelligenceError("read-only bridge retrieval failed") from exc
        self._query, self._limit, self._rows = query, limit, rows
        # Feed byte-validated highlights, not the independently editable
        # summary field, into planner context.
        return [
            f"[source={row['source_id']} chunk={row['chunk_id']}] "
            + " ".join(item["text"] for item in row["highlights"])
            for row in rows
        ]

    def search(self, keyword: str, limit: int = 8) -> list[str]:
        return self.retrieve(keyword, limit=limit)

    def recall_evidence(self) -> dict[str, Any]:
        """Return a detached copy of exactly the most recent validated recall."""
        return deepcopy({
            "query": self._query,
            "read_only": True,
            "hits": self._rows,
            "relevant_context_ids": [row["chunk_id"] for row in self._rows],
        })

    def expand(self, highlight_id: str) -> dict[str, str]:
        """Revalidate recall before expanding one of its highlights to raw text."""
        if type(highlight_id) is not str or not highlight_id or not self._query:
            raise MemoryIntelligenceError("a recalled highlight is required")
        query, limit = self._query, self._limit
        self.retrieve(query, limit=limit)
        matching = [
            row for row in self._rows
            if any(item["highlight_id"] == highlight_id for item in row["highlights"])
        ]
        if len(matching) != 1:
            raise MemoryIntelligenceError("highlight is not in the current recall")
        try:
            expanded = expand_persisted_highlight(self._dest, highlight_id)
        except (OSError, TypeError, ValueError) as exc:
            raise MemoryIntelligenceError("read-only bridge expansion failed") from exc
        row = matching[0]
        if expanded["source_id"] != row["source_id"] or expanded["chunk_id"] != row["chunk_id"]:
            raise MemoryIntelligenceError("expanded highlight recall linkage mismatch")
        return expanded


class OfflineRetrievalRouter:
    """No provider selection, configuration probe, or model invocation."""

    def choose_backend(self, **kwargs: Any) -> tuple[str, str]:
        return "offline", "read_only_memory_intelligence_preview"


def run_memory_intelligence_preview(dest_dir: Path, query: str) -> Any:
    """Non-test caller of the normal Brain -> planner -> TDA dry-run path.

    No global runtime/configuration flag is changed. All trace data stays in
    memory; the caller may inspect/export it under its own authority.
    """
    from .contracts import Observation
    from .pipeline import BrainPipeline

    bridge = ReadOnlyMemoryIntelligenceBridge(dest_dir)
    pipeline = BrainPipeline(read_only_retrieval=bridge)
    return pipeline.run(
        Observation("memory_intelligence_preview", query),
        context={"dry_run": True, "persist_trace": False, "use_think_decide_act": True},
    )
