"""Sanitized read-only summary of the latest persisted BrainPipeline trace (no raw TDA / secrets)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .config import BrainPipelineConfig, get_brain_pipeline_config
from .tda_trace_fields import (
    ALIAS_TDA_TRACE_KEY,
    CANONICAL_TDA_TRACE_KEY,
    think_decide_act_trace_present,
)

logger = logging.getLogger(__name__)

_PREVIEW_MAX = 200
_TRANSITION_STR_MAX = 120

_SENSITIVE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsk-[A-Za-z0-9]{8,}\b", re.I), "[REDACTED]"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{6,}\b", re.I), "Bearer [REDACTED]"),
    (re.compile(r"\bapi[_-]?key\s*[:=]\s*\S+", re.I), "api_key=[REDACTED]"),
    (re.compile(r"\bsecret\s*[:=]\s*\S+", re.I), "secret=[REDACTED]"),
    (re.compile(r"\bpassword\s*[:=]\s*\S+", re.I), "password=[REDACTED]"),
    (re.compile(r"\btoken\s*[:=]\s*\S+", re.I), "token=[REDACTED]"),
    (re.compile(r"\bauthorization\s*[:=]\s*\S+", re.I), "authorization=[REDACTED]"),
)

_CREDENTIAL_LIKE = re.compile(r"\b[A-Za-z0-9+/=_\-]{64,}\b")


def redact_sensitive(value: Union[str, Any]) -> Any:
    """Redact common secret patterns in strings; pass through non-strings."""
    if not isinstance(value, str):
        return value
    s = value
    for rx, repl in _SENSITIVE_PATTERNS:
        s = rx.sub(repl, s)
    if _CREDENTIAL_LIKE.search(s) and any(
        k in s.lower() for k in ("key", "secret", "token", "auth", "bearer", "password", "sk-")
    ):
        s = _CREDENTIAL_LIKE.sub("[REDACTED]", s)
    return s


def _truncate(s: str, limit: int) -> str:
    t = (s or "").strip()
    if len(t) <= limit:
        return t
    return t[: limit - 3] + "..."


def sanitize_brain_trace(trace_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Return a shallow copy of allowed keys with redaction (not a full trace dump)."""
    out: Dict[str, Any] = {}
    for k in (
        "brain_pipeline_id",
        "started_at",
        "input_source",
        "risk",
        "tool_selected",
        "tool_fallback",
        "execution_ok",
        "use_think_decide_act",
        "dry_run",
        "think_decide_act_trace_present",
    ):
        if k in trace_dict:
            v = trace_dict[k]
            out[k] = redact_sensitive(v) if isinstance(v, str) else v
    prev = trace_dict.get("context_preview")
    if isinstance(prev, str):
        out["context_preview"] = _truncate(str(redact_sensitive(prev)), _PREVIEW_MAX)
    return out


def summarize_trace(trace_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Build the compact ``trace`` object for API/dashboard (no raw TDA / unified body)."""
    transitions = trace_dict.get("transitions")
    trans_list: List[str] = [str(t) for t in transitions] if isinstance(transitions, list) else []
    redacted_trans = [str(redact_sensitive(t)) for t in trans_list]
    last_transition = _truncate(redacted_trans[-1], _TRANSITION_STR_MAX) if redacted_trans else ""

    ue = trace_dict.get("unified_export")
    unified_keys: List[str] = []
    _skip = frozenset(
        {CANONICAL_TDA_TRACE_KEY, "think_decide_act", ALIAS_TDA_TRACE_KEY, "raw_trace"}
    )
    if isinstance(ue, dict):
        unified_keys = sorted(str(k) for k in ue.keys() if str(k) not in _skip)[:80]

    tda_used = think_decide_act_trace_present(trace_dict)

    mem_written = any(
        isinstance(t, str) and "think_decide_act_finished" in t for t in trans_list
    ) or bool(str(trace_dict.get("lesson_preview") or "").strip())

    si_queued = any(t == "self_improvement_enqueued" for t in trans_list)

    obs = trace_dict.get("context_preview")
    if isinstance(obs, str):
        observation_preview = _truncate(str(redact_sensitive(obs)), _PREVIEW_MAX)
    else:
        observation_preview = ""

    risk_level = trace_dict.get("risk")
    if risk_level is not None:
        risk_level = str(redact_sensitive(str(risk_level)))

    exec_ok = trace_dict.get("execution_ok")
    if exec_ok is not None and not isinstance(exec_ok, (bool, type(None))):
        exec_ok = bool(exec_ok)

    return {
        "brain_pipeline_id": str(redact_sensitive(str(trace_dict.get("brain_pipeline_id", "") or "")))[:128],
        "started_at": str(trace_dict.get("started_at") or "")[:80],
        "input_source": str(redact_sensitive(str(trace_dict.get("input_source") or "")))[:120],
        "observation_preview": observation_preview,
        "risk_level": risk_level,
        "execution_success": exec_ok,
        "tda_used": tda_used,
        "stage_count": len(trans_list),
        "last_transition": last_transition,
        "memory_written": bool(mem_written),
        "self_improvement_queued": bool(si_queued),
        "unified_export_keys": unified_keys,
    }


def load_latest_brain_trace_summary(
    *,
    config: Optional[BrainPipelineConfig] = None,
) -> Dict[str, Any]:
    """
    Load ``config.trace_path`` JSON and return a safe summary dict.

    Always returns HTTP-friendly structure (caller may jsonify with status 200).
    """
    cfg = config or get_brain_pipeline_config()
    path: Path = cfg.trace_path
    warnings: List[str] = []

    base: Dict[str, Any] = {
        "available": True,
        "enabled": bool(cfg.enabled),
        "dry_run": bool(cfg.dry_run),
        "trace_path": str(path),
        "trace_exists": path.is_file(),
        "warnings": warnings,
    }

    if not path.is_file():
        base["trace_exists"] = False
        base["message"] = "No brain trace has been recorded yet."
        return base

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("brain trace read failed: %s", e)
        warnings.append(f"read_error:{e}")
        base["trace_exists"] = False
        base["message"] = "Brain trace file could not be read."
        return base

    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError as e:
        warnings.append(f"invalid_json:{e}")
        base["trace_exists"] = False
        base["message"] = "Brain trace file is present but could not be read as JSON."
        base["error"] = "invalid_trace_json"
        base["error_message"] = str(e)
        base["trace"] = None
        return base

    if not isinstance(raw, dict):
        warnings.append("trace_root_not_object")
        base["trace_exists"] = False
        base["message"] = "Brain trace file has an unexpected format."
        base["trace"] = None
        return base

    base["trace_exists"] = True
    base["dry_run"] = bool(raw.get("dry_run", cfg.dry_run))
    summary = summarize_trace(raw)
    base["trace"] = summary
    base.update(summary)
    bid = str(raw.get("brain_pipeline_id") or "")
    if bid and isinstance(base.get("trace"), dict):
        try:
            from project_guardian.self_improvement.proposal_queue import count_proposals_for_trace

            base["trace"]["self_improvement_proposal_count"] = int(count_proposals_for_trace(bid))
            base["self_improvement_proposal_count"] = base["trace"]["self_improvement_proposal_count"]
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("proposal count for trace skipped: %s", exc)
            base["trace"]["self_improvement_proposal_count"] = 0
            base["self_improvement_proposal_count"] = 0
    elif isinstance(base.get("trace"), dict):
        base["trace"]["self_improvement_proposal_count"] = 0
        base["self_improvement_proposal_count"] = 0
    return base
