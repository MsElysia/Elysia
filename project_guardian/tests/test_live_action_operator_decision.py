"""Tests for passive Phase 2 live-action operator decision scaffolding."""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path

from project_guardian.live_action_approval_packet import build_live_action_approval_packet
from project_guardian.live_action_gate import ActionRiskCategory, build_approval_request
from project_guardian.live_action_operator_decision import (
    LiveActionOperatorDecision,
    OperatorDecisionKind,
    build_live_action_operator_decision,
    build_operator_decision_audit_update,
    serialize_live_action_operator_decision,
    serialize_live_action_operator_decision_validation,
    validate_live_action_operator_decision,
)
from project_guardian.live_action_rollback import (
    LiveActionRollbackPlan,
    RollbackAvailability,
    RollbackStrategy,
)

ROOT = Path(__file__).resolve().parents[2]
DECISION_MODULE = ROOT / "project_guardian" / "live_action_operator_decision.py"


def _rollback_plan(
    *,
    action_id: str,
    strategy: RollbackStrategy = RollbackStrategy.NOT_REQUIRED,
    availability: RollbackAvailability = RollbackAvailability.NOT_APPLICABLE,
    **kwargs,
) -> LiveActionRollbackPlan:
    defaults = {
        "action_id": action_id,
        "strategy": strategy,
        "availability": availability,
    }
    defaults.update(kwargs)
    return LiveActionRollbackPlan(**defaults)


def _ready_packet(**request_kwargs) -> tuple:
    defaults = {
        "proposed_action": "write_report:weekly",
        "reason": "digest",
        "risk_category": ActionRiskCategory.WRITE_REPORT,
        "target": "REPORTS/weekly.md",
        "expected_result": "file created",
        "rollback_plan": "manual rollback",
        "writes_files": True,
    }
    defaults.update(request_kwargs)
    request = build_approval_request(**defaults)
    rollback = _rollback_plan(
        action_id=request.action_id,
        strategy=RollbackStrategy.MANUAL_ONLY,
        availability=RollbackAvailability.PARTIAL,
        manual_steps=("Delete REPORTS/weekly.md",),
    )
    packet = build_live_action_approval_packet(request, rollback)
    assert packet.ready_for_operator_review is True
    return packet, request


def _decision_for_packet(
    packet,
    *,
    decision: OperatorDecisionKind,
    operator_id: str = "operator-1",
    reason: str = "reviewed",
    approved_scope: str = "",
) -> LiveActionOperatorDecision:
    return build_live_action_operator_decision(
        packet_id=packet.packet_id,
        action_id=packet.request.action_id,
        decision=decision,
        operator_id=operator_id,
        reason=reason,
        approved_scope=approved_scope,
    )


