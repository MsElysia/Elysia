# project_guardian/safe_stack/responses.py
"""Framework-neutral response builders for mirrored safe-stack API routes."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from project_guardian.conversation_store import (
    CHAT_LIST_MESSAGES_DEFAULT,
    ConversationStore,
    sanitize_conversation_id,
)
from project_guardian.self_improvement.proposal_queue import ProposalQueue, sanitize_proposal

logger = logging.getLogger(__name__)

ResponsePayload = Tuple[Dict[str, Any], int]

_EXPORT_KEYS = frozenset({"proposal_id", "target", "prompt", "copy_safe", "warnings"})

_MEMORY_RANKING_ERROR_FALLBACK: Dict[str, Any] = {
    "available": True,
    "enabled": False,
    "dry_run": True,
    "mutation_allowed": False,
    "delete_allowed": False,
    "sample_source": "none",
    "memory_count": 0,
    "proposal_counts": {
        "keep_full": 0,
        "compress": 0,
        "archive": 0,
        "review_manually": 0,
    },
    "top_ranked": [],
    "compression_proposals": [],
    "warnings": [],
}


def _store_unavailable() -> ResponsePayload:
    return {"success": False, "error": "conversation store unavailable"}, 503


def _history_rows(store: ConversationStore, conversation_id: str, *, limit: int) -> List[Dict[str, Any]]:
    cid = sanitize_conversation_id(conversation_id)
    rows = store.list_messages(cid, limit=limit)
    return [
        {
            "role": r.get("role"),
            "content": r.get("content"),
            "created_at": r.get("created_at"),
            "message_id": r.get("message_id"),
        }
        for r in rows
    ]


def build_brain_trace_latest_response(
    *,
    config: Optional[Any] = None,
) -> ResponsePayload:
    try:
        from project_guardian.brain.config import get_brain_pipeline_config
        from project_guardian.brain.trace_visibility import load_latest_brain_trace_summary

        cfg = config or get_brain_pipeline_config()
        return load_latest_brain_trace_summary(config=cfg), 200
    except Exception as exc:
        logger.warning("brain trace latest response failed: %s", exc)
        return (
            {
                "available": True,
                "enabled": False,
                "dry_run": True,
                "trace_path": "",
                "trace_exists": False,
                "warnings": [str(exc)[:200]],
                "message": "Unable to load brain trace summary.",
            },
            200,
        )


def build_memory_ranking_summary_response(
    *,
    conversation_store: Optional[ConversationStore],
    limit: int = 10,
) -> ResponsePayload:
    try:
        from project_guardian.memory_ranking.visibility import load_memory_ranking_visibility

        lim = min(max(int(limit), 1), 50)
        summary = load_memory_ranking_visibility(conversation_store=conversation_store, limit=lim)
        return summary, 200
    except Exception as exc:
        logger.warning("memory ranking summary response failed: %s", exc)
        body = dict(_MEMORY_RANKING_ERROR_FALLBACK)
        body["warnings"] = [str(exc)[:200]]
        return body, 200


def build_prompt_contracts_status_response(
    *,
    config: Optional[Any] = None,
    trace_summary: Optional[Dict[str, Any]] = None,
    trace_path: Optional[Path] = None,
) -> ResponsePayload:
    try:
        from project_guardian.prompt_contracts.status import build_prompt_contract_status

        return (
            build_prompt_contract_status(
                config=config,
                trace_summary=trace_summary,
                trace_path=trace_path,
            ),
            200,
        )
    except Exception as exc:
        logger.warning("prompt-contracts status response failed: %s", exc)
        return {"available": False, "error": str(exc)[:400]}, 500


def build_self_improvement_proposals_list_response(
    queue: ProposalQueue,
    *,
    limit: int = 50,
) -> ResponsePayload:
    try:
        lim = min(max(int(limit), 1), 200)
        rows = queue.list_latest(limit=lim)
        items = [sanitize_proposal(p, for_api=True) for p in rows]
        return {"success": True, "proposals": items, "count": len(items)}, 200
    except Exception as exc:
        logger.warning("self-improvement list response failed: %s", exc)
        return {"success": False, "error": str(exc)[:400]}, 500


def build_self_improvement_proposal_detail_response(
    queue: ProposalQueue,
    proposal_id: str,
) -> ResponsePayload:
    try:
        p = queue.get(proposal_id)
        if p is None:
            return {"success": False, "error": "not_found"}, 404
        return {"success": True, "proposal": sanitize_proposal(p, for_api=True)}, 200
    except Exception as exc:
        logger.warning("self-improvement get response failed: %s", exc)
        return {"success": False, "error": str(exc)[:400]}, 500


def build_self_improvement_proposal_status_update_response(
    queue: ProposalQueue,
    proposal_id: str,
    status: str,
    *,
    note: Optional[str] = None,
) -> ResponsePayload:
    try:
        st = str(status or "").strip().lower()
        ok, msg = queue.update_status(
            proposal_id,
            st,
            note=str(note) if note is not None else None,
        )
        if not ok:
            code = 404 if msg == "not_found" else 400
            return {"success": False, "error": msg}, code
        p = queue.get(proposal_id)
        return (
            {
                "success": True,
                "proposal_id": str(proposal_id),
                "status": st,
                "proposal": sanitize_proposal(p, for_api=True) if p else None,
            },
            200,
        )
    except Exception as exc:
        logger.warning("self-improvement status response failed: %s", exc)
        return {"success": False, "error": str(exc)[:400]}, 500


def build_self_improvement_prompt_export_response(
    queue: ProposalQueue,
    proposal_id: str,
    *,
    target: str = "cursor",
) -> ResponsePayload:
    """Normalized envelope: success + proposal_id, target, prompt, copy_safe, warnings."""
    try:
        from project_guardian.self_improvement.prompt_export import (
            normalize_target,
            proposal_prompt_to_dict,
        )

        try:
            normalize_target(target)
        except ValueError:
            return {"success": False, "error": "unknown_target"}, 400
        p = queue.get(proposal_id)
        if p is None:
            return {"success": False, "error": "not_found"}, 404
        payload = proposal_prompt_to_dict(p, target=target)
        body = {"success": True}
        for key in _EXPORT_KEYS:
            if key in payload:
                body[key] = payload[key]
        return body, 200
    except Exception as exc:
        logger.warning("self-improvement export_prompt response failed: %s", exc)
        return {"success": False, "error": str(exc)[:400]}, 500


def build_conversations_list_response(store: Optional[ConversationStore]) -> ResponsePayload:
    if store is None:
        return _store_unavailable()
    try:
        return {"success": True, "conversations": store.list_conversations()}, 200
    except Exception as exc:
        logger.warning("conversations list response failed: %s", exc)
        return {"success": False, "error": str(exc)[:400]}, 500


def build_conversation_create_response(store: Optional[ConversationStore]) -> ResponsePayload:
    if store is None:
        return _store_unavailable()
    try:
        cid = store.new_conversation_id()
        return {"success": True, "conversation_id": cid, "history": []}, 200
    except Exception as exc:
        logger.warning("conversations create response failed: %s", exc)
        return {"success": False, "error": str(exc)[:400]}, 500


def build_conversation_detail_response(
    store: Optional[ConversationStore],
    conversation_id: str,
    *,
    message_limit: int = 50,
) -> ResponsePayload:
    if store is None:
        return _store_unavailable()
    try:
        cid = sanitize_conversation_id(conversation_id)
        messages = store.list_messages(cid, limit=message_limit)
        return {"success": True, "conversation_id": cid, "messages": messages}, 200
    except Exception as exc:
        logger.warning("conversations get response failed: %s", exc)
        return {"success": False, "error": str(exc)[:400]}, 500


def build_conversation_delete_response(
    store: Optional[ConversationStore],
    conversation_id: str,
) -> ResponsePayload:
    if store is None:
        return _store_unavailable()
    try:
        cid = sanitize_conversation_id(conversation_id)
        store.delete_conversation(cid)
        return {"success": True, "conversation_id": cid}, 200
    except Exception as exc:
        logger.warning("conversations delete response failed: %s", exc)
        return {"success": False, "error": str(exc)[:400]}, 500


def build_chat_history_response(
    store: Optional[ConversationStore],
    conversation_id: str,
    *,
    limit: Optional[int] = None,
) -> ResponsePayload:
    if store is None:
        return _store_unavailable()
    try:
        cid = sanitize_conversation_id(conversation_id)
        lim = limit if limit is not None else max(CHAT_LIST_MESSAGES_DEFAULT, 20)
        history = _history_rows(store, cid, limit=lim)
        return {"success": True, "conversation_id": cid, "history": history}, 200
    except Exception as exc:
        logger.warning("chat history response failed: %s", exc)
        return {"success": False, "error": str(exc)[:400]}, 500


def build_operator_confirmations_list_response(
    *,
    store_path: Optional[Any] = None,
    limit: Optional[int] = None,
    conversation_id: Optional[str] = None,
    status_filter: Optional[str] = None,
) -> ResponsePayload:
    """Read-only operator confirmation diagnostics (no mutation)."""
    try:
        from project_guardian.governance.operator_confirmation_visibility import (
            build_operator_confirmations_list_payload,
        )

        path = Path(str(store_path)) if store_path else None
        body = build_operator_confirmations_list_payload(
            store_path=path,
            limit=limit,
            conversation_id=conversation_id,
            status_filter=status_filter,
        )
        return body, 200
    except Exception as exc:
        logger.warning("operator-confirmations list response failed: %s", exc)
        return {
            "available": False,
            "read_only": True,
            "live_execution_enabled": False,
            "autonomy_enabled": False,
            "confirmations": [],
            "counts": {
                "pending": 0,
                "used": 0,
                "expired": 0,
                "revoked": 0,
                "invalid": 0,
            },
            "warnings": [str(exc)[:120]],
        }, 500


def build_operator_confirmation_detail_response(
    operator_confirmation_id: str,
    *,
    store_path: Optional[Any] = None,
) -> ResponsePayload:
    """Read-only single confirmation detail (no mutation)."""
    try:
        from project_guardian.governance.operator_confirmation_visibility import (
            build_operator_confirmation_detail_payload,
        )

        path = Path(str(store_path)) if store_path else None
        return build_operator_confirmation_detail_payload(
            operator_confirmation_id,
            store_path=path,
        )
    except Exception as exc:
        logger.warning("operator-confirmations detail response failed: %s", exc)
        return {
            "available": False,
            "read_only": True,
            "found": False,
            "error": str(exc)[:200],
        }, 500


def build_chat_history_clear_response(
    store: Optional[ConversationStore],
    conversation_id: str,
) -> ResponsePayload:
    if store is None:
        return _store_unavailable()
    try:
        cid = sanitize_conversation_id(conversation_id)
        store.delete_conversation(cid)
        return {"success": True, "conversation_id": cid, "history": []}, 200
    except Exception as exc:
        logger.warning("chat history clear response failed: %s", exc)
        return {"success": False, "error": str(exc)[:400]}, 500
