"""Phase 2 passive live-action approval packet builder.

Combines gate validation, rollback metadata, and audit record into a single
operator-review packet. Does not execute actions, rollback, or write audit files.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Tuple

from project_guardian.live_action_audit import (
    LiveActionAuditRecord,
    build_live_action_audit_record,
    serialize_live_action_audit_record,
)
from project_guardian.live_action_gate import (
    LiveActionApprovalRequest,
    LiveActionValidationResult,
    validate_live_action_request,
)
from project_guardian.live_action_rollback import (
    LiveActionRollbackPlan,
    LiveActionRollbackValidationResult,
    summarize_live_action_rollback_plan,
    validate_live_action_rollback_plan,
)

DEFAULT_PACKET_MODE = "approval_gated_live_design"


@dataclass(frozen=True)
class LiveActionApprovalPacket:
    """Passive approval packet combining request, validation, rollback, and audit."""

    packet_id: str
    mode: str
    request: LiveActionApprovalRequest
    validation: LiveActionValidationResult
    rollback_plan: LiveActionRollbackPlan
    rollback_validation: LiveActionRollbackValidationResult
    audit_record: LiveActionAuditRecord
    ready_for_operator_review: bool
    execution_permitted: bool
    reasons: Tuple[str, ...]
    safety_verdict: str


def _packet_safety_verdict(
    validation: LiveActionValidationResult,
    rollback_validation: LiveActionRollbackValidationResult,
    ready_for_operator_review: bool,
) -> str:
    if validation.blocked:
        return "BLOCKED"
    if not rollback_validation.valid:
        return "NEEDS_ROLLBACK_REVIEW"
    if ready_for_operator_review:
        return "READY_FOR_REVIEW"
    return "BLOCKED"


def _packet_reasons(
    validation: LiveActionValidationResult,
    rollback_validation: LiveActionRollbackValidationResult,
    request: LiveActionApprovalRequest,
) -> Tuple[str, ...]:
    reasons: list[str] = []
    reasons.extend(validation.reasons)
    if request.touches_autonomy_or_live_execution and "touches_autonomy_or_live_execution" not in reasons:
        reasons.append("touches_autonomy_or_live_execution")
    if not rollback_validation.valid:
        reasons.extend(rollback_validation.reasons)
    return tuple(reasons)


def build_live_action_approval_packet(
    request: LiveActionApprovalRequest,
    rollback_plan: LiveActionRollbackPlan,
    *,
    mode: str = DEFAULT_PACKET_MODE,
    packet_id: str | None = None,
) -> LiveActionApprovalPacket:
    """Build a passive approval packet. Does not execute or write anything."""
    validation = validate_live_action_request(request)
    rollback_validation = validate_live_action_rollback_plan(rollback_plan)
    rollback_summary = summarize_live_action_rollback_plan(rollback_plan)
    audit_record = build_live_action_audit_record(
        request,
        validation,
        mode=mode,
        rollback_plan_summary=rollback_summary,
    )

    ready_for_operator_review = (
        not validation.blocked
        and rollback_validation.valid
        and not request.touches_autonomy_or_live_execution
    )
    execution_permitted = False
    reasons = _packet_reasons(validation, rollback_validation, request)
    safety_verdict = _packet_safety_verdict(
        validation, rollback_validation, ready_for_operator_review
    )

    return LiveActionApprovalPacket(
        packet_id=packet_id or str(uuid.uuid4()),
        mode=mode,
        request=request,
        validation=validation,
        rollback_plan=rollback_plan,
        rollback_validation=rollback_validation,
        audit_record=audit_record,
        ready_for_operator_review=ready_for_operator_review,
        execution_permitted=execution_permitted,
        reasons=reasons,
        safety_verdict=safety_verdict,
    )


def _serialize_request(request: LiveActionApprovalRequest) -> Dict[str, Any]:
    return {
        "action_id": request.action_id,
        "proposed_action": request.proposed_action,
        "reason": request.reason,
        "risk_category": request.risk_category.value,
        "target": request.target,
        "expected_result": request.expected_result,
        "rollback_plan": request.rollback_plan,
        "touches_autonomy_or_live_execution": request.touches_autonomy_or_live_execution,
        "writes_files": request.writes_files,
        "touches_network_api_or_browser": request.touches_network_api_or_browser,
        "allowlist_decision": (
            request.allowlist_decision.value if request.allowlist_decision is not None else None
        ),
    }


def _serialize_validation(validation: LiveActionValidationResult) -> Dict[str, Any]:
    return {
        "allowed": validation.allowed,
        "requires_approval": validation.requires_approval,
        "blocked": validation.blocked,
        "decision": validation.decision.value,
        "reasons": list(validation.reasons),
        "safety_verdict": validation.safety_verdict,
    }


def _serialize_rollback_plan(plan: LiveActionRollbackPlan) -> Dict[str, Any]:
    return summarize_live_action_rollback_plan(plan)


def _serialize_rollback_validation(
    result: LiveActionRollbackValidationResult,
) -> Dict[str, Any]:
    return {
        "valid": result.valid,
        "availability": result.availability.value,
        "reasons": list(result.reasons),
        "safety_verdict": result.safety_verdict,
    }


def serialize_live_action_approval_packet(packet: LiveActionApprovalPacket) -> Dict[str, Any]:
    """Return a JSON-safe plain dict for the approval packet."""
    return {
        "packet_id": packet.packet_id,
        "mode": packet.mode,
        "request": _serialize_request(packet.request),
        "validation": _serialize_validation(packet.validation),
        "rollback_plan": _serialize_rollback_plan(packet.rollback_plan),
        "rollback_validation": _serialize_rollback_validation(packet.rollback_validation),
        "audit_record": serialize_live_action_audit_record(packet.audit_record),
        "ready_for_operator_review": packet.ready_for_operator_review,
        "execution_permitted": packet.execution_permitted,
        "reasons": list(packet.reasons),
        "safety_verdict": packet.safety_verdict,
    }


def serialize_live_action_approval_packet_json(packet: LiveActionApprovalPacket) -> str:
    """Return a JSON string for the approval packet (helper for tests/operators)."""
    return json.dumps(serialize_live_action_approval_packet(packet), ensure_ascii=False)
