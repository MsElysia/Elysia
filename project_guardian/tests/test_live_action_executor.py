"""Tests for disabled-by-default live action executor scaffold."""

from __future__ import annotations

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from project_guardian.live_action_approval_route import (
    LiveActionApprovalRouteStore,
    compute_packet_content_hash,
    record_operator_decision_for_packet,
)
from project_guardian.live_action_executor import (
    LiveActionExecutionRequest,
    LiveExecutorFailureCode,
    LiveExecutorStatus,
    execute_live_action,
    is_live_executor_enabled,
    rollback_harmless_smoke_write,
    serialize_live_action_execution_result,
    serialize_live_action_execution_result_json,
)
from project_guardian.live_action_passive_smoke_flow import (
    register_harmless_smoke_packet_for_approval,
)
from project_guardian.live_action_readiness import evaluate_live_mode_readiness
from project_guardian.live_action_smoke_packet import (
    HARMLESS_LIVE_SMOKE_ACTION_ID,
    HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
    HARMLESS_LIVE_SMOKE_TARGET_FILENAME,
)

ROOT = Path(__file__).resolve().parents[2]
EXECUTOR_MODULE = ROOT / "project_guardian" / "live_action_executor.py"
APPROVAL_ROUTE_MODULE = ROOT / "project_guardian" / "live_action_approval_route.py"


def _smoke_workspace(tmp_path: Path) -> Path:
    return tmp_path / "isolated_smoke_root"


def _smoke_target(workspace: Path) -> Path:
    return workspace / "live_smoke_workspace" / HARMLESS_LIVE_SMOKE_TARGET_FILENAME