class TestOperatorDecisionValidation:
    def test_deny_records_decision_execution_still_blocked(self) -> None:
        packet, _ = _ready_packet()
        decision = _decision_for_packet(packet, decision=OperatorDecisionKind.DENY, reason="too risky")
        result = validate_live_action_operator_decision(packet, decision)

        assert result.valid is True
        assert result.execution_permitted is False
        assert result.safety_verdict == "DENIED"
        assert decision.execution_permitted is False

    def test_request_changes_records_decision_execution_still_blocked(self) -> None:
        packet, _ = _ready_packet()
        decision = _decision_for_packet(
            packet,
            decision=OperatorDecisionKind.REQUEST_CHANGES,
            reason="add rollback detail",
        )
        result = validate_live_action_operator_decision(packet, decision)

        assert result.valid is True
        assert result.execution_permitted is False
        assert result.safety_verdict == "CHANGES_REQUESTED"

    def test_approve_on_ready_packet_records_approval_execution_still_blocked(self) -> None:
        packet, _ = _ready_packet()
        decision = _decision_for_packet(
            packet,
            decision=OperatorDecisionKind.APPROVE,
            operator_id="operator-42",
            reason="scope limited and rollback acceptable",
            approved_scope="write REPORTS/weekly.md only",
        )
        result = validate_live_action_operator_decision(packet, decision)

        assert result.valid is True
        assert result.execution_permitted is False
        assert result.safety_verdict == "APPROVAL_RECORDED_EXECUTION_STILL_BLOCKED"
        assert "EXECUTION_APPROVED" not in result.safety_verdict

    def test_approve_missing_operator_id_fails(self) -> None:
        packet, _ = _ready_packet()
        decision = _decision_for_packet(
            packet,
            decision=OperatorDecisionKind.APPROVE,
            operator_id="",
            reason="ok",
            approved_scope="write REPORTS/weekly.md only",
        )
        result = validate_live_action_operator_decision(packet, decision)

        assert result.valid is False
        assert result.safety_verdict == "INVALID_DECISION"
        assert any("operator_id" in reason for reason in result.reasons)

    def test_approve_missing_reason_fails(self) -> None:
        packet, _ = _ready_packet()
        decision = _decision_for_packet(
            packet,
            decision=OperatorDecisionKind.APPROVE,
            operator_id="operator-42",
            reason="",
            approved_scope="write REPORTS/weekly.md only",
        )
        result = validate_live_action_operator_decision(packet, decision)

        assert result.valid is False
        assert any("reason" in reason for reason in result.reasons)

    def test_approve_missing_approved_scope_fails(self) -> None:
        packet, _ = _ready_packet()
        decision = _decision_for_packet(
            packet,
            decision=OperatorDecisionKind.APPROVE,
            operator_id="operator-42",
            reason="looks fine",
            approved_scope="",
        )
        result = validate_live_action_operator_decision(packet, decision)

        assert result.valid is False
        assert any("approved_scope" in reason for reason in result.reasons)

    def test_approve_on_blocked_packet_fails(self) -> None:
        request = build_approval_request(
            proposed_action="network:fetch",
            reason="test",
            risk_category=ActionRiskCategory.NETWORK_REQUEST,
            target="https://example.com",
            expected_result="none",
            rollback_plan="none",
            touches_network_api_or_browser=True,
        )
        rollback = _rollback_plan(
            action_id=request.action_id,
            strategy=RollbackStrategy.NONE,
            availability=RollbackAvailability.UNAVAILABLE,
        )
        packet = build_live_action_approval_packet(request, rollback)
        decision = _decision_for_packet(
            packet,
            decision=OperatorDecisionKind.APPROVE,
            operator_id="operator-42",
            reason="approve anyway",
            approved_scope="network fetch",
        )
        result = validate_live_action_operator_decision(packet, decision)

        assert packet.safety_verdict == "BLOCKED"
        assert result.valid is False
        assert any("packet_blocked" in reason or "packet_not_ready" in reason for reason in result.reasons)

    def test_approve_on_rollback_invalid_packet_fails(self) -> None:
        request = build_approval_request(
            proposed_action="write_report:weekly",
            reason="digest",
            risk_category=ActionRiskCategory.WRITE_REPORT,
            target="REPORTS/weekly.md",
            expected_result="file created",
            rollback_plan="manual",
            writes_files=True,
        )
        rollback = _rollback_plan(
            action_id=request.action_id,
            strategy=RollbackStrategy.MANUAL_ONLY,
            availability=RollbackAvailability.PARTIAL,
            manual_steps=(),
        )
        packet = build_live_action_approval_packet(request, rollback)
        decision = _decision_for_packet(
            packet,
            decision=OperatorDecisionKind.APPROVE,
            operator_id="operator-42",
            reason="approve",
            approved_scope="write file",
        )
        result = validate_live_action_operator_decision(packet, decision)

        assert packet.safety_verdict == "NEEDS_ROLLBACK_REVIEW"
        assert result.valid is False
        assert any("rollback" in reason for reason in result.reasons)

    def test_mismatched_packet_id_fails(self) -> None:
        packet, _ = _ready_packet()
        decision = build_live_action_operator_decision(
            packet_id="wrong-packet-id",
            action_id=packet.request.action_id,
            decision=OperatorDecisionKind.DENY,
            reason="no",
        )
        result = validate_live_action_operator_decision(packet, decision)

        assert result.valid is False
        assert "packet_id_mismatch" in result.reasons

    def test_mismatched_action_id_fails(self) -> None:
        packet, _ = _ready_packet()
        decision = build_live_action_operator_decision(
            packet_id=packet.packet_id,
            action_id="wrong-action-id",
            decision=OperatorDecisionKind.DENY,
            reason="no",
        )
        result = validate_live_action_operator_decision(packet, decision)

        assert result.valid is False
        assert "action_id_mismatch" in result.reasons


