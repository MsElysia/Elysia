"""Build local context bundles from approved memory search results (no model calls)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .approved_memory_search import (
    ApprovedMemorySearchError,
    SearchHit,
    load_memory_store,
    resolve_memory_store_path,
    search_memory_store,
)
from .memory_candidates import text_preview

MEMORY_CONTEXT_SUBDIR = "memory_context"
CONTEXT_BUNDLE_JSON = "context_bundle.json"
CONTEXT_BUNDLE_MD = "context_bundle.md"
DEFAULT_MAX_CHARS = 6000
BUNDLE_TYPE = "approved_memory_context"
SAFETY_STATEMENT = (
    "This bundle was built from approved local memory only. "
    "No model was called. No live memory was written."
)
PROMPT_BLOCK = (
    "Use the approved memories below as context. "
    "Answer only from the provided memory unless clearly marked as general reasoning."
)


class ApprovedMemoryContextError(ApprovedMemorySearchError):
    """Raised when context bundle building cannot proceed safely."""


@dataclass
class ContextBundleReport:
    query: str
    source_memory_store: str
    output_dir: str
    json_path: str
    markdown_path: str
    result_count: int
    max_chars: int
    include_full_text: bool
    bundle: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "source_memory_store": self.source_memory_store,
            "output_dir": self.output_dir,
            "json_path": self.json_path,
            "markdown_path": self.markdown_path,
            "result_count": self.result_count,
            "max_chars": self.max_chars,
            "include_full_text": self.include_full_text,
            "bundle": self.bundle,
        }


def default_context_output_dir(dest_dir: Path) -> Path:
    return dest_dir / MEMORY_CONTEXT_SUBDIR


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _is_approved_store_record(record: Dict[str, Any]) -> bool:
    if record.get("operator_approved") is not True:
        return False
    if record.get("live_runtime_memory_written") is not False:
        return False
    if str(record.get("memory_status") or "") != "active":
        return False
    return bool(str(record.get("text") or "").strip())


def _filter_approved_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [record for record in records if _is_approved_store_record(record)]


def _truncate_text(text: str, max_len: int) -> str:
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return text[: max_len - 3] + "..."


def _result_payload(
    record: Dict[str, Any],
    hit: SearchHit,
    *,
    include_full_text: bool,
    text_budget: int,
) -> Dict[str, Any]:
    full_text = str(record.get("text") or "")
    preview = str(record.get("text_preview") or "") or text_preview(full_text)
    if include_full_text:
        body = _truncate_text(full_text, text_budget)
        body_field = "text"
    else:
        body = _truncate_text(hit.snippet or preview, text_budget)
        body_field = "snippet"

    payload: Dict[str, Any] = {
        "memory_id": hit.memory_id,
        "candidate_id": record.get("candidate_id"),
        "source_type": record.get("source_type"),
        "original_filename": record.get("original_filename"),
        "suggested_memory_type": hit.suggested_memory_type,
        "score": hit.score,
        "text_preview": preview,
        body_field: body,
        "text_sha256": record.get("text_sha256"),
        "stored_at": hit.stored_at,
    }
    return payload


def build_context_bundle_payload(
    *,
    query: str,
    source_memory_store: str,
    records_by_id: Dict[str, Dict[str, Any]],
    hits: List[SearchHit],
    max_chars: int = DEFAULT_MAX_CHARS,
    include_full_text: bool = False,
) -> Dict[str, Any]:
    remaining = max(0, max_chars)
    results: List[Dict[str, Any]] = []
    for hit in hits:
        record = records_by_id.get(hit.memory_id)
        if not record:
            continue
        if remaining <= 0:
            break
        payload = _result_payload(
            record,
            hit,
            include_full_text=include_full_text,
            text_budget=remaining,
        )
        used = len(str(payload.get("text") or payload.get("snippet") or ""))
        remaining -= used
        results.append(payload)

    return {
        "query": query,
        "generated_at": _utc_now_iso(),
        "source_memory_store": source_memory_store,
        "result_count": len(results),
        "max_chars": max_chars,
        "model_called": False,
        "embeddings_used": False,
        "live_memory_written": False,
        "bundle_type": BUNDLE_TYPE,
        "results": results,
    }


def render_context_bundle_markdown(bundle: Dict[str, Any]) -> str:
    lines = [
        "# Approved Memory Context Bundle",
        "",
        f"**Query:** {bundle.get('query', '')}",
        "",
        "## Safety",
        "",
        SAFETY_STATEMENT,
        "",
        "## Suggested Prompt",
        "",
        PROMPT_BLOCK,
        "",
        "## Results",
        "",
    ]
    results = bundle.get("results") or []
    if not results:
        lines.append("_No matching approved memories found._")
        lines.append("")
        return "\n".join(lines)

    for index, item in enumerate(results, start=1):
        lines.extend(
            [
                f"### {index}. {item.get('memory_id')}",
                "",
                f"- **Source type:** {item.get('source_type')}",
                f"- **Original file:** {item.get('original_filename')}",
                f"- **Memory type:** {item.get('suggested_memory_type')}",
                f"- **Score:** {item.get('score')}",
                f"- **Stored at:** {item.get('stored_at')}",
                "",
            ]
        )
        body = item.get("text") or item.get("snippet") or item.get("text_preview") or ""
        lines.extend([str(body), ""])
    return "\n".join(lines)


def build_approved_memory_context(
    *,
    query: str,
    dest_dir: Optional[Path] = None,
    memory_store_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    limit: Optional[int] = 5,
    max_chars: int = DEFAULT_MAX_CHARS,
    include_full_text: bool = False,
) -> ContextBundleReport:
    if not str(query or "").strip():
        raise ApprovedMemoryContextError("Query is required.")

    store_path = resolve_memory_store_path(
        dest_dir=dest_dir,
        memory_store_path=memory_store_path,
    )
    resolved_dest = (
        dest_dir.expanduser().resolve()
        if dest_dir is not None
        else store_path.parent.parent
    )
    out_dir = (
        output_dir.expanduser().resolve()
        if output_dir is not None
        else default_context_output_dir(resolved_dest)
    )

    try:
        records = _filter_approved_records(load_memory_store(store_path))
    except ApprovedMemorySearchError as exc:
        raise ApprovedMemoryContextError(str(exc)) from exc
    records_by_id = {str(item["memory_id"]): item for item in records}
    search_report = search_memory_store(records, query, limit=limit)

    bundle = build_context_bundle_payload(
        query=query.strip(),
        source_memory_store=str(store_path),
        records_by_id=records_by_id,
        hits=search_report.results,
        max_chars=max_chars,
        include_full_text=include_full_text,
    )

    json_path = out_dir / CONTEXT_BUNDLE_JSON
    md_path = out_dir / CONTEXT_BUNDLE_MD
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    md_path.write_text(
        render_context_bundle_markdown(bundle) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return ContextBundleReport(
        query=query.strip(),
        source_memory_store=str(store_path),
        output_dir=str(out_dir),
        json_path=str(json_path),
        markdown_path=str(md_path),
        result_count=bundle["result_count"],
        max_chars=max_chars,
        include_full_text=include_full_text,
        bundle=bundle,
    )
