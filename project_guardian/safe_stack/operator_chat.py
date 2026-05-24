# project_guardian/safe_stack/operator_chat.py
"""Framework-neutral operator chat turn orchestration (no HTTP, no LLM calls)."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from project_guardian.conversation_store import (
    ConversationStore,
    build_recent_transcript,
    redact_chat_text,
    sanitize_conversation_id,
)

logger = logging.getLogger(__name__)

BRAIN_TRACE_METADATA_KEYS = frozenset(
    {
        "brain_trace_enabled",
        "brain_trace_id",
        "brain_trace_path",
        "brain_dry_run",
        "brain_risk_level",
        "brain_tda_used",
        "brain_execution_success",
        "brain_transition_count",
        "brain_last_transition",
        "brain_trace_error",
        "brain_live_execution_guard_allowed",
        "brain_live_execution_guard_reasons",
        "brain_live_execution_guard_forced_dry_run",
        "brain_live_execution_guard_audit_ok",
    }
)

BRAIN_STORAGE_METADATA_KEYS = frozenset(
    {
        "brain_trace_enabled",
        "brain_trace_id",
        "brain_dry_run",
        "brain_tda_used",
        "brain_risk_level",
        "brain_execution_success",
        "brain_transition_count",
        "brain_last_transition",
        "brain_trace_error",
        "brain_live_execution_guard_allowed",
        "brain_live_execution_guard_reasons",
        "brain_live_execution_guard_forced_dry_run",
        "brain_live_execution_guard_audit_ok",
    }
)

BrainTraceCallback = Callable[[str, str], Dict[str, Any]]
AfterPersistCallback = Callable[
    [str, str, str, Dict[str, Any], Dict[str, Any]],
    None,
]


class OperatorChatResponderError(Exception):
    """Host responder signals failure; assistant message must not be persisted."""

    def __init__(self, error: str):
        super().__init__(error)
        self.error = str(error or "responder_failed")[:400]


@dataclass(frozen=True)
class OperatorChatRequest:
    """Input passed to the host-owned responder callback."""

    message: str
    conversation_id: str
    composed_prompt: str
    history_context: "OperatorChatHistoryContext"
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_entrypoint: str = "operator_chat"
    dry_run: bool = True


@dataclass(frozen=True)
class OperatorChatHistoryContext:
    conversation_id: str
    history_rows: List[Dict[str, Any]]
    transcript: str
    composed_prompt: str
    message_count: int
    transcript_chars: int


@dataclass(frozen=True)
class OperatorChatBrainTraceResult:
    metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


@dataclass
class OperatorChatResult:
    ok: bool
    conversation_id: str
    reply: str = ""
    history_context: Optional[OperatorChatHistoryContext] = None
    user_message_id: str = ""
    assistant_message_id: str = ""
    brain_metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OperatorChatResponderResult:
    reply_text: str
    extra_fields: Dict[str, Any] = field(default_factory=dict)


Responder = Callable[[OperatorChatRequest], OperatorChatResponderResult]


def normalize_operator_conversation_id(
    conversation_id: Optional[str],
    *,
    default_id: str = "control_panel",
    generate_if_missing: bool = False,
    conversation_store: Optional[ConversationStore] = None,
) -> str:
    """Normalize or allocate a conversation id (never empty after sanitize)."""
    if conversation_id is None or not str(conversation_id).strip():
        if generate_if_missing and conversation_store is not None:
            return sanitize_conversation_id(conversation_store.new_conversation_id())
        if generate_if_missing:
            return sanitize_conversation_id(f"conv_{uuid.uuid4().hex[:24]}")
        return sanitize_conversation_id(default_id)
    return sanitize_conversation_id(conversation_id)


def sanitize_operator_chat_metadata(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Allowlisted brain keys + redacted scalar extras safe for ConversationStore metadata."""
    out: Dict[str, Any] = {}
    for key, value in (meta or {}).items():
        k = str(key)[:64]
        if k in BRAIN_STORAGE_METADATA_KEYS:
            if isinstance(value, (dict, list)):
                continue
            if isinstance(value, str):
                out[k] = redact_chat_text(value)[:400]
            elif isinstance(value, (int, float, bool)) or value is None:
                out[k] = value
        elif isinstance(value, str):
            out[k] = redact_chat_text(value)[:400]
        elif isinstance(value, (int, float, bool)) or value is None:
            out[k] = value
    return out


