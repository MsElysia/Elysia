"""Read-only search and recall over the approved local memory store JSONL."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .approved_memory_store import default_memory_store_path
from .memory_candidates import text_preview

SNIPPET_MAX = 200


class ApprovedMemorySearchError(Exception):
    """Raised when approved memory search cannot proceed safely."""


@dataclass
class SearchHit:
    memory_id: str
    score: int
    match_count: int
    suggested_memory_type: Optional[str]
    original_filename: Optional[str]
    snippet: str
    stored_at: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "score": self.score,
            "match_count": self.match_count,
            "suggested_memory_type": self.suggested_memory_type,
            "original_filename": self.original_filename,
            "snippet": self.snippet,
            "stored_at": self.stored_at,
        }


@dataclass
class SearchReport:
    memory_store_path: str
    query: str
    count: int
    results: List[SearchHit] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_store_path": self.memory_store_path,
            "query": self.query,
            "count": self.count,
            "results": [item.to_dict() for item in self.results],
        }


@dataclass
class ListReport:
    memory_store_path: str
    limit: int
    count: int
    results: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_store_path": self.memory_store_path,
            "limit": self.limit,
            "count": self.count,
            "results": self.results,
        }


@dataclass
class StatsReport:
    memory_store_path: str
    total_records: int
    active_records: int
    memory_types: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_store_path": self.memory_store_path,
            "total_records": self.total_records,
            "active_records": self.active_records,
            "memory_types": self.memory_types,
        }


def resolve_memory_store_path(
    *,
    dest_dir: Optional[Path] = None,
    memory_store_path: Optional[Path] = None,
) -> Path:
    if memory_store_path is not None:
        return memory_store_path.expanduser().resolve()
    if dest_dir is None:
        raise ApprovedMemorySearchError(
            "Provide --dest-dir or --memory-store to locate the approved memory store."
        )
    return default_memory_store_path(dest_dir.expanduser().resolve())


def load_memory_store(memory_store_path: Path) -> List[Dict[str, Any]]:
    path = memory_store_path.expanduser().resolve()
    if not path.is_file():
        raise ApprovedMemorySearchError(f"Memory store not found: {path}")

    records: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    item = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ApprovedMemorySearchError(
                        f"Malformed JSON in {path} at line {line_no}: {exc}"
                    ) from exc
                if not isinstance(item, dict):
                    raise ApprovedMemorySearchError(
                        f"Expected JSON object in {path} at line {line_no}."
                    )
                memory_id = str(item.get("memory_id") or "").strip()
                if not memory_id:
                    raise ApprovedMemorySearchError(
                        f"Memory record missing memory_id in {path} at line {line_no}."
                    )
                records.append(item)
    except OSError as exc:
        raise ApprovedMemorySearchError(f"Unable to read memory store {path}: {exc}") from exc
    return records


def _query_terms(query: str) -> List[str]:
    return [term for term in re.split(r"\s+", query.strip().lower()) if term]


def _searchable_blob(record: Dict[str, Any]) -> str:
    parts = [
        str(record.get("text") or ""),
        str(record.get("text_preview") or ""),
        str(record.get("original_filename") or ""),
        str(record.get("suggested_memory_type") or ""),
        " ".join(str(tag) for tag in (record.get("tags") or [])),
    ]
    return " ".join(parts).lower()


def _make_snippet(text: str, terms: Sequence[str]) -> str:
    if not text:
        return ""
    if not terms:
        return text_preview(text, max_len=SNIPPET_MAX)
    lower = text.lower()
    for term in terms:
        idx = lower.find(term)
        if idx >= 0:
            start = max(0, idx - 40)
            end = min(len(text), idx + len(term) + 80)
            snippet = text[start:end].strip()
            if start > 0:
                snippet = "..." + snippet
            if end < len(text):
                snippet = snippet + "..."
            return snippet
    return text_preview(text, max_len=SNIPPET_MAX)


def _score_record(record: Dict[str, Any], terms: Sequence[str]) -> int:
    if not terms:
        return 0
    blob = _searchable_blob(record)
    score = 0
    for term in terms:
        if term in blob:
            score += blob.count(term)
    return score


def search_memory_store(
    records: List[Dict[str, Any]],
    query: str,
    *,
    limit: Optional[int] = None,
) -> SearchReport:
    terms = _query_terms(query)
    hits: List[SearchHit] = []
    for record in records:
        score = _score_record(record, terms)
        if score <= 0:
            continue
        text = str(record.get("text") or "")
        hits.append(
            SearchHit(
                memory_id=str(record["memory_id"]),
                score=score,
                match_count=len([term for term in terms if term in _searchable_blob(record)]),
                suggested_memory_type=record.get("suggested_memory_type"),
                original_filename=record.get("original_filename"),
                snippet=_make_snippet(text, terms),
                stored_at=record.get("stored_at"),
            )
        )
    hits.sort(key=lambda item: (-item.score, item.stored_at or "", item.memory_id))
    if limit is not None:
        hits = hits[: max(0, limit)]
    return SearchReport(
        memory_store_path="",
        query=query,
        count=len(hits),
        results=hits,
    )


def show_memory_record(
    records: List[Dict[str, Any]],
    memory_id: str,
) -> Dict[str, Any]:
    for record in records:
        if str(record.get("memory_id") or "") == memory_id:
            return dict(record)
    raise ApprovedMemorySearchError(f"Memory not found: {memory_id}")


def list_recent_memories(
    records: List[Dict[str, Any]],
    *,
    limit: int = 10,
) -> ListReport:
    ordered = sorted(
        records,
        key=lambda item: (str(item.get("stored_at") or ""), str(item.get("memory_id") or "")),
        reverse=True,
    )
    limited = ordered[: max(0, limit)]
    results = [
        {
            "memory_id": item.get("memory_id"),
            "stored_at": item.get("stored_at"),
            "suggested_memory_type": item.get("suggested_memory_type"),
            "original_filename": item.get("original_filename"),
            "text_preview": item.get("text_preview") or text_preview(str(item.get("text") or "")),
        }
        for item in limited
    ]
    return ListReport(
        memory_store_path="",
        limit=limit,
        count=len(results),
        results=results,
    )


def memory_store_stats(records: List[Dict[str, Any]]) -> StatsReport:
    memory_types: Dict[str, int] = {}
    active_records = 0
    for record in records:
        if str(record.get("memory_status") or "") == "active":
            active_records += 1
        key = str(record.get("suggested_memory_type") or "unknown")
        memory_types[key] = memory_types.get(key, 0) + 1
    return StatsReport(
        memory_store_path="",
        total_records=len(records),
        active_records=active_records,
        memory_types=memory_types,
    )
