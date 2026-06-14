"""Tests for triple-gated approval route to harmless smoke executor wiring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from project_guardian.live_action_approval_route import (
    LiveActionApprovalRouteStore,
    compute_packet_content_hash,
    is_approval_route_executes_smoke_enabled,
    is_live_action_approval_route_enabled,
    record_operator_decision_for_packet,
)
from project_guardian.live_action_executor import (
    rollback_harmless_smoke_write,
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
)

ROOT = Path(__file__).resolve().parents[2]


def _smoke_workspace(tmp_path: Path) -> Path:
    return tmp_path / "isolated_smoke_root"


def _smoke_target(workspace: Path) -> Path:
    return workspace / "live_smoke_workspace" / HARMLESS_LIVE_SMOKE_TARGET_FILENAME


def _future_expires_at(*, hours: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _past_expires_at(*, hours: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _approve_body(smoke) -> dict:
    return {
        "decision": "APPROVE",
        "operator_id": "operator-wiring",
        "reason": "wiring test",
        "approved_scope": f"write {HARMLESS_LIVE_SMOKE_RELATIVE_TARGET}",
        "packet_content_hash": compute_packet_content_hash(smoke.packet),
    }


def _register_smoke(store, tmp_path, *, expires_at: str | None = None):
    workspace = _smoke_workspace(tmp_path)
    smoke = register_harmless_smoke_packet_for_approval(
        store,
        workspace,
        repo_root=ROOT,
        expires_at=expires_at or _future_expires_at(),
    )
    return smoke, workspace


@pytest.fixture
def store(tmp_path):
    return LiveActionApprovalRouteStore(audit_path=tmp_path / "wiring_decisions.jsonl")


@pytest.fixture
def route_enabled(monkeypatch):
    monkeypatch.setenv("ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED", "true")
    yield


@pytest.fixture
def executor_enabled(monkeypatch):
    monkeypatch.setenv("ELYSIA_LIVE_EXECUTOR_ENABLED", "true")
    yield


@pytest.fixture
def executes_smoke_enabled(monkeypatch):
    monkeypatch.setenv("ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE", "true")
    yield


@pytest.fixture
def triple_gates(route_enabled, executor_enabled, executes_smoke_enabled):
    yield


def _assert_no_execution(body: dict) -> None:
    assert body["executor_called"] is False
    assert body["executed"] is False
    assert body["execution_permitted"] is False


class TestDefaultDecisionOnly:
    def test_default_route_approve_records_only(self, tmp_path, store, route_enabled):
        smoke, workspace = _register_smoke(store, tmp_path)
        target = _smoke_target(workspace)

        body, code = record_operator_decision_for_packet(
            store, smoke.packet.packet_id, _approve_body(smoke)
        )

        assert code == 200
        assert body["decision_recorded"] is True
        _assert_no_execution(body)
        assert not target.exists()

    def test_route_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED", raising=False)
        monkeypatch.delenv("ELYSIA_APPROVAL_ROUTE_EXECUTES_SMOKE", raising=False)
        assert is_live_action_approval_route_enabled() is False
        assert is_approval_route_executes_smoke_enabled() is False


class TestPartialGates:
    def test_route_on_executor_off_no_write(
        self, tmp_path, store, route_enabled, executes_smoke_enabled
    ):
        smoke, workspace = _register_smoke(store, tmp_path)
        target = _smoke_target(workspace)

        body, code = record_operator_decision_for_packet(
            store, smoke.packet.packet_id, _approve_body(smoke)
        )

        assert code == 200
        _assert_no_execution(body)
        assert not target.exists()

    def test_route_and_executor_on_executes_smoke_off_no_write(
        self, tmp_path, store, route_enabled, executor_enabled
    ):
        smoke, workspace = _register_smoke(store, tmp_path)
        target = _smoke_target(workspace)

        body, code = record_operator_decision_for_packet(
            store, smoke.packet.packet_id, _approve_body(smoke)
        )

        assert code == 200
        _assert_no_execution(body)
        assert not target.exists()


class TestTripleGateExecution:
    def test_all_gates_true_writes_exact_smoke_file(
        self, tmp_path, store, triple_gates
    ):
        smoke, workspace = _register_smoke(store, tmp_path)
        target = _smoke_target(workspace)

        body, code = record_operator_decision_for_packet(
            store, smoke.packet.packet_id, _approve_body(smoke)
        )

        assert code == 200
        assert body["executor_called"] is True
        assert body["execution_permitted"] is True
        assert body["executed"] is True
        assert body["execution_result"] is not None
        assert body["approval_packet_id"] == smoke.packet.packet_id
        assert body["operator_decision_id"] == body["decision_id"]
        assert target.exists()
        assert target.read_bytes() == HARMLESS_LIVE_SMOKE_CONTENT

    def test_triple_gate_response_fields(self, tmp_path, store, triple_gates):
        smoke, _workspace = _register_smoke(store, tmp_path)

        body, code = record_operator_decision_for_packet(
            store, smoke.packet.packet_id, _approve_body(smoke)
        )

        assert code == 200
        assert body["executor_called"] is True
        assert body["execution_permitted"] is True
        assert body["executed"] is True
        assert body["execution_result"]["status"] == "EXECUTION_SUCCEEDED"


class TestNonExecutingDecisions:
    @pytest.mark.parametrize(
        "decision",
        ["DENY", "REQUEST_CHANGES", "CANCEL", "EXPIRE"],
    )
    def test_non_approve_never_executes(
        self, tmp_path, store, triple_gates, decision: str
    ):
        smoke, workspace = _register_smoke(store, tmp_path)
        target = _smoke_target(workspace)

        body, code = record_operator_decision_for_packet(
            store,
            smoke.packet.packet_id,
            {
                "decision": decision,
                "operator_id": "operator-deny",
                "reason": "must not execute",
                "packet_content_hash": compute_packet_content_hash(smoke.packet),
            },
        )

        assert code in (200, 422)
        _assert_no_execution(body)
        assert not target.exists()


class TestValidationBlocks:
    def test_expired_packet_never_executes(self, tmp_path, store, triple_gates):
        smoke, workspace = _register_smoke(store, tmp_path, expires_at=_past_expires_at())
        target = _smoke_target(workspace)

        body, code = record_operator_decision_for_packet(
            store, smoke.packet.packet_id, _approve_body(smoke)
        )

        assert code == 409
        _assert_no_execution(body)
        assert not target.exists()

    def test_hash_mismatch_never_executes(self, tmp_path, store, triple_gates):
        smoke, workspace = _register_smoke(store, tmp_path)
        target = _smoke_target(workspace)
        bad_body = _approve_body(smoke)
        bad_body["packet_content_hash"] = "deadbeef"

        body, code = record_operator_decision_for_packet(
            store, smoke.packet.packet_id, bad_body
        )

        assert code == 409
        _assert_no_execution(body)
        assert not target.exists()

    def test_unsafe_workspace_never_executes(self, tmp_path, store, triple_gates):
        smoke, workspace = _register_smoke(store, tmp_path)
        target = _smoke_target(workspace)
        stored = store.get_stored_packet(smoke.packet.packet_id)
        assert stored is not None
        stored.workspace_root = str(ROOT)
        stored.repo_root = str(ROOT)

        body, code = record_operator_decision_for_packet(
            store, smoke.packet.packet_id, _approve_body(smoke)
        )

        assert code == 200
        assert body["executor_called"] is True
        assert body["executed"] is False
        assert body["execution_permitted"] is False
        assert not (ROOT / "approved_smoke.txt").exists()
        assert not target.exists()


class TestSafetyAndRollback:
    def test_no_repo_root_file_created(self, tmp_path, store, triple_gates):
        smoke, _workspace = _register_smoke(store, tmp_path)
        repo_target = ROOT / "approved_smoke.txt"
        assert not repo_target.exists()

        record_operator_decision_for_packet(
            store, smoke.packet.packet_id, _approve_body(smoke)
        )

        assert not repo_target.exists()

    def test_no_auto_rollback_after_success(self, tmp_path, store, triple_gates):
        smoke, workspace = _register_smoke(store, tmp_path)
        target = _smoke_target(workspace)

        record_operator_decision_for_packet(
            store, smoke.packet.packet_id, _approve_body(smoke)
        )

        assert target.exists()

    def test_explicit_rollback_after_route_execution(
        self, tmp_path, store, triple_gates, executor_enabled
    ):
        smoke, workspace = _register_smoke(store, tmp_path)
        target = _smoke_target(workspace)

        record_operator_decision_for_packet(
            store, smoke.packet.packet_id, _approve_body(smoke)
        )
        assert target.exists()

        rollback = rollback_harmless_smoke_write(
            workspace_root=str(workspace),
            target_path=HARMLESS_LIVE_SMOKE_RELATIVE_TARGET,
            rollback_plan_id=HARMLESS_LIVE_SMOKE_ACTION_ID,
            repo_root=str(ROOT),
        )

        assert rollback.status == "ROLLBACK_SUCCEEDED"
        assert not target.exists()


class TestReadinessStillBlocked:
    def test_readiness_remains_blocked_after_triple_gate_execution(
        self, tmp_path, store, triple_gates
    ):
        smoke, _workspace = _register_smoke(store, tmp_path)
        before = evaluate_live_mode_readiness()

        record_operator_decision_for_packet(
            store, smoke.packet.packet_id, _approve_body(smoke)
        )

        after = evaluate_live_mode_readiness()
        assert before.ready_for_limited_live_mode is False
        assert after.ready_for_limited_live_mode is False
        assert after.status.value == "BLOCKED"
        assert any(
            "APPROVAL_ROUTE_NOT_WIRED_TO_EXECUTOR" in b
            or "APPROVAL_ROUTE_DEFAULT_DISABLED" in b
            for b in after.blockers
        )