class TestOperatorDecisionSerialization:
    def test_serializer_is_json_safe(self) -> None:
        packet, _ = _ready_packet()
        decision = _decision_for_packet(
            packet,
            decision=OperatorDecisionKind.APPROVE,
            operator_id="operator-42",
            reason="approved with scope",
            approved_scope="write REPORTS/weekly.md only",
        )
        decision_payload = serialize_live_action_operator_decision(decision)
        result = validate_live_action_operator_decision(packet, decision)
        validation_payload = serialize_live_action_operator_decision_validation(result)

        encoded = json.dumps(
            {"decision": decision_payload, "validation": validation_payload},
            ensure_ascii=False,
        )
        decoded = json.loads(encoded)
        assert decoded["decision"]["decision"] == OperatorDecisionKind.APPROVE.value
        assert decoded["validation"]["execution_permitted"] is False
        assert decoded["validation"]["safety_verdict"] == "APPROVAL_RECORDED_EXECUTION_STILL_BLOCKED"


class TestPassiveAuditIntegration:
    def test_audit_update_helper_does_not_imply_execution(self) -> None:
        packet, _ = _ready_packet()
        decision = _decision_for_packet(
            packet,
            decision=OperatorDecisionKind.APPROVE,
            operator_id="operator-42",
            reason="approved",
            approved_scope="write REPORTS/weekly.md only",
        )
        result = validate_live_action_operator_decision(packet, decision)
        update = build_operator_decision_audit_update(decision, result)

        assert update["execution_permitted"] is False
        assert update["event_status"] == "APPROVED"
        assert update["safety_verdict"] == "APPROVAL_RECORDED_EXECUTION_STILL_BLOCKED"


class TestPassiveModule:
    def test_validator_creates_no_files(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        packet, _ = _ready_packet()
        decision = _decision_for_packet(packet, decision=OperatorDecisionKind.DENY, reason="no")
        validate_live_action_operator_decision(packet, decision)
        assert list(tmp_path.iterdir()) == []

    def test_import_creates_no_files(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        importlib.import_module("project_guardian.live_action_operator_decision")
        assert list(tmp_path.iterdir()) == []

    def test_module_does_not_import_execution_systems(self) -> None:
        tree = ast.parse(DECISION_MODULE.read_text(encoding="utf-8"))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        allowed_prefixes = (
            "project_guardian.live_action_approval_packet",
            "project_guardian.live_action_audit",
        )
        stdlib_ok = {
            "__future__",
            "uuid",
            "dataclasses",
            "datetime",
            "enum",
            "typing",
        }
        for imp in imports:
            if imp in stdlib_ok:
                continue
            assert any(
                imp == prefix or imp.startswith(prefix + ".") for prefix in allowed_prefixes
            ), f"unexpected import: {imp}"

        forbidden = (
            "subprocess",
            "httpx",
            "requests",
            "flask",
            "elysia",
            "project_guardian.capability_execution",
            "project_guardian.tool_executor",
            "project_guardian.webscout_agent",
            "project_guardian.bounded_browser",
        )
        for imp in imports:
            for bad in forbidden:
                assert imp != bad and not imp.startswith(bad + ".")
