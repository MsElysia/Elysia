"""Tests for passive Phase 2 live-action rollback scaffolding."""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path

from project_guardian.live_action_audit import (
    LiveActionAuditEventStatus,
    build_live_action_audit_record,
)
from project_guardian.live_action_gate import (
    ActionRiskCategory,
    build_approval_request,
    validate_live_action_request,
)
from project_guardian.live_action_rollback import (
    LiveActionRollbackPlan,
    RollbackAvailability,
    RollbackStrategy,
    summarize_live_action_rollback_plan,
    validate_live_action_rollback_plan,
)

ROOT = Path(__file__).resolve().parents[2]
ROLLBACK_MODULE = ROOT / "project_guardian" / "live_action_rollback.py"


def _plan(**kwargs) -> LiveActionRollbackPlan:
    defaults = {
        "action_id": "act-rollback-test",
        "strategy": RollbackStrategy.FILE_BACKUP,
        "availability": RollbackAvailability.AVAILABLE,
        "target": "REPORTS/weekly.md",
        "backup_path": "REPORTS/.backups/weekly.md.bak",
    }
    defaults.update(kwargs)
    return LiveActionRollbackPlan(**defaults)


class TestRollbackValidator:
    def test_valid_file_backup_passes(self) -> None:
        result = validate_live_action_rollback_plan(_plan())
        assert result.valid is True
        assert result.safety_verdict == "SAFE"
        assert result.availability is RollbackAvailability.AVAILABLE
        assert not result.reasons

    def test_file_backup_without_backup_path_fails(self) -> None:
        result = validate_live_action_rollback_plan(_plan(backup_path=""))
        assert result.valid is False
        assert result.safety_verdict == "UNSAFE"
        assert any("backup_path" in reason for reason in result.reasons)

    def test_valid_delete_created_file_passes(self) -> None:
        result = validate_live_action_rollback_plan(
            _plan(
                strategy=RollbackStrategy.DELETE_CREATED_FILE,
                availability=RollbackAvailability.AVAILABLE,
                target="REPORTS/weekly.md",
                backup_path="",
            )
        )
        assert result.valid is True

    def test_valid_manual_only_passes(self) -> None:
        result = validate_live_action_rollback_plan(
            _plan(
                strategy=RollbackStrategy.MANUAL_ONLY,
                availability=RollbackAvailability.PARTIAL,
                target="",
                backup_path="",
                manual_steps=("Notify operator", "Revert via control panel"),
            )
        )
        assert result.valid is True

    def test_manual_only_without_manual_steps_fails(self) -> None:
        result = validate_live_action_rollback_plan(
            _plan(
                strategy=RollbackStrategy.MANUAL_ONLY,
                availability=RollbackAvailability.PARTIAL,
                target="",
                backup_path="",
                manual_steps=(),
            )
        )
        assert result.valid is False
        assert any("manual_steps" in reason for reason in result.reasons)

    def test_none_must_be_unavailable(self) -> None:
        ok = validate_live_action_rollback_plan(
            _plan(
                strategy=RollbackStrategy.NONE,
                availability=RollbackAvailability.UNAVAILABLE,
                target="",
                backup_path="",
            )
        )
        bad = validate_live_action_rollback_plan(
            _plan(
                strategy=RollbackStrategy.NONE,
                availability=RollbackAvailability.AVAILABLE,
                target="",
                backup_path="",
            )
        )
        assert ok.valid is True
        assert bad.valid is False
        assert any("UNAVAILABLE" in reason for reason in bad.reasons)

    def test_not_required_must_be_not_applicable(self) -> None:
        ok = validate_live_action_rollback_plan(
            _plan(
                strategy=RollbackStrategy.NOT_REQUIRED,
                availability=RollbackAvailability.NOT_APPLICABLE,
                target="",
                backup_path="",
            )
        )
        bad = validate_live_action_rollback_plan(
            _plan(
                strategy=RollbackStrategy.NOT_REQUIRED,
                availability=RollbackAvailability.UNAVAILABLE,
                target="",
                backup_path="",
            )
        )
        assert ok.valid is True
        assert bad.valid is False
        assert any("NOT_APPLICABLE" in reason for reason in bad.reasons)

    def test_state_snapshot_requires_snapshot_id(self) -> None:
        ok = validate_live_action_rollback_plan(
            _plan(
                strategy=RollbackStrategy.STATE_SNAPSHOT,
                availability=RollbackAvailability.AVAILABLE,
                target="",
                backup_path="",
                snapshot_id="snap-001",
            )
        )
        bad = validate_live_action_rollback_plan(
            _plan(
                strategy=RollbackStrategy.STATE_SNAPSHOT,
                availability=RollbackAvailability.AVAILABLE,
                target="",
                backup_path="",
                snapshot_id="",
            )
        )
        assert ok.valid is True
        assert bad.valid is False
        assert any("snapshot_id" in reason for reason in bad.reasons)

    def test_external_reversal_requires_manual_steps(self) -> None:
        ok = validate_live_action_rollback_plan(
            _plan(
                strategy=RollbackStrategy.EXTERNAL_REVERSAL,
                availability=RollbackAvailability.PARTIAL,
                target="",
                backup_path="",
                manual_steps=("Contact provider support",),
            )
        )
        bad = validate_live_action_rollback_plan(
            _plan(
                strategy=RollbackStrategy.EXTERNAL_REVERSAL,
                availability=RollbackAvailability.PARTIAL,
                target="",
                backup_path="",
                manual_steps=(),
            )
        )
        assert ok.valid is True
        assert bad.valid is False
        assert any("manual_steps" in reason for reason in bad.reasons)