def merge_brain_trace_metadata(
    raw: Optional[Dict[str, Any]],
) -> tuple[Dict[str, Any], List[str]]:
    """Compact brain metadata for API/storage; strip nested/raw trace blobs."""
    warnings: List[str] = []
    merged: Dict[str, Any] = {}
    for key, value in (raw or {}).items():
        k = str(key)
        if k not in BRAIN_TRACE_METADATA_KEYS:
            if k.startswith("brain_") and isinstance(value, (dict, list)):
                warnings.append(f"dropped_nested_brain_field:{k}")
            continue
        if isinstance(value, (dict, list)):
            warnings.append(f"dropped_nested_brain_field:{k}")
            continue
        if isinstance(value, str):
            merged[k] = redact_chat_text(value)[:400]
        elif isinstance(value, (int, float, bool)) or value is None:
            merged[k] = value
    return merged, warnings


def default_fail_open_brain_trace(
    brain_trace_callback: Optional[BrainTraceCallback],
    message: str,
    http_context: str = "general",
) -> OperatorChatBrainTraceResult:
    """Invoke optional brain trace callback; never raise."""
    if brain_trace_callback is None:
        return OperatorChatBrainTraceResult()
    try:
        raw = brain_trace_callback(message, http_context) or {}
        meta, merge_warnings = merge_brain_trace_metadata(raw)
        return OperatorChatBrainTraceResult(metadata=meta, warnings=list(merge_warnings))
    except Exception as exc:
        logger.warning("operator chat brain trace failed (fail-open): %s", exc)
        meta = {"brain_trace_error": str(exc)[:400]}
        return OperatorChatBrainTraceResult(
            metadata=meta,
            warnings=[f"brain_trace_failed:{str(exc)[:200]}"],
        )


def build_operator_history_context(
    store: ConversationStore,
    conversation_id: str,
    message: str,
    *,
    history_limit: int = 20,
    history_char_limit: int = 8000,
) -> OperatorChatHistoryContext:
    """Load bounded prior messages and build composed prompt (excludes current turn)."""
    lim = max(1, min(int(history_limit), 200))
    rows = store.get_recent_context(conversation_id, limit=lim)
    transcript = build_recent_transcript(
        rows,
        max_messages=lim,
        max_chars=max(1, int(history_char_limit)),
    )
    composed = (
        (transcript + "\n\nCurrent user message:\n" + message) if transcript.strip() else message
    )
    return OperatorChatHistoryContext(
        conversation_id=conversation_id,
        history_rows=list(rows),
        transcript=transcript,
        composed_prompt=composed,
        message_count=len(rows),
        transcript_chars=len(transcript),
    )


