"""Tests for live action executor — disabled by default; harmless smoke when enabled."""

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
    HARMLESS_LIVE_SMOKE_CONTENT,
    HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
    HARMLESS_LIVE_SMOKE_TARGET_FILENAME,
    compute_harmless_smoke_content_hash,
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


def _past_expires_at(*, hours: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _approved_request(
    workspace: Path,
    *,
    packet_id: str = "packet-001",
    decision_id: str = "decision-001",
    operator_decision: str = "APPROVE",
    expires_at: str | None = None,
    expected_content_hash: str | None = None,
    action_category: str = "harmless_live_smoke",
    target_path: str = HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
) -> LiveActionExecutionRequest:
    return LiveActionExecutionRequest(
        approval_packet_id=packet_id,
        operator_decision_id=decision_id,
        operator_decision=operator_decision,
        action_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
        action_category=action_category,
        target_path=target_path,
        workspace_root=str(workspace.resolve()),
        expected_content_hash=expected_content_hash or compute_harmless_smoke_content_hash(),
        rollback_plan_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
        audit_record_id="audit-001",
        dry_run_trace_id="trace-001",
        expires_at=expires_at or _future_expires_at(),
        repo_root=str(ROOT),
    )


@pytest.fixture
def disabled_executor(monkeypatch):
    monkeypatch.delenv("ELYSIA_LIVE_EXECUTOR_ENABLED", raising=False)
    yield


@pytest.fixture
def enabled_executor(monkeypatch):
    monkeypatch.setenv("ELYSIA_LIVE_EXECUTOR_ENABLED", "true")
    yield


class TestExecutorDisabledByDefault:
    def test_unset_flag_returns_executor_disabled(self, tmp_path, disabled_executor):
        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)
        assert not target.exists()

        result = execute_live_action(_approved_request(workspace))
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
        result = execute_live_action(_approved_request(workspace))

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
                operator_decision="APPROVE",
                action_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
                action_category="harmless_live_smoke",
                target_path=HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
                workspace_root=str(workspace.resolve()),
                expected_content_hash=smoke.content_hash,
                rollback_plan_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
                audit_record_id="audit-approved",
                dry_run_trace_id="trace-approved",
                expires_at=_future_expires_at(),
                repo_root=str(ROOT),
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

        execute_live_action(_approved_request(workspace))

        assert not workspace.exists()
        assert not target.exists()

    def test_disabled_result_is_json_serializable(self, tmp_path, disabled_executor):
        workspace = _smoke_workspace(tmp_path)
        result = execute_live_action(_approved_request(workspace))
        payload = serialize_live_action_execution_result(result)
        encoded = serialize_live_action_execution_result_json(result)

        json.loads(encoded)
        assert payload["executed"] is False
        assert payload["executor_called"] is True
        assert payload["failure_code"] == LiveExecutorFailureCode.EXECUTOR_DISABLED.value

    def test_disabled_does_not_change_readiness(self, tmp_path, disabled_executor):
        workspace = _smoke_workspace(tmp_path)
        before = evaluate_live_mode_readiness()
        execute_live_action(_approved_request(workspace))
        after = evaluate_live_mode_readiness()

        assert before.ready_for_limited_live_mode is False
        assert after.ready_for_limited_live_mode is False
        assert after.status.value == "BLOCKED"
        assert any(
            key in b
            for key in (
                "PRODUCTION_LIVE_EXECUTION_DISABLED_BY_DEFAULT",
                "AUTONOMY_CONFIG_DISABLED",
            )
            for b in after.blockers
        )
        assert not any(
            key in b
            for key in (
                "LIMITED_LIVE_PROFILE_NOT_DECLARED",
                "OPERATOR_LIMITED_LIVE_RUNBOOK_MISSING",
            )
            for b in after.blockers
        )

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

    def test_approval_route_imports_executor_only_inside_functions(self):
        source = APPROVAL_ROUTE_MODULE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                assert node.module != "project_guardian.live_action_executor"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "project_guardian.live_action_executor"


