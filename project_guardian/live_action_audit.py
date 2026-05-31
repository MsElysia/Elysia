"""Phase 2 passive live-action audit record schema and explicit JSONL writer.

Append-only audit lines are written only when ``append_live_action_audit_record``
is called with an explicit path. Nothing runs on import or during Safe Observer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

from project_guardian.live_action_gate import (
    AllowlistDecision,
    LiveActionApprovalRequest,
    LiveActionValidationResult,
)


class LiveActionAuditEventStatus(str, Enum):
    """Audit event lifecycle status (passive labels only; no execution implied)."""

    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    BLOCKED = "BLOCKED"
    EXECUTION_SKIPPED = "EXECUTION_SKIPPED"
    EXECUTION_STARTED = "EXECUTION_STARTED"
    EXECUTION_SUCCEEDED = "EXECUTION_SUCCEEDED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    ROLLBACK_AVAILABLE = "ROLLBACK_AVAILABLE"
    ROLLBACK_UNAVAILABLE = "ROLLBACK_UNAVAILABLE"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _approval_status_from_validation(validation: LiveActionValidationResult) -> str:
    if validation.blocked:
        return "blocked"
    if validation.requires_approval:
        return "pending"
    if validation.allowed:
        return "not_required"
    return "unknown"


def _event_status_from_validation(validation: LiveActionValidationResult) -> LiveActionAuditEventStatus:
    if validation.blocked:
        return LiveActionAuditEventStatus.BLOCKED
    if validation.allowed:
        return LiveActionAuditEventStatus.EXECUTION_SKIPPED
    if validation.requires_approval:
        return LiveActionAuditEventStatus.PROPOSED
    return LiveActionAuditEventStatus.PROPOSED


def _result_from_validation(validation: LiveActionValidationResult) -> str:
    if validation.blocked:
        return "blocked"
    if validation.allowed:
        return "allowed_logged"
    if validation.requires_approval:
        return "pending_approval"
    return "unknown"


def _rollback_event_status(rollback_plan: str) -> LiveActionAuditEventStatus:
    plan = (rollback_plan or "").strip()
    if plan and plan.lower() not in ("none", "n/a", "na"):
        return LiveActionAuditEventStatus.ROLLBACK_AVAILABLE
    return LiveActionAuditEventStatus.ROLLBACK_UNAVAILABLE


@dataclass(frozen=True)
class LiveActionAuditRecord:
    """Passive audit record for a proposed or gated live action."""

    timestamp: str
    mode: str
    action_id: str
    proposed_action: str
    risk_category: str
    approval_status: str
    allowlist_decision: str
    executor: str
    target: str
    result: str
    rollback_info: str
    safety_verdict: str
    reasons: Tuple[str, ...]
    writes_files: bool
    touches_autonomy_or_live_execution: bool
    touches_network_api_or_browser: bool
    event_status: LiveActionAuditEventStatus
    rollback_status: LiveActionAuditEventStatus


def build_live_action_audit_record(
    request: LiveActionApprovalRequest,
    validation: LiveActionValidationResult,
    *,
    mode: str = "safe_observer",
    executor: str = "",
    event_status: Optional[LiveActionAuditEventStatus] = None,
    timestamp: Optional[str] = None,
) -> LiveActionAuditRecord:
    """Build a passive audit record from an approval request and validation result."""
    decision = validation.decision
    if request.allowlist_decision is not None:
        decision = request.allowlist_decision

    rollback_status = _rollback_event_status(request.rollback_plan)
    resolved_event = event_status or _event_status_from_validation(validation)

    return LiveActionAuditRecord(
        timestamp=timestamp or _utc_now_iso(),
        mode=mode,
        action_id=request.action_id,
        proposed_action=request.proposed_action,
        risk_category=request.risk_category.value,
        approval_status=_approval_status_from_validation(validation),
        allowlist_decision=decision.value,
        executor=executor,
        target=request.target,
        result=_result_from_validation(validation),
        rollback_info=request.rollback_plan,
        safety_verdict=validation.safety_verdict,
        reasons=tuple(validation.reasons),
        writes_files=request.writes_files,
        touches_autonomy_or_live_execution=request.touches_autonomy_or_live_execution,
        touches_network_api_or_browser=request.touches_network_api_or_browser,
        event_status=resolved_event,
        rollback_status=rollback_status,
    )


def serialize_live_action_audit_record(record: LiveActionAuditRecord) -> Dict[str, Any]:
    """Return a JSON-safe plain dict for the audit record."""
    return {
        "timestamp": record.timestamp,
        "mode": record.mode,
        "action_id": record.action_id,
        "proposed_action": record.proposed_action,
        "risk_category": record.risk_category,
        "approval_status": record.approval_status,
        "allowlist_decision": record.allowlist_decision,
        "executor": record.executor,
        "target": record.target,
        "result": record.result,
        "rollback_info": record.rollback_info,
        "safety_verdict": record.safety_verdict,
        "reasons": list(record.reasons),
        "writes_files": record.writes_files,
        "touches_autonomy_or_live_execution": record.touches_autonomy_or_live_execution,
        "touches_network_api_or_browser": record.touches_network_api_or_browser,
        "event_status": record.event_status.value,
        "rollback_status": record.rollback_status.value,
    }


def append_live_action_audit_record(
    record: LiveActionAuditRecord,
    audit_path: Union[str, Path],
) -> bool:
    """Append one UTF-8 JSONL audit line to ``audit_path``. Never runs automatically."""
    path = Path(audit_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(serialize_live_action_audit_record(record), ensure_ascii=False)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return True
    except OSError:
        return False
