"""Fail-closed policy guard for future live execution.

This module evaluates whether a proposed live execution request satisfies the
documented governance gates. It is deliberately side-effect free: it does not
execute tools, call models, read config files, write audit logs, or contact
external services.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Tuple


ReasonCode = str

CONFIG_DISABLED = "config_disabled"
ENTRYPOINT_DISABLED = "entrypoint_disabled"
LIVE_EXECUTION_DISABLED = "live_execution_disabled"
MISSING_OPERATOR_CONFIRMATION = "missing_operator_confirmation"
MISSING_DRY_RUN_TRACE = "missing_dry_run_trace"
STALE_DRY_RUN_TRACE = "stale_dry_run_trace"
INVALID_DRY_RUN_TRACE_TIME = "invalid_dry_run_trace_time"
HIGH_RISK_DENIED = "high_risk_denied"
BLOCKED_RISK_DENIED = "blocked_risk_denied"
MEDIUM_RISK_REQUIRES_EXPLICIT_APPROVAL = "medium_risk_requires_explicit_approval"
MISSING_EXECUTOR_ALLOWLIST = "missing_executor_allowlist"
EXECUTOR_NOT_ALLOWLISTED = "executor_not_allowlisted"
RAW_COMMAND_DENIED = "raw_command_denied"
SELF_MODIFICATION_DENIED = "self_modification_denied"
AUTONOMY_CONTEXT_DENIED = "autonomy_context_denied"
ROLLBACK_REQUIRED_FOR_MUTATION = "rollback_required_for_mutation"

_VALID_RISKS = frozenset({"low", "medium", "high", "blocked"})
_RAW_COMMAND_RE = re.compile(
    r"(?i)\b(shell|powershell|cmd(?:\.exe)?|terminal|subprocess|os\.system|"
    r"bash|zsh|sh\s+-c|python\s+-c|node\s+-e|exec\(|eval\(|sudo|"
    r"rm\s+-rf|del\s+/s|format\s+c:)\b"
)


@dataclass(frozen=True)
class LiveExecutionRequest:
    """Structured input for evaluating a possible live execution attempt."""

    request_id: str = ""
    source_entrypoint: str = ""
    config_enabled: bool = False
    entrypoint_enabled: bool = False
    live_execution_enabled: bool = False
    risk_level: str = "blocked"
    action_type: str = ""
    target: str = ""
    executor_name: str = ""
    executor_allowlist: Tuple[str, ...] = field(default_factory=tuple)
    operator_confirmed: bool = False
    operator_confirmation_id: str = ""
    explicit_medium_risk_approval: bool = False
    dry_run_trace_id: str = ""
    dry_run_trace_completed_at: Optional[Any] = None
    now: Optional[Any] = None
    dry_run_trace_ttl_seconds: int = 900
    raw_text: str = ""
    payload: Mapping[str, Any] = field(default_factory=dict)
    is_self_modification: bool = False
    is_autonomy_context: bool = False
    mutates_files: bool = False
    mutates_code: bool = False
    rollback_available: bool = False
    rollback_plan_id: str = ""


@dataclass(frozen=True)
class LiveExecutionDecision:
    """Serializable allow/deny result for a live execution request."""

    allowed: bool
    reasons: Tuple[ReasonCode, ...] = field(default_factory=tuple)
    request_id: str = ""
    risk_level: str = "blocked"
    executor_name: str = ""
    source_entrypoint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def evaluate_live_execution_request(request: Optional[LiveExecutionRequest] = None) -> LiveExecutionDecision:
    """Return a fail-closed decision for a proposed live execution request."""
    req = request or LiveExecutionRequest()
    reasons = []
    risk = _normalize_risk(req.risk_level)

    if not req.config_enabled:
        reasons.append(CONFIG_DISABLED)
    if not req.entrypoint_enabled:
        reasons.append(ENTRYPOINT_DISABLED)
    if not req.live_execution_enabled:
        reasons.append(LIVE_EXECUTION_DISABLED)

    if not req.operator_confirmed or not str(req.operator_confirmation_id).strip():
        reasons.append(MISSING_OPERATOR_CONFIRMATION)

    trace_reason = _dry_run_trace_reason(req)
    if trace_reason:
        reasons.append(trace_reason)

    if risk == "blocked":
        reasons.append(BLOCKED_RISK_DENIED)
    elif risk == "high":
        reasons.append(HIGH_RISK_DENIED)
    elif risk == "medium" and not req.explicit_medium_risk_approval:
        reasons.append(MEDIUM_RISK_REQUIRES_EXPLICIT_APPROVAL)

    allowlist = {str(item).strip() for item in req.executor_allowlist if str(item).strip()}
    executor = str(req.executor_name or "").strip()
    if not allowlist:
        reasons.append(MISSING_EXECUTOR_ALLOWLIST)
    elif not executor or executor not in allowlist:
        reasons.append(EXECUTOR_NOT_ALLOWLISTED)

    if _looks_like_raw_command(req):
        reasons.append(RAW_COMMAND_DENIED)
    if _is_self_modification(req):
        reasons.append(SELF_MODIFICATION_DENIED)
    if req.is_autonomy_context or str(req.source_entrypoint).strip().lower() == "autonomy":
        reasons.append(AUTONOMY_CONTEXT_DENIED)
    if (req.mutates_files or req.mutates_code) and not (
        req.rollback_available or str(req.rollback_plan_id).strip()
    ):
        reasons.append(ROLLBACK_REQUIRED_FOR_MUTATION)

    unique_reasons = tuple(dict.fromkeys(reasons))
    return LiveExecutionDecision(
        allowed=not unique_reasons,
        reasons=unique_reasons,
        request_id=str(req.request_id or ""),
        risk_level=risk,
        executor_name=executor,
        source_entrypoint=str(req.source_entrypoint or ""),
    )


def _normalize_risk(value: Any) -> str:
    risk = str(value or "blocked").strip().lower()
    if risk in _VALID_RISKS:
        return risk
    if risk in {"critical", "deny", "denied"}:
        return "blocked"
    return "blocked"


def _dry_run_trace_reason(req: LiveExecutionRequest) -> Optional[ReasonCode]:
    if not str(req.dry_run_trace_id or "").strip() or req.dry_run_trace_completed_at is None:
        return MISSING_DRY_RUN_TRACE

    completed = _coerce_datetime(req.dry_run_trace_completed_at)
    now = _coerce_datetime(req.now) if req.now is not None else datetime.now(timezone.utc)
    if completed is None or now is None:
        return INVALID_DRY_RUN_TRACE_TIME

    ttl = max(1, int(req.dry_run_trace_ttl_seconds or 1))
    if (now - completed).total_seconds() > ttl:
        return STALE_DRY_RUN_TRACE
    return None


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _looks_like_raw_command(req: LiveExecutionRequest) -> bool:
    text = " ".join(
        (
            str(req.action_type or ""),
            str(req.target or ""),
            str(req.executor_name or ""),
            str(req.raw_text or ""),
            _payload_text(req.payload),
        )
    )
    return bool(_RAW_COMMAND_RE.search(text))


def _payload_text(payload: Mapping[str, Any]) -> str:
    if not isinstance(payload, Mapping):
        return str(payload)
    parts = []
    for key, value in payload.items():
        parts.append(str(key))
        parts.append(str(value))
    return " ".join(parts)


def _is_self_modification(req: LiveExecutionRequest) -> bool:
    if req.is_self_modification:
        return True
    text = " ".join((str(req.action_type or ""), str(req.target or ""))).lower()
    return any(
        marker in text
        for marker in (
            "self_modification",
            "self-modification",
            "self_improvement_apply",
            "mutation_apply",
            "proposal_implement",
        )
    )