class TestEnabledHarmlessSmokeExecutor:
    def test_enabled_writes_exact_smoke_file_in_tmp_workspace(
        self, tmp_path, enabled_executor
    ):
        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)
        assert not target.exists()

        result = execute_live_action(_approved_request(workspace))

        assert result.status == LiveExecutorStatus.EXECUTION_SUCCEEDED.value
        assert result.executed is True
        assert result.execution_permitted is True
        assert result.executor_called is True
        assert result.action_category == "harmless_live_smoke"
        assert result.target_path == HARMLESS_LIVE_SMOKE_RELATIVE_TARGET
        assert result.before_hash is None
        assert result.after_hash is not None
        assert result.rollback_summary is not None
        assert target.exists()
        assert target.read_bytes() == HARMLESS_LIVE_SMOKE_CONTENT
        files = [p for p in workspace.rglob("*") if p.is_file()]
        assert files == [target]

    def test_enabled_rejects_missing_operator_decision(
        self, tmp_path, enabled_executor
    ):
        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)
        request = _approved_request(workspace, operator_decision="")

        result = execute_live_action(request)

        assert result.status == LiveExecutorStatus.EXECUTION_DENIED.value
        assert result.failure_code == LiveExecutorFailureCode.OPERATOR_DECISION_NOT_APPROVED.value
        assert result.executed is False
        assert not target.exists()

    def test_enabled_rejects_deny_decision(self, tmp_path, enabled_executor):
        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)

        result = execute_live_action(_approved_request(workspace, operator_decision="DENY"))

        assert result.status == LiveExecutorStatus.EXECUTION_DENIED.value
        assert result.failure_code == LiveExecutorFailureCode.OPERATOR_DECISION_NOT_APPROVED.value
        assert result.executed is False
        assert not target.exists()

    def test_enabled_rejects_expired_packet(self, tmp_path, enabled_executor):
        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)

        result = execute_live_action(
            _approved_request(workspace, expires_at=_past_expires_at())
        )

        assert result.status == LiveExecutorStatus.EXECUTION_DENIED.value
        assert result.failure_code == LiveExecutorFailureCode.PACKET_EXPIRED.value
        assert result.executed is False
        assert not target.exists()

    def test_enabled_rejects_content_hash_mismatch(self, tmp_path, enabled_executor):
        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)

        result = execute_live_action(
            _approved_request(workspace, expected_content_hash="deadbeef")
        )

        assert result.status == LiveExecutorStatus.EXECUTION_DENIED.value
        assert result.failure_code == LiveExecutorFailureCode.CONTENT_HASH_MISMATCH.value
        assert result.executed is False
        assert not target.exists()

    def test_enabled_rejects_unsafe_target(self, tmp_path, enabled_executor):
        workspace = _smoke_workspace(tmp_path)
        repo_target = ROOT / "approved_smoke.txt"

        result = execute_live_action(
            _approved_request(workspace, target_path="approved_smoke.txt")
        )

        assert result.status == LiveExecutorStatus.EXECUTION_DENIED.value
        assert result.failure_code == LiveExecutorFailureCode.TARGET_OUTSIDE_SMOKE_WORKSPACE.value
        assert result.executed is False
        assert not repo_target.exists()

    def test_enabled_rejects_non_smoke_action_category(self, tmp_path, enabled_executor):
        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)

        result = execute_live_action(
            _approved_request(workspace, action_category="mutation_apply")
        )

        assert result.status == LiveExecutorStatus.EXECUTION_DENIED.value
        assert result.failure_code == LiveExecutorFailureCode.ACTION_NOT_ALLOWLISTED.value
        assert result.executed is False
        assert not target.exists()

    def test_enabled_does_not_create_repo_root_files(self, tmp_path, enabled_executor):
        workspace = _smoke_workspace(tmp_path)
        repo_target = ROOT / "approved_smoke.txt"
        assert not repo_target.exists()

        execute_live_action(_approved_request(workspace))

        assert not repo_target.exists()

    def test_rollback_deletes_created_smoke_file(self, tmp_path, enabled_executor):
        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)

        execute_live_action(_approved_request(workspace))
        assert target.exists()

        rollback = rollback_harmless_smoke_write(
            workspace_root=str(workspace),
            target_path=HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
            rollback_plan_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
            repo_root=str(ROOT),
        )

        assert rollback.status == LiveExecutorStatus.ROLLBACK_SUCCEEDED.value
        assert not target.exists()

    def test_rollback_restores_prior_content(self, tmp_path, enabled_executor):
        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)
        prior = b"prior smoke baseline\n"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(prior)

        execute_live_action(_approved_request(workspace))
        assert target.read_bytes() == HARMLESS_LIVE_SMOKE_CONTENT

        rollback = rollback_harmless_smoke_write(
            workspace_root=str(workspace),
            target_path=HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
            rollback_plan_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
            repo_root=str(ROOT),
            prior_content=prior,
        )

        assert rollback.status == LiveExecutorStatus.ROLLBACK_SUCCEEDED.value
        assert target.read_bytes() == prior

    def test_rollback_rejects_unsafe_target(self, tmp_path, enabled_executor):
        workspace = _smoke_workspace(tmp_path)
        repo_target = ROOT / "approved_smoke.txt"

        rollback = rollback_harmless_smoke_write(
            workspace_root=str(ROOT),
            target_path="approved_smoke.txt",
            rollback_plan_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
            repo_root=str(ROOT),
        )

        assert rollback.status == LiveExecutorStatus.EXECUTION_DENIED.value
        assert rollback.failure_code == LiveExecutorFailureCode.TARGET_OUTSIDE_SMOKE_WORKSPACE.value
        assert not repo_target.exists()

    def test_enabled_execution_does_not_mark_readiness_ready(
        self, tmp_path, enabled_executor
    ):
        workspace = _smoke_workspace(tmp_path)
        before = evaluate_live_mode_readiness()

        execute_live_action(_approved_request(workspace))

        after = evaluate_live_mode_readiness()
        assert before.ready_for_limited_live_mode is False
        assert after.ready_for_limited_live_mode is False
        assert after.status.value == "BLOCKED"
        assert any(
            key in b
            for key in (
                "PRODUCTION_LIVE_EXECUTION_DISABLED_BY_DEFAULT",
                "AUTONOMY_CONFIG_DISABLED",
            )
            for b in after.blockers
        )
        assert not any(
            key in b
            for key in (
                "LIMITED_LIVE_PROFILE_NOT_DECLARED",
                "OPERATOR_LIMITED_LIVE_RUNBOOK_MISSING",
            )
            for b in after.blockers
        )