def _future_expires_at(*, hours: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _execution_request(
    *,
    workspace: Path,
    packet_id: str = "packet-001",
    decision_id: str = "decision-001",
) -> LiveActionExecutionRequest:
    return LiveActionExecutionRequest(
        approval_packet_id=packet_id,
        operator_decision_id=decision_id,
        action_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
        action_category="harmless_live_smoke",
        target_path=HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
        workspace_root=str(workspace.resolve()),
        expected_content_hash="abc123",
        rollback_plan_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
        audit_record_id="audit-001",
        dry_run_trace_id="trace-001",
    )


@pytest.fixture
def disabled_executor(monkeypatch):
    monkeypatch.delenv("ELYSIA_LIVE_EXECUTOR_ENABLED", raising=False)
    yield


class TestExecutorDisabledByDefault:
    def test_unset_flag_returns_executor_disabled(self, tmp_path, disabled_executor):
        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)
        assert not target.exists()

        result = execute_live_action(_execution_request(workspace=workspace))
        payload = serialize_live_action_execution_result(result)

        assert result.status == LiveExecutorStatus.EXECUTOR_DISABLED.value
        assert result.failure_code == LiveExecutorFailureCode.EXECUTOR_DISABLED.value
        assert result.executed is False
        assert result.execution_permitted is False
        assert result.executor_called is True
        assert result.safety_verdict == "EXECUTOR_DISABLED"
        assert not target.exists()
        assert payload["approval_packet_id"] == "packet-001"
        assert payload["operator_decision_id"] == "decision-001"
        assert payload["target_path"] == HARMLESS_LIVE_SMOKE_RELATIVE_TARGET

    @pytest.mark.parametrize(
        "flag_value",
        ["", "false", "0", "no", "off", "invalid", "FALSE", "No"],
    )
    def test_false_like_flags_block_execution(
        self, tmp_path, monkeypatch, flag_value: str
    ):
        monkeypatch.setenv("ELYSIA_LIVE_EXECUTOR_ENABLED", flag_value)
        assert is_live_executor_enabled() is False

        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)
        result = execute_live_action(_execution_request(workspace=workspace))

        assert result.status == LiveExecutorStatus.EXECUTOR_DISABLED.value
        assert result.failure_code == LiveExecutorFailureCode.EXECUTOR_DISABLED.value
        assert result.executed is False
        assert not target.exists()

    def test_disabled_ignores_valid_approved_smoke_packet(
        self, tmp_path, disabled_executor, monkeypatch
    ):
        monkeypatch.setenv("ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED", "true")
        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)
        store = LiveActionApprovalRouteStore()

        smoke = register_harmless_smoke_packet_for_approval(
            store,
            workspace,
            repo_root=ROOT,
            expires_at=_future_expires_at(),
        )
        record_operator_decision_for_packet(
            store,
            smoke.packet.packet_id,
            {
                "decision": "APPROVE",
                "operator_id": "operator-1",
                "reason": "approved for scaffold test",
                "approved_scope": f"write {HARMLESS_LIVE_SMOKE_RELATIVE_TARGET}",
                "packet_content_hash": compute_packet_content_hash(smoke.packet),
            },
        )

        result = execute_live_action(
            LiveActionExecutionRequest(
                approval_packet_id=smoke.packet.packet_id,
                operator_decision_id="decision-approved",
                action_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
                action_category="harmless_live_smoke",
                target_path=HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
                workspace_root=str(workspace.resolve()),
                expected_content_hash=smoke.content_hash,
                rollback_plan_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
                audit_record_id="audit-approved",
                dry_run_trace_id="trace-approved",
            )
        )

        assert result.status == LiveExecutorStatus.EXECUTOR_DISABLED.value
        assert result.executed is False
        assert not target.exists()
        assert not workspace.exists()

    def test_disabled_with_unsafe_target_writes_nothing(
        self, tmp_path, disabled_executor
    ):
        repo_target = ROOT / "approved_smoke.txt"
        result = execute_live_action(
            LiveActionExecutionRequest(
                approval_packet_id="packet-unsafe",
                operator_decision_id="decision-unsafe",
                action_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
                target_path=str(ROOT / "approved_smoke.txt"),
                workspace_root=str(ROOT),
            )
        )

        assert result.status == LiveExecutorStatus.EXECUTOR_DISABLED.value
        assert result.executed is False
        assert not repo_target.exists()

    def test_disabled_does_not_create_workspace_or_target(
        self, tmp_path, disabled_executor
    ):
        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)

        execute_live_action(_execution_request(workspace=workspace))

        assert not workspace.exists()
        assert not target.exists()

    def test_disabled_result_is_json_serializable(self, tmp_path, disabled_executor):
        workspace = _smoke_workspace(tmp_path)
        result = execute_live_action(_execution_request(workspace=workspace))
        payload = serialize_live_action_execution_result(result)
        encoded = serialize_live_action_execution_result_json(result)

        json.loads(encoded)
        assert payload["executed"] is False
        assert payload["executor_called"] is True
        assert payload["failure_code"] == LiveExecutorFailureCode.EXECUTOR_DISABLED.value

    def test_disabled_does_not_change_readiness(self, tmp_path, disabled_executor):
        workspace = _smoke_workspace(tmp_path)
        before = evaluate_live_mode_readiness()
        execute_live_action(_execution_request(workspace=workspace))
        after = evaluate_live_mode_readiness()

        assert before.ready_for_limited_live_mode is False
        assert after.ready_for_limited_live_mode is False
        assert after.status.value == "BLOCKED"
        assert any("HARMLESS_LIVE_ACTION_SMOKE_VERIFIED" in b for b in after.blockers)

    def test_rollback_scaffold_does_not_execute(self, tmp_path, disabled_executor):
        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)
        result = rollback_harmless_smoke_write(
            workspace_root=str(workspace),
            target_path=HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
            rollback_plan_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
        )

        assert result.status == LiveExecutorStatus.EXECUTOR_DISABLED.value
        assert result.executed is False
        assert not target.exists()


class TestApprovalRouteNotWiredToExecutor:
    def test_approval_route_records_without_calling_executor(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("ELYSIA_LIVE_EXECUTOR_ENABLED", raising=False)
        monkeypatch.setenv("ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED", "true")

        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)
        store = LiveActionApprovalRouteStore()

        smoke = register_harmless_smoke_packet_for_approval(
            store,
            workspace,
            repo_root=ROOT,
            expires_at=_future_expires_at(),
        )
        body, code = record_operator_decision_for_packet(
            store,
            smoke.packet.packet_id,
            {
                "decision": "APPROVE",
                "operator_id": "operator-route",
                "reason": "route must not execute",
                "approved_scope": f"write {HARMLESS_LIVE_SMOKE_RELATIVE_TARGET}",
                "packet_content_hash": compute_packet_content_hash(smoke.packet),
            },
        )

        assert code == 200
        assert body["executed"] is False
        assert body["executor_called"] is False
        assert not target.exists()

    def test_executor_module_has_no_forbidden_imports_or_calls(self):
        source = EXECUTOR_MODULE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden_calls = {
            "subprocess",
            "open",
            "Popen",
            "run_for_proposal",
            "apply_mutation",
            "requests",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls
        assert "subprocess" not in source
        assert "project_guardian.core" not in source
        assert "elysia.api.server" not in source

    def test_approval_route_does_not_import_executor(self):
        source = APPROVAL_ROUTE_MODULE.read_text(encoding="utf-8")
        assert "live_action_executor" not in source