class TestRollbackSummary:
    def test_json_summary_is_serializable(self) -> None:
        plan = _plan(
            manual_steps=("step one",),
            irreversible_risks=("data loss",),
            estimated_complexity="low",
            notes="test note",
        )
        payload = summarize_live_action_rollback_plan(plan)
        encoded = json.dumps(payload, ensure_ascii=False)
        decoded = json.loads(encoded)
        assert decoded["strategy"] == RollbackStrategy.FILE_BACKUP.value
        assert decoded["availability"] == RollbackAvailability.AVAILABLE.value
        assert decoded["manual_steps"] == ["step one"]
        assert decoded["irreversible_risks"] == ["data loss"]


class TestPassiveModule:
    def test_validator_creates_no_files(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        validate_live_action_rollback_plan(_plan())
        assert list(tmp_path.iterdir()) == []

    def test_import_creates_no_files(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        importlib.import_module("project_guardian.live_action_rollback")
        assert list(tmp_path.iterdir()) == []

    def test_module_does_not_import_execution_systems(self) -> None:
        tree = ast.parse(ROLLBACK_MODULE.read_text(encoding="utf-8"))
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
            "project_guardian.live_action_gate",
            "project_guardian.live_action_audit",
        )
        for imp in imports:
            for bad in forbidden:
                assert imp != bad and not imp.startswith(bad + ".")

    def test_all_rollback_strategies_defined(self) -> None:
        expected = {
            "NONE",
            "NOT_REQUIRED",
            "MANUAL_ONLY",
            "FILE_BACKUP",
            "FILE_RESTORE",
            "DELETE_CREATED_FILE",
            "REVERT_PATCH",
            "CONFIG_RESTORE",
            "STATE_SNAPSHOT",
            "EXTERNAL_REVERSAL",
        }
        assert {s.value for s in RollbackStrategy} == expected

    def test_all_availability_states_defined(self) -> None:
        expected = {"AVAILABLE", "PARTIAL", "UNAVAILABLE", "NOT_APPLICABLE"}
        assert {s.value for s in RollbackAvailability} == expected


class TestAuditPassiveIntegration:
    def test_audit_accepts_rollback_plan_summary_dict(self) -> None:
        request = build_approval_request(
            proposed_action="write_report:weekly",
            reason="digest",
            risk_category=ActionRiskCategory.WRITE_REPORT,
            target="REPORTS/weekly.md",
            expected_result="file created",
            rollback_plan="legacy string plan",
            writes_files=True,
        )
        validation = validate_live_action_request(request)
        rollback_plan = _plan()
        rollback_summary = summarize_live_action_rollback_plan(rollback_plan)

        record = build_live_action_audit_record(
            request,
            validation,
            rollback_plan_summary=rollback_summary,
        )

        assert record.rollback_status is LiveActionAuditEventStatus.ROLLBACK_AVAILABLE
        decoded = json.loads(record.rollback_info)
        assert decoded["strategy"] == RollbackStrategy.FILE_BACKUP.value
        assert decoded["backup_path"] == rollback_plan.backup_path
