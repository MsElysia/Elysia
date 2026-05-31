"""Phase 2 passive operator decision schema and validation.

Represents operator approve/deny decisions for live-action approval packets.
Does not execute actions, rollback, or write audit files.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from project_guardian.live_action_approval_packet import LiveActionApprovalPacket
from project_guardian.live_action_audit import LiveActionAuditEventStatus


class OperatorDecisionKind(str, Enum):
    """Operator decision for a live-action approval packet."""

    APPROVE = "APPROVE"
    DENY = "DENY"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nonempty(value: Optional[str]) -> bool:
    return bool(value and str(value).strip())


@dataclass(frozen=True)
class LiveActionOperatorDecision:
    """Passive operator decision record for an approval packet."""

    decision_id: str
    packet_id: str
    action_id: str
    operator_id: str
    decision: OperatorDecisionKind
    reason: str
    timestamp: str
    approved_scope: str
    expires_at: str
    conditions: Tuple[str, ...]
    execution_permitted: bool
    safety_verdict: str


@dataclass(frozen=True)
class LiveActionOperatorDecisionValidationResult:
    """Validation outcome for an operator decision against an approval packet."""

    valid: bool
    decision: OperatorDecisionKind
    execution_permitted: bool
    reasons: Tuple[str, ...]
    safety_verdict: str


def build_live_action_operator_decision(
    *,
    packet_id: str,
    action_id: str,
    decision: OperatorDecisionKind,
    reason: str = "",
    operator_id: str = "",
    approved_scope: str = "",
    expires_at: str = "",
    conditions: Tuple[str, ...] = (),
    decision_id: str | None = None,
    timestamp: str | None = None,
    safety_verdict: str = "",
) -> LiveActionOperatorDecision:
    """Build a passive operator decision object. ``execution_permitted`` is always False."""
    return LiveActionOperatorDecision(
        decision_id=decision_id or str(uuid.uuid4()),
        packet_id=packet_id,
        action_id=action_id,
        operator_id=operator_id,
        decision=decision,
        reason=reason,
        timestamp=timestamp or _utc_now_iso(),
        approved_scope=approved_scope,
        expires_at=expires_at,
        conditions=conditions,
        execution_permitted=False,
        safety_verdict=safety_verdict,
    )


def _decision_safety_verdict(
    decision: OperatorDecisionKind,
    valid: bool,
) -> str:
    if not valid:
        return "INVALID_DECISION"
    if decision is OperatorDecisionKind.APPROVE:
        return "APPROVAL_RECORDED_EXECUTION_STILL_BLOCKED"
    if decision is OperatorDecisionKind.DENY:
        return "DENIED"
    if decision is OperatorDecisionKind.REQUEST_CHANGES:
        return "CHANGES_REQUESTED"
    if decision is OperatorDecisionKind.EXPIRED:
        return "EXPIRED"
    if decision is OperatorDecisionKind.CANCELLED:
        return "CANCELLED"
    return "DECISION_RECORDED"


def validate_live_action_operator_decision(
    packet: LiveActionApprovalPacket,
    operator_decision: LiveActionOperatorDecision,
) -> LiveActionOperatorDecisionValidationResult:
    """Validate an operator decision against a passive approval packet."""
    reasons: list[str] = []
    decision = operator_decision.decision

    if operator_decision.packet_id != packet.packet_id:
        reasons.append("packet_id_mismatch")
    if operator_decision.action_id != packet.request.action_id:
        reasons.append("action_id_mismatch")
    if not packet.ready_for_operator_review:
        reasons.append("packet_not_ready_for_operator_review")
    if packet.execution_permitted:
        reasons.append("packet_execution_permitted")
    if operator_decision.execution_permitted:
        reasons.append("decision_execution_permitted_not_allowed")

    if decision is OperatorDecisionKind.APPROVE:
        if packet.safety_verdict == "BLOCKED":
            reasons.append("packet_blocked")
        if packet.safety_verdict == "NEEDS_ROLLBACK_REVIEW":
            reasons.append("packet_needs_rollback_review")
        if not _nonempty(operator_decision.operator_id):
            reasons.append("missing_operator_id")
        if not _nonempty(operator_decision.reason):
            reasons.append("missing_reason")
        if not _nonempty(operator_decision.approved_scope):
            reasons.append("missing_approved_scope")

    valid = not reasons
    safety_verdict = _decision_safety_verdict(decision, valid)

    return LiveActionOperatorDecisionValidationResult(
        valid=valid,
        decision=decision,
        execution_permitted=False,
        reasons=tuple(reasons),
        safety_verdict=safety_verdict,
    )


def serialize_live_action_operator_decision(
    operator_decision: LiveActionOperatorDecision,
) -> Dict[str, Any]:
    """Return a JSON-safe plain dict for an operator decision."""
    return {
        "decision_id": operator_decision.decision_id,
        "packet_id": operator_decision.packet_id,
        "action_id": operator_decision.action_id,
        "operator_id": operator_decision.operator_id,
        "decision": operator_decision.decision.value,
        "reason": operator_decision.reason,
        "timestamp": operator_decision.timestamp,
        "approved_scope": operator_decision.approved_scope,
        "expires_at": operator_decision.expires_at,
        "conditions": list(operator_decision.conditions),
        "execution_permitted": operator_decision.execution_permitted,
        "safety_verdict": operator_decision.safety_verdict,
    }


def serialize_live_action_operator_decision_validation(
    result: LiveActionOperatorDecisionValidationResult,
) -> Dict[str, Any]:
    """Return a JSON-safe plain dict for a decision validation result."""
    return {
        "valid": result.valid,
        "decision": result.decision.value,
        "execution_permitted": result.execution_permitted,
        "reasons": list(result.reasons),
        "safety_verdict": result.safety_verdict,
    }


def _audit_event_status_for_decision(
    decision: OperatorDecisionKind,
    valid: bool,
) -> LiveActionAuditEventStatus:
    if not valid:
        return LiveActionAuditEventStatus.BLOCKED
    if decision is OperatorDecisionKind.APPROVE:
        return LiveActionAuditEventStatus.APPROVED
    if decision is OperatorDecisionKind.DENY:
        return LiveActionAuditEventStatus.DENIED
    if decision is OperatorDecisionKind.REQUEST_CHANGES:
        return LiveActionAuditEventStatus.PROPOSED
    if decision is OperatorDecisionKind.EXPIRED:
        return LiveActionAuditEventStatus.EXECUTION_SKIPPED
    if decision is OperatorDecisionKind.CANCELLED:
        return LiveActionAuditEventStatus.EXECUTION_SKIPPED
    return LiveActionAuditEventStatus.PROPOSED


def build_operator_decision_audit_update(
    operator_decision: LiveActionOperatorDecision,
    validation: LiveActionOperatorDecisionValidationResult,
) -> Dict[str, Any]:
    """Build a passive audit-status update dict. Does not write files."""
    return {
        "decision_id": operator_decision.decision_id,
        "packet_id": operator_decision.packet_id,
        "action_id": operator_decision.action_id,
        "operator_id": operator_decision.operator_id,
        "decision": operator_decision.decision.value,
        "event_status": _audit_event_status_for_decision(
            operator_decision.decision, validation.valid
        ).value,
        "execution_permitted": False,
        "safety_verdict": validation.safety_verdict,
        "reasons": list(validation.reasons),
        "timestamp": operator_decision.timestamp,
    }
