# project_guardian/llm_trace_jsonl.py
"""
Optional append-only JSONL traces for unified LLM calls (Langfuse-style observability without a server).

Enable with environment variable ``ELYSIA_LLM_TRACE_JSONL`` set to a file path (absolute or relative to
process cwd). Each ``unified_chat_completion`` exit writes one JSON object per line.

Privacy defaults: user message is not stored verbatim; only length and a short SHA-256 prefix of the
UTF-8 bytes. Set ``ELYSIA_LLM_TRACE_INCLUDE_USER_PREFIX=1`` to add ``user_text_prefix`` (first 120 chars).

Optional: ``ELYSIA_LLM_TRACE_PROJECT`` — string label stored as ``project`` (e.g. install name).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)
_lock = threading.Lock()


def _sanitize_selfbuild_rag(raw: Any) -> Any:
    if not isinstance(raw, dict):
        return raw
    out = dict(raw)
    sims = out.get("sims_rounded")
    if isinstance(sims, list) and len(sims) > 16:
        out["sims_rounded"] = sims[:16] + [f"...(+{len(sims) - 16})"]
    return out


def append_unified_chat_trace(
    *,
    reply: str,
    err: str,
    meta: Dict[str, Any],
    module_name: str,
    agent_name: Optional[str],
    route_task_type: str,
    require_autonomy_safe_reasoning: bool,
    user_text: str,
) -> None:
    path = (os.environ.get("ELYSIA_LLM_TRACE_JSONL") or "").strip()
    if not path:
        return
    try:
        ut = user_text or ""
        h = hashlib.sha256(ut.encode("utf-8", errors="ignore")).hexdigest()
        row: Dict[str, Any] = {
            "v": 1,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "t_unix": time.time(),
            "event": "unified_chat_completion",
            "project": (os.environ.get("ELYSIA_LLM_TRACE_PROJECT") or "").strip() or None,
            "llm_call_id": meta.get("llm_call_id"),
            "module_name": module_name,
            "agent_name": agent_name,
            "route_task_type": route_task_type,
            "require_autonomy_safe_reasoning": bool(require_autonomy_safe_reasoning),
            "backend": meta.get("backend"),
            "router_primary": meta.get("router_primary"),
            "provider_order": meta.get("provider_order"),
            "attempted_backends": meta.get("attempted_backends"),
            "reason": (str(meta.get("reason") or "")[:800]),
            "latency_ms": meta.get("latency_ms"),
            "fallback_from": meta.get("fallback_from"),
            "success": bool(reply) and not (err or "").strip(),
            "reply_chars": len(reply or ""),
            "error_chars": len(err or ""),
            "error_prefix": ((err or "")[:240] if err else None),
            "selfbuild_rag": _sanitize_selfbuild_rag(meta.get("selfbuild_rag")),
            "user_chars": len(ut),
            "user_text_fp16": h[:16],
        }
        if os.environ.get("ELYSIA_LLM_TRACE_INCLUDE_USER_PREFIX", "").strip().lower() in (
            "1",
            "true",
            "yes",
        ):
            row["user_text_prefix"] = ut[:120]
        line = json.dumps(row, ensure_ascii=False, default=str) + "\n"
        with _lock:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception as e:
        logger.debug("[llm_trace_jsonl] append skipped: %s", e)