def run_operator_chat_turn(
    message: str,
    *,
    conversation_id: Optional[str] = None,
    conversation_store: Optional[ConversationStore] = None,
    responder: Optional[Responder] = None,
    brain_trace_callback: Optional[BrainTraceCallback] = None,
    after_persist_callback: Optional[AfterPersistCallback] = None,
    source_entrypoint: str = "operator_chat",
    history_limit: int = 20,
    history_char_limit: int = 8000,
    metadata: Optional[Dict[str, Any]] = None,
    dry_run: bool = True,
    default_conversation_id: str = "control_panel",
    generate_conversation_id_if_missing: bool = False,
    http_context: str = "general",
    persist_user_before_responder: bool = True,
) -> OperatorChatResult:
    """
    Run one operator chat turn: history → (optional) persist user → brain trace → responder → persist.

    Does not call LLMs, tools, shell, or autonomy. Host supplies ``responder``.
    When ``persist_user_before_responder`` is False, messages are stored only after a successful reply.
    """
    warnings: List[str] = []
    extra_meta = dict(metadata or {})

    text = str(message or "").strip()
    cid = normalize_operator_conversation_id(
        conversation_id,
        default_id=default_conversation_id,
        generate_if_missing=generate_conversation_id_if_missing,
        conversation_store=conversation_store,
    )

    if not text:
        return OperatorChatResult(
            ok=False,
            conversation_id=cid,
            error="message is required",
            warnings=warnings,
        )

    if responder is None:
        return OperatorChatResult(
            ok=False,
            conversation_id=cid,
            error="responder is required",
            warnings=warnings,
        )

    if conversation_store is None:
        return OperatorChatResult(
            ok=False,
            conversation_id=cid,
            error="conversation_store is required",
            warnings=warnings,
        )

    history_ctx = build_operator_history_context(
        conversation_store,
        cid,
        text,
        history_limit=history_limit,
        history_char_limit=history_char_limit,
    )

    user_row: Dict[str, Any] = {}
    if persist_user_before_responder:
        try:
            user_row = conversation_store.append_message(cid, role="user", content=text)
        except Exception as exc:
            logger.warning("operator chat user persist failed: %s", exc)
            return OperatorChatResult(
                ok=False,
                conversation_id=cid,
                history_context=history_ctx,
                error=f"user_persist_failed:{str(exc)[:200]}",
                warnings=warnings,
            )

    brain_result = default_fail_open_brain_trace(
        brain_trace_callback,
        text,
        http_context=str(http_context or source_entrypoint)[:240],
    )
    warnings.extend(brain_result.warnings)
    brain_meta = dict(brain_result.metadata)
    storage_meta = sanitize_operator_chat_metadata({**extra_meta, **brain_meta})

    req = OperatorChatRequest(
        message=text,
        conversation_id=cid,
        composed_prompt=history_ctx.composed_prompt,
        history_context=history_ctx,
        metadata={**extra_meta, **brain_meta},
        source_entrypoint=str(source_entrypoint or "operator_chat")[:120],
        dry_run=bool(dry_run),
    )

    try:
        responder_out = responder(req)
        if isinstance(responder_out, OperatorChatResponderResult):
            reply_text = str(responder_out.reply_text or "")
            responder_extra = dict(responder_out.extra_fields or {})
        elif isinstance(responder_out, tuple) and responder_out:
            reply_text = str(responder_out[0] or "")
            responder_extra = dict(responder_out[1]) if len(responder_out) > 1 else {}
        else:
            reply_text = str(responder_out or "")
            responder_extra = {}
    except OperatorChatResponderError as exc:
        return OperatorChatResult(
            ok=False,
            conversation_id=cid,
            history_context=history_ctx,
            user_message_id=str(user_row.get("message_id") or ""),
            brain_metadata=brain_meta,
            warnings=warnings,
            error=exc.error,
        )
    except Exception as exc:
        logger.warning("operator chat responder failed: %s", exc)
        return OperatorChatResult(
            ok=False,
            conversation_id=cid,
            history_context=history_ctx,
            user_message_id=str(user_row.get("message_id") or ""),
            brain_metadata=brain_meta,
            warnings=warnings,
            error=str(exc)[:400],
        )

    if not persist_user_before_responder:
        try:
            user_row = conversation_store.append_message(cid, role="user", content=text)
        except Exception as exc:
            logger.warning("operator chat user persist failed: %s", exc)
            return OperatorChatResult(
                ok=False,
                conversation_id=cid,
                history_context=history_ctx,
                brain_metadata=brain_meta,
                warnings=warnings,
                error=f"user_persist_failed:{str(exc)[:200]}",
            )

    assistant_row: Dict[str, Any] = {}
    try:
        assistant_row = conversation_store.append_message(
            cid,
            role="assistant",
            content=reply_text,
            metadata=storage_meta or None,
        )
    except Exception as exc:
        logger.warning("operator chat assistant persist failed: %s", exc)
        return OperatorChatResult(
            ok=False,
            conversation_id=cid,
            reply=reply_text,
            history_context=history_ctx,
            user_message_id=str(user_row.get("message_id") or ""),
            brain_metadata=brain_meta,
            warnings=warnings,
            error=f"assistant_persist_failed:{str(exc)[:200]}",
            extra=responder_extra,
        )

    if after_persist_callback is not None:
        try:
            after_persist_callback(cid, text, reply_text, brain_meta, responder_extra)
        except Exception as exc:
            logger.warning("operator chat after_persist failed: %s", exc)
            warnings.append(f"after_persist_failed:{str(exc)[:200]}")

    return OperatorChatResult(
        ok=True,
        conversation_id=cid,
        reply=reply_text,
        history_context=history_ctx,
        user_message_id=str(user_row.get("message_id") or ""),
        assistant_message_id=str(assistant_row.get("message_id") or ""),
        brain_metadata=brain_meta,
        warnings=warnings,
        extra=responder_extra,
    )
