# project_guardian/memory_ranking/visibility.py
"""Read-only memory ranking summaries for operator dashboards (no store mutation)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from project_guardian.conversation_store import ConversationStore, redact_chat_text
from project_guardian.memory_ranking.ranking import (
    MemoryCompressionProposal,
    MemoryRankingConfig,
    RankedMemory,
    build_ranking_report,
    get_memory_ranking_config,
    memory_dict_to_input,
    redact_memory_text,
)

logger = logging.getLogger(__name__)

DEFAULT_TOP_LIMIT = 10
_MAX_CONVERSATIONS = 3
_MAX_MESSAGES_PER_CONV = 20
_MAX_MESSAGES_TOTAL = 40
_PREVIEW_CHARS = 220
_SUMMARY_PREVIEW_CHARS = 280


def summarize_ranked_memory(ranked: RankedMemory, *, preview_chars: int = _PREVIEW_CHARS) -> Dict[str, Any]:
    text = redact_memory_text(ranked.text or "")
    sc = ranked.scores
    preview = text[:preview_chars]
    return {
        "memory_id": str(ranked.memory_id or ""),
        "memory_value_score": round(float(ranked.memory_value_score), 4),
        "preview": preview,
        "text_preview": preview,
        "scores": {
            "relevance": round(float(sc.relevance_score), 3),
            "recency": round(float(sc.recency_score), 3),
            "frequency": round(float(sc.frequency_score), 3),
            "user_importance": round(float(sc.user_importance_score), 3),
            "retention_priority": round(float(sc.retention_priority), 3),
        },
    }


def summarize_compression_proposal(prop: MemoryCompressionProposal) -> Dict[str, Any]:
    summary = redact_memory_text(prop.proposed_summary or "")
    return {
        "memory_id": str(prop.memory_id or ""),
        "action": str(prop.action or ""),
        "reason": str(prop.reason or "")[:240],
        "dry_run": bool(prop.dry_run),
        "advisory_only": True,
        "original_value_score": round(float(prop.original_value_score), 4),
        "risk_of_loss": round(float(prop.risk_of_loss), 4),
        "current_length": int(prop.current_length),
        "proposed_summary_preview": summary[:_SUMMARY_PREVIEW_CHARS],
        "proposed_summary": summary[:_SUMMARY_PREVIEW_CHARS],
    }


def _proposal_counts(proposals: List[MemoryCompressionProposal]) -> Dict[str, int]:
    counts = {"keep_full": 0, "compress": 0, "archive": 0, "review_manually": 0}
    for p in proposals:
        act = str(p.action or "").strip().lower()
        if act in counts:
            counts[act] += 1
    return counts


def _load_conversation_memory_rows(
    store: ConversationStore,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []
    try:
        convs = store.list_conversations()[:_MAX_CONVERSATIONS]
    except Exception as exc:
        logger.warning("memory ranking visibility: list_conversations failed: %s", exc)
        warnings.append(f"conversation_list_error:{exc}")
        return [], warnings

    for conv in convs:
        cid = str(conv.get("conversation_id") or "")
        if not cid:
            continue
        try:
            msgs = store.list_messages(cid, limit=_MAX_MESSAGES_PER_CONV)
        except Exception as exc:
            warnings.append(f"conversation_read_error:{cid}:{exc}")
            continue
        for msg in msgs:
            content = redact_chat_text(str(msg.get("content") or ""))
            if not content.strip():
                continue
            rows.append(
                {
                    "id": str(msg.get("message_id") or f"{cid}-{len(rows)}"),
                    "thought": content,
                    "created_at": msg.get("created_at"),
                    "source": f"conversation:{msg.get('role') or 'unknown'}",
                    "access_count": 1,
                }
            )
        if len(rows) >= _MAX_MESSAGES_TOTAL:
            break

    if len(rows) > _MAX_MESSAGES_TOTAL:
        rows = rows[-_MAX_MESSAGES_TOTAL:]
    return rows, warnings


def _load_brain_trace_memory_rows() -> Tuple[List[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    rows: List[Dict[str, Any]] = []
    try:
        from project_guardian.brain.config import get_brain_pipeline_config

        path: Path = get_brain_pipeline_config().trace_path
        if not path.is_file():
            return [], warnings
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            warnings.append("brain_trace_not_object")
            return [], warnings

        snippets = raw.get("memory_snippets")
        if isinstance(snippets, list):
            for i, item in enumerate(snippets[:15]):
                if isinstance(item, str) and item.strip():
                    rows.append(
                        {
                            "id": f"brain-snippet-{i}",
                            "thought": redact_memory_text(item),
                            "source": "brain_trace_snippet",
                        }
                    )

        lesson = raw.get("lesson_preview")
        if isinstance(lesson, str) and lesson.strip():
            rows.append(
                {
                    "id": "brain-lesson-preview",
                    "thought": redact_memory_text(lesson),
                    "source": "brain_trace_lesson",
                }
            )
    except Exception as exc:
        logger.warning("memory ranking visibility: brain trace read failed: %s", exc)
        warnings.append(f"brain_trace_error:{exc}")
    return rows, warnings


def build_memory_ranking_summary(
    report=None,
    *,
    cfg=None,
    config=None,
    sample_source: str = "none",
    limit: int = DEFAULT_TOP_LIMIT,
    extra_warnings: Optional[List[str]] = None,
    memories: Optional[List[Any]] = None,
    conversation_store: Optional[ConversationStore] = None,
    current_goal_text: str = "operator dashboard memory review",
) -> Dict[str, Any]:
    """Shape a ranking report into the API summary dict (read-only metadata)."""
    cfg = cfg or config or get_memory_ranking_config()
    if report is None:
        rows: List[Dict[str, Any]] = []
        if conversation_store is not None:
            rows, conv_warnings = _load_conversation_memory_rows(conversation_store)
            extra_warnings = list(extra_warnings or []) + conv_warnings
            if rows:
                sample_source = "conversation_store"
        else:
            provided = list(memories or [])[:100]
            if provided:
                sample_source = "sample"
            for i, item in enumerate(provided):
                if isinstance(item, dict):
                    row = dict(item)
                else:
                    row = {"id": f"sample-{i}", "thought": str(item or "")}
                if "thought" in row:
                    row["thought"] = redact_memory_text(str(row.get("thought") or ""))
                if "text" in row:
                    row["text"] = redact_memory_text(str(row.get("text") or ""))
                rows.append(row)
        items = [memory_dict_to_input(row, i) for i, row in enumerate(rows)]
        report = build_ranking_report(items, cfg, current_goal_text=current_goal_text)
    lim = max(1, min(int(limit), 50))
    proposals = list(report.proposals or [])
    ranked = list(report.ranked or [])
    warnings = list(extra_warnings or []) + list(report.warnings or [])

    compress_actions = frozenset({"compress", "archive", "review_manually"})
    compression_rows = [p for p in proposals if str(p.action) in compress_actions]

    return {
        "available": True,
        "enabled": bool(cfg.enabled),
        "dry_run": bool(cfg.dry_run),
        "mutation_allowed": False,
        "delete_allowed": False,
        "sample_source": sample_source,
        "memory_count": len(ranked),
        "proposal_counts": _proposal_counts(proposals),
        "top_ranked": [summarize_ranked_memory(r) for r in ranked[:lim]],
        "compression_proposals": [
            summarize_compression_proposal(p) for p in compression_rows[:lim]
        ],
        "warnings": warnings[:20],
    }


def load_memory_ranking_visibility(
    *,
    conversation_store: Optional[ConversationStore] = None,
    limit: int = DEFAULT_TOP_LIMIT,
    current_goal_text: str = "operator dashboard memory review",
) -> Dict[str, Any]:
    """
    Load recent safe memory inputs, rank them, and return an advisory summary.

    Does not write, compress, archive, or delete any memory.
    """
    cfg = get_memory_ranking_config()
    base_warnings: List[str] = []
    if not cfg.enabled:
        base_warnings.append("memory_ranking.enabled is false; showing advisory preview only.")

    memory_rows: List[Dict[str, Any]] = []
    sample_source = "none"
    scoped_store = conversation_store is not None

    store = conversation_store
    if store is None:
        from project_guardian.conversation_store import get_default_conversation_store

        store = get_default_conversation_store()

    conv_rows, conv_warn = _load_conversation_memory_rows(store)
    base_warnings.extend(conv_warn)
    if conv_rows:
        memory_rows = conv_rows
        sample_source = "conversation_store"

    if not memory_rows and not scoped_store:
        brain_rows, brain_warn = _load_brain_trace_memory_rows()
        base_warnings.extend(brain_warn)
        if brain_rows:
            memory_rows = brain_rows
            sample_source = "brain_trace"

    if not memory_rows:
        return build_memory_ranking_summary(
            build_ranking_report([], cfg, current_goal_text=current_goal_text),
            cfg=cfg,
            sample_source="none",
            limit=limit,
            extra_warnings=base_warnings
            + (["no_memory_source_available"] if sample_source == "none" else []),
        )

    items = [memory_dict_to_input(row, i) for i, row in enumerate(memory_rows)]
    report = build_ranking_report(items, cfg, current_goal_text=current_goal_text)
    return build_memory_ranking_summary(
        report,
        cfg=cfg,
        sample_source=sample_source,
        limit=limit,
        extra_warnings=base_warnings,
    )
