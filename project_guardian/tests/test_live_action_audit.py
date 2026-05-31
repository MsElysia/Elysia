"""Tests for passive Phase 2 live-action audit scaffolding."""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from project_guardian.live_action_audit import (
    LiveActionAuditEventStatus,
    LiveActionAuditRecord,
    append_live_action_audit_record,
    build_live_action_audit_record,
    serialize_live_action_audit_record,
)
from project_guardian.live_action_gate import (
    ActionRiskCategory,
    AllowlistDecision,
    build_approval_request,
    validate_live_action_request,
)

ROOT = Path(__file__).resolve().parents[2]
AUDIT_MODULE = ROOT / "project_guardian" / "live_action_audit.py"
DEFAULT_LIVE_ACTION_AUDIT = ROOT / "data" / "runtime" / "live_action_audit.jsonl"
DRY_RUN_REPORT_SCRIPT = ROOT / "scripts" / "run_elysia_dry_run_report.py"


def _line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


class TestAuditRecordBuilder:
    def test_read_only_builds_audit_record(self) -> None:
        request = build_approval_request(
            proposed_action="read:status",
            reason="health check",
            risk_category=ActionRiskCategory.READ_ONLY,
            target="status://127.0.0.1:8888/status",
            expected_result="json payload",
            rollback_plan="none",
        )
        validation = validate_live_action_request(request)
        record = build_live_action_audit_record(request, validation, mode="safe_observer")

        assert validation.allowed is True
        assert record.action_id == request.action_id
        assert record.risk_category == "READ_ONLY"
        assert record.approval_status == "not_required"
        assert record.allowlist_decision == AllowlistDecision.ALLOW_LOGGED.value
        assert record.result == "allowed_logged"
        assert record.safety_verdict == "SAFE"
        assert record.event_status is LiveActionAuditEventStatus.EXECUTION_SKIPPED
        assert record.rollback_info == "none"
        assert record.rollback_status is LiveActionAuditEventStatus.ROLLBACK_UNAVAILABLE
        assert record.touches_autonomy_or_live_execution is False
        assert record.touches_network_api_or_browser is False
        assert record.writes_files is False

    def test_blocked_request_audit_record(self) -> None:
        request = build_approval_request(
            proposed_action="api:call",
            reason="test block",
            risk_category=ActionRiskCategory.API_CALL,
            target="https://example.com",
            expected_result="none",
            rollback_plan="none",
            touches_network_api_or_browser=True,
        )
        validation = validate_live_action_request(request)
        record = build_live_action_audit_record(request, validation)

        assert validation.blocked is True
        assert record.approval_status == "blocked"
        assert record.event_status is LiveActionAuditEventStatus.BLOCKED
        assert record.safety_verdict == "BLOCKED"
        assert record.result == "blocked"
        assert record.touches_network_api_or_browser is True
        assert record.reasons

    def test_requires_approval_includes_rollback_available(self) -> None:
        request = build_approval_request(
            proposed_action="write_report:weekly",
            reason="digest",
            risk_category=ActionRiskCategory.WRITE_REPORT,
            target="REPORTS/weekly.md",
            expected_result="file created",
            rollback_plan="delete REPORTS/weekly.md",
            writes_files=True,
        )
        validation = validate_live_action_request(request)
        record = build_live_action_audit_record(request, validation)

        assert record.approval_status == "pending"
        assert record.event_status is LiveActionAuditEventStatus.PROPOSED
        assert record.rollback_status is LiveActionAuditEventStatus.ROLLBACK_AVAILABLE
        assert record.rollback_info.startswith("delete")
        assert record.writes_files is True


class TestAuditSerializationAndWriter:
    def test_serialization_is_json_safe(self) -> None:
        request = build_approval_request(
            proposed_action="read:logs",
            reason="inspect",
            risk_category=ActionRiskCategory.READ_ONLY,
            target="logs/elysia_unified.log",
            expected_result="tail",
            rollback_plan="none",
        )
        validation = validate_live_action_request(request)
        record = build_live_action_audit_record(request, validation)
        payload = serialize_live_action_audit_record(record)

        encoded = json.dumps(payload, ensure_ascii=False)
        decoded = json.loads(encoded)
        assert decoded["event_status"] == LiveActionAuditEventStatus.EXECUTION_SKIPPED.value
        assert decoded["risk_category"] == "READ_ONLY"
        assert isinstance(decoded["reasons"], list)

    def test_writer_appends_one_jsonl_line(self, tmp_path: Path) -> None:
        request = build_approval_request(
            proposed_action="read:status",
            reason="audit writer test",
            risk_category=ActionRiskCategory.READ_ONLY,
            target="status",
            expected_result="ok",
            rollback_plan="none",
        )
        validation = validate_live_action_request(request)
        record = build_live_action_audit_record(request, validation)
        dest = tmp_path / "nested" / "live_action_audit.jsonl"

        assert append_live_action_audit_record(record, dest) is True
        assert _line_count(dest) == 1
        line = json.loads(dest.read_text(encoding="utf-8").strip())
        assert line["action_id"] == record.action_id
        assert line["safety_verdict"] == "SAFE"

        assert append_live_action_audit_record(record, dest) is True
        assert _line_count(dest) == 2

    def test_import_does_not_create_files(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        importlib.import_module("project_guardian.live_action_audit")
        assert list(tmp_path.iterdir()) == []


class TestPassiveModule:
    def test_module_does_not_import_execution_systems(self) -> None:
        tree = ast.parse(AUDIT_MODULE.read_text(encoding="utf-8"))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

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

    def test_all_audit_event_statuses_defined(self) -> None:
        expected = {
            "PROPOSED",
            "APPROVED",
            "DENIED",
            "BLOCKED",
            "EXECUTION_SKIPPED",
            "EXECUTION_STARTED",
            "EXECUTION_SUCCEEDED",
            "EXECUTION_FAILED",
            "ROLLBACK_AVAILABLE",
            "ROLLBACK_UNAVAILABLE",
        }
        assert {s.value for s in LiveActionAuditEventStatus} == expected


class TestSafeObserverIsolation:
    def test_dry_run_report_does_not_append_live_action_audit(self) -> None:
        before = _line_count(DEFAULT_LIVE_ACTION_AUDIT)
        spec = importlib.util.spec_from_file_location("run_elysia_dry_run_report", DRY_RUN_REPORT_SCRIPT)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        rc = mod.main(["--mode", "real-planning"])
        after = _line_count(DEFAULT_LIVE_ACTION_AUDIT)
        assert rc in (0, 1, 2)
        assert after == before
