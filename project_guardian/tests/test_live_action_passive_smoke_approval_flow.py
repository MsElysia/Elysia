"""Passive end-to-end harmless smoke approval flow integration tests."""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from project_guardian.live_action_approval_route import (
    ApprovalRouteErrorCode,
    LiveActionApprovalRouteStore,
    compute_packet_content_hash,
    get_approval_decision_trail,
    get_approval_packet_detail,
    list_pending_approval_packets,
    record_operator_decision_for_packet,
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
FLOW_MODULE = ROOT / "project_guardian" / "live_action_passive_smoke_flow.py"


def _smoke_workspace(tmp_path: Path) -> Path:
    return tmp_path / "isolated_smoke_root"


def _smoke_target(workspace: Path) -> Path:
    return workspace / "live_smoke_workspace" / HARMLESS_LIVE_SMOKE_TARGET_FILENAME


def _future_expires_at(*, hours: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _past_expires_at(*, hours: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _assert_no_execution_fields(payload: dict) -> None:
    assert payload["execution_permitted"] is False
    assert payload["executed"] is False
    assert payload["executor_called"] is False


@pytest.fixture
def enabled_route(monkeypatch):
    monkeypatch.setenv("ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED", "true")
    yield


@pytest.fixture
def store(tmp_path):
    return LiveActionApprovalRouteStore(audit_path=tmp_path / "flow_decisions.jsonl")


class TestPassiveSmokeApprovalFlow:
    def test_end_to_end_approve_flow_without_execution(
        self, tmp_path, store, enabled_route
    ):
        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)
        assert not target.exists()

        smoke = register_harmless_smoke_packet_for_approval(
            store,
            workspace,
            repo_root=ROOT,
            expires_at=_future_expires_at(),
            dry_run_trace_id="trace-smoke-001",
        )
        packet_id = smoke.packet.packet_id

        pending, pending_code = list_pending_approval_packets(store)
        assert pending_code == 200
        assert pending["count"] == 1
        assert pending["packets"][0]["packet_id"] == packet_id
        _assert_no_execution_fields(pending)

        detail, detail_code = get_approval_packet_detail(store, packet_id)
        assert detail_code == 200
        assert detail["action_id"] == HARMLESS_LIVE_SMOKE_ACTION_ID
        assert detail["proposed_target_path"] == HARMLESS_LIVE_SMOKE_RELATIVE_TARGET
        assert detail["packet_content_hash"] == compute_packet_content_hash(smoke.packet)
        _assert_no_execution_fields(detail)

        decision_body, decision_code = record_operator_decision_for_packet(
            store,
            packet_id,
            {
                "decision": "APPROVE",
                "operator_id": "operator-smoke",
                "reason": "harmless smoke scope reviewed",
                "approved_scope": (
                    f"single-file write {HARMLESS_LIVE_SMOKE_RELATIVE_TARGET} only"
                ),
                "packet_content_hash": compute_packet_content_hash(smoke.packet),
            },
        )
        assert decision_code == 200
        assert decision_body["validation"]["valid"] is True
        assert decision_body["validation"]["safety_verdict"] == (
            "APPROVAL_RECORDED_EXECUTION_STILL_BLOCKED"
        )
        _assert_no_execution_fields(decision_body)

        trail, trail_code = get_approval_decision_trail(store, packet_id)
        assert trail_code == 200
        assert trail["decision_count"] == 1
        assert trail["decisions"][0]["decision"] == "APPROVE"
        assert trail["decisions"][0]["packet_id"] == packet_id
        assert "audit_record_preview" in trail
        _assert_no_execution_fields(trail)

        assert not target.exists()
        assert not workspace.exists()

    def test_deny_flow_records_without_execution(self, tmp_path, store, enabled_route):
        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)

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
                "decision": "DENY",
                "operator_id": "operator-smoke",
                "reason": "not ready for smoke",
            },
        )
        assert code == 200
        assert body["validation"]["safety_verdict"] == "DENIED"
        _assert_no_execution_fields(body)
        assert not target.exists()

    def test_expired_packet_cannot_be_approved(self, tmp_path, store, enabled_route):
        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)

        smoke = register_harmless_smoke_packet_for_approval(
            store,
            workspace,
            repo_root=ROOT,
            expires_at=_past_expires_at(),
        )

        pending, _ = list_pending_approval_packets(store)
        assert pending["count"] == 0

        body, code = record_operator_decision_for_packet(
            store,
            smoke.packet.packet_id,
            {
                "decision": "APPROVE",
                "operator_id": "operator-smoke",
                "reason": "late approval attempt",
                "approved_scope": "write only",
                "packet_content_hash": compute_packet_content_hash(smoke.packet),
            },
        )
        assert code == 409
        assert body["error_code"] == ApprovalRouteErrorCode.PACKET_EXPIRED.value
        _assert_no_execution_fields(body)
        assert not target.exists()

    def test_hash_mismatch_cannot_be_approved(self, tmp_path, store, enabled_route):
        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)

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
                "operator_id": "operator-smoke",
                "reason": "wrong hash",
                "approved_scope": "write only",
                "packet_content_hash": "not-the-real-hash",
            },
        )
        assert code == 409
        assert body["error_code"] == ApprovalRouteErrorCode.PACKET_HASH_MISMATCH.value
        _assert_no_execution_fields(body)
        assert not target.exists()

    def test_audit_trail_includes_packet_and_decision_metadata(
        self, tmp_path, store, enabled_route
    ):
        workspace = _smoke_workspace(tmp_path)
        smoke = register_harmless_smoke_packet_for_approval(
            store,
            workspace,
            repo_root=ROOT,
            expires_at=_future_expires_at(),
            dry_run_trace_id="trace-audit-001",
        )
        packet_id = smoke.packet.packet_id

        record_operator_decision_for_packet(
            store,
            packet_id,
            {
                "decision": "APPROVE",
                "operator_id": "operator-audit",
                "reason": "audit trail check",
                "approved_scope": f"write {HARMLESS_LIVE_SMOKE_RELATIVE_TARGET}",
                "packet_content_hash": compute_packet_content_hash(smoke.packet),
            },
        )

        trail, code = get_approval_decision_trail(store, packet_id)
        assert code == 200
        assert trail["packet_id"] == packet_id
        assert trail["dry_run_trace_summary"]["trace_id"] == "trace-audit-001"
        assert trail["audit_record_preview"]["action_id"] == HARMLESS_LIVE_SMOKE_ACTION_ID
        assert trail["decisions"][0]["operator_id"] == "operator-audit"
        assert trail["decisions"][0]["action_id"] == HARMLESS_LIVE_SMOKE_ACTION_ID

    def test_no_smoke_target_file_before_or_after_flow(
        self, tmp_path, store, enabled_route
    ):
        workspace = _smoke_workspace(tmp_path)
        target = _smoke_target(workspace)
        assert not target.exists()

        smoke = register_harmless_smoke_packet_for_approval(
            store,
            workspace,
            repo_root=ROOT,
            expires_at=_future_expires_at(),
        )
        assert not target.exists()

        record_operator_decision_for_packet(
            store,
            smoke.packet.packet_id,
            {
                "decision": "APPROVE",
                "operator_id": "operator-smoke",
                "reason": "file must not exist",
                "approved_scope": "write only",
                "packet_content_hash": compute_packet_content_hash(smoke.packet),
            },
        )
        assert not target.exists()

    def test_readiness_remains_blocked_after_flow(self, tmp_path, store, enabled_route):
        workspace = _smoke_workspace(tmp_path)
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
                "operator_id": "operator-smoke",
                "reason": "readiness must stay blocked",
                "approved_scope": "write only",
                "packet_content_hash": compute_packet_content_hash(smoke.packet),
            },
        )

        report = evaluate_live_mode_readiness()
        assert report.ready_for_limited_live_mode is False
        assert report.status.value == "BLOCKED"
        assert any(
            "APPROVAL_ROUTE_NOT_WIRED_TO_EXECUTOR" in blocker
            or "APPROVAL_ROUTE_DEFAULT_DISABLED" in blocker
            for blocker in report.blockers
        )
        assert not any(
            "HARMLESS_LIVE_ACTION_SMOKE_VERIFIED" in blocker
            for blocker in report.blockers
        )


class TestPassiveFlowNoExecution:
    def test_flow_glue_has_no_executor_calls(self):
        source = FLOW_MODULE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {
            "execute_live_action",
            "run_for_proposal",
            "ImplementerAgent",
            "apply_mutation",
            "open",
            "write",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden
