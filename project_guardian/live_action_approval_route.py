"""Passive live-action approval route scaffolding.

Lists approval packets, shows detail, records operator decisions, and returns
audit trails. Does not execute actions, call a live executor, or run smoke tests.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from project_guardian.live_action_approval_packet import (
    LiveActionApprovalPacket,
    serialize_live_action_approval_packet,
)
from project_guardian.live_action_operator_decision import (
    LiveActionOperatorDecision,
    OperatorDecisionKind,
    build_live_action_operator_decision,
    build_operator_decision_audit_update,
    serialize_live_action_operator_decision,
    serialize_live_action_operator_decision_validation,
    validate_live_action_operator_decision,
)


class ApprovalRouteErrorCode(str, Enum):
    """Passive approval route error codes (no execution implied)."""

    APPROVAL_ROUTE_DISABLED = "APPROVAL_ROUTE_DISABLED"
    PACKET_NOT_FOUND = "PACKET_NOT_FOUND"
    PACKET_HASH_MISMATCH = "PACKET_HASH_MISMATCH"
    PACKET_EXPIRED = "PACKET_EXPIRED"
    DECISION_ALREADY_RECORDED = "DECISION_ALREADY_RECORDED"
    INVALID_DECISION = "INVALID_DECISION"
    VALIDATION_FAILED = "VALIDATION_FAILED"


_TERMINAL_DECISIONS = frozenset(
    {
        OperatorDecisionKind.APPROVE,
        OperatorDecisionKind.DENY,
        OperatorDecisionKind.CANCELLED,
        OperatorDecisionKind.EXPIRED,
    }
)

_DECISION_ALIASES: Dict[str, OperatorDecisionKind] = {
    "APPROVE": OperatorDecisionKind.APPROVE,
    "DENY": OperatorDecisionKind.DENY,
    "REQUEST_CHANGES": OperatorDecisionKind.REQUEST_CHANGES,
    "CANCEL": OperatorDecisionKind.CANCELLED,
    "CANCELLED": OperatorDecisionKind.CANCELLED,
    "EXPIRE": OperatorDecisionKind.EXPIRED,
    "EXPIRED": OperatorDecisionKind.EXPIRED,
}


def is_live_action_approval_route_enabled() -> bool:
    """Return True only when explicit env enables passive approval routes."""
    raw = os.environ.get("ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_utc_iso(value: str) -> Optional[datetime]:
    if not value or not str(value).strip():
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def compute_packet_content_hash(packet: LiveActionApprovalPacket) -> str:
    """Canonical SHA-256 over serialized approval packet JSON."""
    payload = json.dumps(
        serialize_live_action_approval_packet(packet),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_packet_expired(
    expires_at: str,
    *,
    now: Optional[datetime] = None,
) -> bool:
    """Return True when ``expires_at`` is set and in the past."""
    parsed = _parse_utc_iso(expires_at)
    if parsed is None:
        return False
    current = now or datetime.now(timezone.utc)
    return current >= parsed


def _no_execution_fields() -> Dict[str, Any]:
    return {
        "execution_permitted": False,
        "executed": False,
        "executor_called": False,
    }


def _error_response(
    code: ApprovalRouteErrorCode,
    message: str,
    *,
    status: int = 400,
) -> Tuple[Dict[str, Any], int]:
    body = {
        "error_code": code.value,
        "message": message,
        **_no_execution_fields(),
    }
    return body, status


@dataclass
class StoredApprovalPacket:
    """Registered approval packet with operator-review metadata."""

    packet: LiveActionApprovalPacket
    expires_at: str = ""
    dry_run_trace_id: str = ""
    dry_run_trace_summary: Dict[str, Any] = field(default_factory=dict)
    registered_at: str = field(default_factory=_utc_now_iso)


@dataclass
class LiveActionApprovalRouteStore:
    """In-memory passive store for approval packets and append-only decisions."""

    audit_path: Optional[Union[str, Path]] = None
    _packets: Dict[str, StoredApprovalPacket] = field(default_factory=dict)
    _decisions: Dict[str, List[LiveActionOperatorDecision]] = field(default_factory=dict)

    def register_packet(
        self,
        packet: LiveActionApprovalPacket,
        *,
        expires_at: str = "",
        dry_run_trace_id: str = "",
        dry_run_trace_summary: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a packet for operator review. Does not execute anything."""
        self._packets[packet.packet_id] = StoredApprovalPacket(
            packet=packet,
            expires_at=expires_at,
            dry_run_trace_id=dry_run_trace_id,
            dry_run_trace_summary=dict(dry_run_trace_summary or {}),
        )

    def get_stored_packet(self, packet_id: str) -> Optional[StoredApprovalPacket]:
        return self._packets.get(packet_id)

    def has_terminal_decision(self, packet_id: str) -> bool:
        for decision in self._decisions.get(packet_id, ()):
            if decision.decision in _TERMINAL_DECISIONS:
                return True
        return False

    def append_decision(self, decision: LiveActionOperatorDecision) -> None:
        """Append decision record. Append-only; does not execute."""
        self._decisions.setdefault(decision.packet_id, []).append(decision)
        if self.audit_path is not None:
            line = json.dumps(
                serialize_live_action_operator_decision(decision),
                ensure_ascii=False,
            )
            path = Path(self.audit_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def decisions_for_packet(self, packet_id: str) -> Tuple[LiveActionOperatorDecision, ...]:
        return tuple(self._decisions.get(packet_id, ()))


def _packet_is_pending(stored: StoredApprovalPacket) -> bool:
    packet = stored.packet
    if not packet.ready_for_operator_review:
        return False
    if is_packet_expired(stored.expires_at):
        return False
    return True


def _list_item_from_stored(stored: StoredApprovalPacket) -> Dict[str, Any]:
    packet = stored.packet
    request = packet.request
    return {
        "packet_id": packet.packet_id,
        "action_id": request.action_id,
        "action_category": request.risk_category.value,
        "target_path": request.target,
        "content_hash": request.expected_result,
        "risk_classification": (
            request.allowlist_decision.value
            if request.allowlist_decision is not None
            else packet.validation.decision.value
        ),
        "safety_verdict": packet.safety_verdict,
        "expires_at": stored.expires_at,
        "ready_for_operator_review": packet.ready_for_operator_review
        and not is_packet_expired(stored.expires_at),
        **_no_execution_fields(),
    }


def _detail_from_stored(stored: StoredApprovalPacket) -> Dict[str, Any]:
    packet = stored.packet
    request = packet.request
    serialized = serialize_live_action_approval_packet(packet)
    expired = is_packet_expired(stored.expires_at)
    return {
        "packet_id": packet.packet_id,
        "mode": packet.mode,
        "action_category": request.risk_category.value,
        "action_id": request.action_id,
        "proposed_target_path": request.target,
        "proposed_content_hash": request.expected_result,
        "risk_classification": {
            "risk_category": request.risk_category.value,
            "allowlist_decision": (
                request.allowlist_decision.value if request.allowlist_decision else None
            ),
            "validation_decision": packet.validation.decision.value,
            "blocked": packet.validation.blocked,
        },
        "rollback_plan_summary": serialized.get("rollback_plan", {}),
        "audit_record_preview": serialized.get("audit_record", {}),
        "dry_run_trace_summary": {
            "trace_id": stored.dry_run_trace_id,
            **stored.dry_run_trace_summary,
        },
        "expires_at": stored.expires_at,
        "expired": expired,
        "packet_content_hash": compute_packet_content_hash(packet),
        "ready_for_operator_review": packet.ready_for_operator_review and not expired,
        "safety_verdict": packet.safety_verdict,
        "reasons": list(packet.reasons),
        **_no_execution_fields(),
    }


def _parse_decision_kind(raw: str) -> Optional[OperatorDecisionKind]:
    return _DECISION_ALIASES.get(str(raw or "").strip().upper())


def list_pending_approval_packets(
    store: LiveActionApprovalRouteStore,
    *,
    route_enabled: Optional[bool] = None,
) -> Tuple[Dict[str, Any], int]:
    """List packets ready for operator review. Does not execute."""
    if route_enabled is None:
        route_enabled = is_live_action_approval_route_enabled()
    if not route_enabled:
        return _error_response(
            ApprovalRouteErrorCode.APPROVAL_ROUTE_DISABLED,
            "Live-action approval route is disabled by default",
            status=403,
        )

    pending = [
        _list_item_from_stored(stored)
        for stored in store._packets.values()
        if _packet_is_pending(stored) and not store.has_terminal_decision(stored.packet.packet_id)
    ]
    body = {
        "packets": pending,
        "count": len(pending),
        **_no_execution_fields(),
    }
    return body, 200


def get_approval_packet_detail(
    store: LiveActionApprovalRouteStore,
    packet_id: str,
    *,
    route_enabled: Optional[bool] = None,
) -> Tuple[Dict[str, Any], int]:
    """Return operator-visible packet detail. Does not execute."""
    if route_enabled is None:
        route_enabled = is_live_action_approval_route_enabled()
    if not route_enabled:
        return _error_response(
            ApprovalRouteErrorCode.APPROVAL_ROUTE_DISABLED,
            "Live-action approval route is disabled by default",
            status=403,
        )

    stored = store.get_stored_packet(packet_id)
    if stored is None:
        return _error_response(
            ApprovalRouteErrorCode.PACKET_NOT_FOUND,
            f"Approval packet not found: {packet_id}",
            status=404,
        )

    return _detail_from_stored(stored), 200


def record_operator_decision_for_packet(
    store: LiveActionApprovalRouteStore,
    packet_id: str,
    body: Dict[str, Any],
    *,
    route_enabled: Optional[bool] = None,
    route_source: str = "api",
) -> Tuple[Dict[str, Any], int]:
    """Record operator decision only. Never executes approved actions."""
    if route_enabled is None:
        route_enabled = is_live_action_approval_route_enabled()
    if not route_enabled:
        return _error_response(
            ApprovalRouteErrorCode.APPROVAL_ROUTE_DISABLED,
            "Live-action approval route is disabled by default",
            status=403,
        )

    stored = store.get_stored_packet(packet_id)
    if stored is None:
        return _error_response(
            ApprovalRouteErrorCode.PACKET_NOT_FOUND,
            f"Approval packet not found: {packet_id}",
            status=404,
        )

    if store.has_terminal_decision(packet_id):
        return _error_response(
            ApprovalRouteErrorCode.DECISION_ALREADY_RECORDED,
            "A terminal decision already exists for this packet",
            status=409,
        )

    decision_kind = _parse_decision_kind(str(body.get("decision", "")))
    if decision_kind is None:
        return _error_response(
            ApprovalRouteErrorCode.INVALID_DECISION,
            "decision must be one of APPROVE, DENY, REQUEST_CHANGES, CANCEL, EXPIRE",
            status=400,
        )

    packet = stored.packet
    if decision_kind is OperatorDecisionKind.APPROVE:
        if is_packet_expired(stored.expires_at):
            return _error_response(
                ApprovalRouteErrorCode.PACKET_EXPIRED,
                "Expired packets cannot be approved",
                status=409,
            )
        submitted_hash = str(body.get("packet_content_hash", "")).strip()
        expected_hash = compute_packet_content_hash(packet)
        if not submitted_hash or submitted_hash != expected_hash:
            return _error_response(
                ApprovalRouteErrorCode.PACKET_HASH_MISMATCH,
                "Submitted packet_content_hash does not match server packet",
                status=409,
            )

    operator_decision = build_live_action_operator_decision(
        packet_id=packet_id,
        action_id=packet.request.action_id,
        decision=decision_kind,
        operator_id=str(body.get("operator_id", "")),
        reason=str(body.get("reason", "")),
        approved_scope=str(body.get("approved_scope", "")),
        expires_at=stored.expires_at,
        conditions=tuple(body.get("conditions") or ()),
    )
    validation = validate_live_action_operator_decision(packet, operator_decision)
    audit_update = build_operator_decision_audit_update(operator_decision, validation)

    if not validation.valid:
        return {
            "decision_id": operator_decision.decision_id,
            "packet_id": packet_id,
            "decision": decision_kind.value,
            "validation": serialize_live_action_operator_decision_validation(validation),
            "audit_update_preview": audit_update,
            "error_code": ApprovalRouteErrorCode.VALIDATION_FAILED.value,
            "message": "Operator decision failed validation",
            **_no_execution_fields(),
        }, 422

    store.append_decision(operator_decision)

    return {
        "decision_id": operator_decision.decision_id,
        "packet_id": packet_id,
        "decision": decision_kind.value,
        "validation": serialize_live_action_operator_decision_validation(validation),
        "audit_update_preview": audit_update,
        "route_source": route_source,
        "message": "Decision recorded. Execution remains blocked.",
        **_no_execution_fields(),
    }, 200


def get_approval_decision_trail(
    store: LiveActionApprovalRouteStore,
    packet_id: str,
    *,
    route_enabled: Optional[bool] = None,
) -> Tuple[Dict[str, Any], int]:
    """Return append-only decision trail for a packet. Does not execute."""
    if route_enabled is None:
        route_enabled = is_live_action_approval_route_enabled()
    if not route_enabled:
        return _error_response(
            ApprovalRouteErrorCode.APPROVAL_ROUTE_DISABLED,
            "Live-action approval route is disabled by default",
            status=403,
        )

    stored = store.get_stored_packet(packet_id)
    if stored is None:
        return _error_response(
            ApprovalRouteErrorCode.PACKET_NOT_FOUND,
            f"Approval packet not found: {packet_id}",
            status=404,
        )

    decisions = [
        serialize_live_action_operator_decision(decision)
        for decision in store.decisions_for_packet(packet_id)
    ]
    body = {
        "packet_id": packet_id,
        "decisions": decisions,
        "decision_count": len(decisions),
        "audit_record_preview": serialize_live_action_approval_packet(stored.packet).get(
            "audit_record", {}
        ),
        "dry_run_trace_summary": {
            "trace_id": stored.dry_run_trace_id,
            **stored.dry_run_trace_summary,
        },
        **_no_execution_fields(),
    }
    return body, 200
