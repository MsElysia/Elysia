"""Tests for passive Phase 2 live-action approval packet scaffolding."""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path

from project_guardian.live_action_approval_packet import (
    DEFAULT_PACKET_MODE,
    build_live_action_approval_packet,
    serialize_live_action_approval_packet,
)
from project_guardian.live_action_gate import ActionRiskCategory, build_approval_request
from project_guardian.live_action_rollback import (
    LiveActionRollbackPlan,
    RollbackAvailability,
    RollbackStrategy,
)

ROOT = Path(__file__).resolve().parents[2]
PACKET_MODULE = ROOT / "project_guardian" / "live_action_approval_packet.py"
DEFAULT_LIVE_ACTION_AUDIT = ROOT / "data" / "runtime" / "live_action_audit.jsonl"


def _line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _rollback_plan(
    *,
    action_id: str = "act-packet-test",
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


class TestApprovalPacketBuilder:
    def test_read_only_not_required_ready_for_review_execution_not_permitted(self) -> None:
        request = build_approval_request(
            proposed_action="read:status",
            reason="health check",
            risk_category=ActionRiskCategory.READ_ONLY,
            target="status://127.0.0.1:8888/status",
            expected_result="json payload",
            rollback_plan="not required",
        )
        rollback = _rollback_plan(action_id=request.action_id)
        packet = build_live_action_approval_packet(request, rollback)

        assert packet.execution_permitted is False
        assert packet.ready_for_operator_review is True
        assert packet.safety_verdict == "READY_FOR_REVIEW"
        assert packet.validation.allowed is True
        assert packet.rollback_validation.valid is True
        assert packet.safety_verdict != "EXECUTION_APPROVED"

    def test_write_report_manual_only_ready_for_review(self) -> None:
        request = build_approval_request(
            proposed_action="write_report:weekly",
            reason="digest",
            risk_category=ActionRiskCategory.WRITE_REPORT,
            target="REPORTS/weekly.md",
            expected_result="file created",
            rollback_plan="manual rollback",
            writes_files=True,
        )
        rollback = _rollback_plan(
            action_id=request.action_id,
            strategy=RollbackStrategy.MANUAL_ONLY,
            availability=RollbackAvailability.PARTIAL,
            manual_steps=("Delete REPORTS/weekly.md",),
        )
        packet = build_live_action_approval_packet(request, rollback)

        assert packet.execution_permitted is False
        assert packet.ready_for_operator_review is True
        assert packet.safety_verdict == "READY_FOR_REVIEW"
        assert packet.validation.requires_approval is True

    def test_blocked_network_request(self) -> None:
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

        assert packet.validation.blocked is True
        assert packet.ready_for_operator_review is False
        assert packet.execution_permitted is False
        assert packet.safety_verdict == "BLOCKED"

    def test_blocked_browser_or_webscout(self) -> None:
        request = build_approval_request(
            proposed_action="browser:navigate",
            reason="test",
            risk_category=ActionRiskCategory.BROWSER_OR_WEBSCOUT,
            target="https://example.com",
            expected_result="page",
            rollback_plan="none",
            touches_network_api_or_browser=True,
        )
        rollback = _rollback_plan(
            action_id=request.action_id,
            strategy=RollbackStrategy.NONE,
            availability=RollbackAvailability.UNAVAILABLE,
        )
        packet = build_live_action_approval_packet(request, rollback)

        assert packet.validation.blocked is True
        assert packet.ready_for_operator_review is False
        assert packet.safety_verdict == "BLOCKED"

    def test_blocked_autonomy_config_change(self) -> None:
        request = build_approval_request(
            proposed_action="config:autonomy",
            reason="test",
            risk_category=ActionRiskCategory.AUTONOMY_CONFIG_CHANGE,
            target="config/autonomy.json",
            expected_result="enabled",
            rollback_plan="restore backup",
        )
        rollback = _rollback_plan(
            action_id=request.action_id,
            strategy=RollbackStrategy.CONFIG_RESTORE,
            availability=RollbackAvailability.AVAILABLE,
            target="config/autonomy.json",
            backup_path="config/.backups/autonomy.json.bak",
        )
        packet = build_live_action_approval_packet(request, rollback)

        assert packet.validation.blocked is True
        assert packet.ready_for_operator_review is False
        assert packet.safety_verdict == "BLOCKED"

    def test_touches_autonomy_or_live_execution_blocked(self) -> None:
        request = build_approval_request(
            proposed_action="write_report:weekly",
            reason="test",
            risk_category=ActionRiskCategory.WRITE_REPORT,
            target="REPORTS/weekly.md",
            expected_result="file",
            rollback_plan="delete file",
            touches_autonomy_or_live_execution=True,
            writes_files=True,
        )
        rollback = _rollback_plan(
            action_id=request.action_id,
            strategy=RollbackStrategy.DELETE_CREATED_FILE,
            availability=RollbackAvailability.AVAILABLE,
            target="REPORTS/weekly.md",
        )
        packet = build_live_action_approval_packet(request, rollback)

        assert packet.validation.blocked is True
        assert packet.ready_for_operator_review is False
        assert packet.execution_permitted is False
        assert packet.safety_verdict == "BLOCKED"

    def test_invalid_rollback_needs_rollback_review(self) -> None:
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

        assert packet.rollback_validation.valid is False
        assert packet.ready_for_operator_review is False
        assert packet.execution_permitted is False
        assert packet.safety_verdict == "NEEDS_ROLLBACK_REVIEW"
        assert any("manual_steps" in reason for reason in packet.reasons)


class TestApprovalPacketSerialization:
    def test_serializer_is_json_safe(self) -> None:
        request = build_approval_request(
            proposed_action="read:status",
            reason="inspect",
            risk_category=ActionRiskCategory.READ_ONLY,
            target="status",
            expected_result="ok",
            rollback_plan="not required",
        )
        rollback = _rollback_plan(action_id=request.action_id)
        packet = build_live_action_approval_packet(request, rollback, mode=DEFAULT_PACKET_MODE)
        payload = serialize_live_action_approval_packet(packet)

        encoded = json.dumps(payload, ensure_ascii=False)
        decoded = json.loads(encoded)
        assert decoded["mode"] == DEFAULT_PACKET_MODE
        assert decoded["execution_permitted"] is False
        assert decoded["request"]["risk_category"] == "READ_ONLY"
        assert decoded["rollback_plan"]["strategy"] == RollbackStrategy.NOT_REQUIRED.value
        assert decoded["audit_record"]["action_id"] == request.action_id
        assert decoded["safety_verdict"] != "EXECUTION_APPROVED"


class TestPassiveModule:
    def test_builder_does_not_create_files(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        request = build_approval_request(
            proposed_action="read:status",
            reason="test",
            risk_category=ActionRiskCategory.READ_ONLY,
            target="status",
            expected_result="ok",
            rollback_plan="not required",
        )
        rollback = _rollback_plan(action_id=request.action_id)
        build_live_action_approval_packet(request, rollback)
        assert list(tmp_path.iterdir()) == []

    def test_builder_does_not_write_audit_jsonl(self) -> None:
        before = _line_count(DEFAULT_LIVE_ACTION_AUDIT)
        request = build_approval_request(
            proposed_action="read:status",
            reason="test",
            risk_category=ActionRiskCategory.READ_ONLY,
            target="status",
            expected_result="ok",
            rollback_plan="not required",
        )
        rollback = _rollback_plan(action_id=request.action_id)
        build_live_action_approval_packet(request, rollback)
        after = _line_count(DEFAULT_LIVE_ACTION_AUDIT)
        assert after == before

    def test_import_creates_no_files(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        importlib.import_module("project_guardian.live_action_approval_packet")
        assert list(tmp_path.iterdir()) == []

    def test_module_does_not_import_execution_systems(self) -> None:
        tree = ast.parse(PACKET_MODULE.read_text(encoding="utf-8"))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        allowed_prefixes = (
            "project_guardian.live_action_gate",
            "project_guardian.live_action_audit",
            "project_guardian.live_action_rollback",
        )
        stdlib_ok = {
            "__future__",
            "json",
            "uuid",
            "dataclasses",
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
