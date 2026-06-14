"""Tests for passive live-action approval route scaffolding."""

from __future__ import annotations

import ast
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from project_guardian.live_action_approval_packet import build_live_action_approval_packet
from project_guardian.live_action_approval_route import (
    ApprovalRouteErrorCode,
    LiveActionApprovalRouteStore,
    compute_packet_content_hash,
    get_approval_decision_trail,
    get_approval_packet_detail,
    is_live_action_approval_route_enabled,
    list_pending_approval_packets,
    record_operator_decision_for_packet,
)
from project_guardian.live_action_gate import ActionRiskCategory, build_approval_request
from project_guardian.live_action_rollback import (
    LiveActionRollbackPlan,
    RollbackAvailability,
    RollbackStrategy,
)

ROOT = Path(__file__).resolve().parents[2]
ROUTE_MODULE = ROOT / "project_guardian" / "live_action_approval_route.py"


def _rollback_plan(
    *,
    action_id: str,
    strategy: RollbackStrategy = RollbackStrategy.MANUAL_ONLY,
    availability: RollbackAvailability = RollbackAvailability.PARTIAL,
    **kwargs,
) -> LiveActionRollbackPlan:
    defaults = {
        "action_id": action_id,
        "strategy": strategy,
        "availability": availability,
        "manual_steps": ("Delete file",),
    }
    defaults.update(kwargs)
    return LiveActionRollbackPlan(**defaults)


def _ready_packet(**request_kwargs):
    defaults = {
        "proposed_action": "write_report:weekly",
        "reason": "digest",
        "risk_category": ActionRiskCategory.WRITE_REPORT,
        "target": "REPORTS/weekly.md",
        "expected_result": "sha256:abc123",
        "rollback_plan": "manual rollback",
        "writes_files": True,
    }
    defaults.update(request_kwargs)
    request = build_approval_request(**defaults)
    rollback = _rollback_plan(action_id=request.action_id)
    packet = build_live_action_approval_packet(request, rollback)
    assert packet.ready_for_operator_review is True
    return packet


def _future_expires_at(*, hours: int = 1) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def _past_expires_at(*, hours: int = 1) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _register_ready_packet(
    store: LiveActionApprovalRouteStore,
    *,
    expires_at: str | None = None,
    **request_kwargs,
):
    packet = _ready_packet(**request_kwargs)
    store.register_packet(
        packet,
        expires_at=expires_at or _future_expires_at(),
        dry_run_trace_id="trace-001",
        dry_run_trace_summary={
            "outcome": "dry_run_blocked_not_executed",
            "blocked": True,
            "executed": False,
        },
    )
    return packet


@pytest.fixture
def enabled_route(monkeypatch):
    monkeypatch.setenv("ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED", "true")
    yield


@pytest.fixture
def store(tmp_path):
    return LiveActionApprovalRouteStore(audit_path=tmp_path / "decisions.jsonl")


class TestRouteDisabledByDefault:
    def test_route_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED", raising=False)
        assert is_live_action_approval_route_enabled() is False

    def test_list_pending_returns_403_when_disabled(self, store, monkeypatch):
        monkeypatch.delenv("ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED", raising=False)
        _register_ready_packet(store)
        body, code = list_pending_approval_packets(store)
        assert code == 403
        assert body["error_code"] == ApprovalRouteErrorCode.APPROVAL_ROUTE_DISABLED.value
        assert body["execution_permitted"] is False
        assert body["executed"] is False
        assert body["executor_called"] is False


class TestPacketListing:
    def test_list_pending_returns_reviewable_packets(self, store, enabled_route):
        packet = _register_ready_packet(store)
        body, code = list_pending_approval_packets(store)
        assert code == 200
        assert body["count"] == 1
        assert body["packets"][0]["packet_id"] == packet.packet_id
        assert body["execution_permitted"] is False
        assert body["executed"] is False

    def test_expired_packet_excluded_from_pending(self, store, enabled_route):
        _register_ready_packet(store, expires_at=_past_expires_at())
        body, code = list_pending_approval_packets(store)
        assert code == 200
        assert body["count"] == 0


class TestPacketDetail:
    def test_detail_includes_operator_fields(self, store, enabled_route):
        packet = _register_ready_packet(store)
        body, code = get_approval_packet_detail(store, packet.packet_id)
        assert code == 200
        assert body["packet_id"] == packet.packet_id
        assert body["proposed_target_path"] == "REPORTS/weekly.md"
        assert body["proposed_content_hash"] == "sha256:abc123"
        assert "rollback_plan_summary" in body
        assert "audit_record_preview" in body
        assert body["dry_run_trace_summary"]["trace_id"] == "trace-001"
        assert body["packet_content_hash"] == compute_packet_content_hash(packet)
        assert body["executor_called"] is False


class TestOperatorDecisions:
    def test_approve_records_decision_does_not_execute(self, store, enabled_route, tmp_path):
        packet = _register_ready_packet(store)
        target = tmp_path / "would_write.txt"
        body, code = record_operator_decision_for_packet(
            store,
            packet.packet_id,
            {
                "decision": "APPROVE",
                "operator_id": "operator-1",
                "reason": "scope acceptable",
                "approved_scope": "write REPORTS/weekly.md only",
                "packet_content_hash": compute_packet_content_hash(packet),
            },
        )
        assert code == 200
        assert body["validation"]["valid"] is True
        assert body["validation"]["execution_permitted"] is False
        assert body["executed"] is False
        assert body["executor_called"] is False
        assert not target.exists()

    def test_deny_records_decision_does_not_execute(self, store, enabled_route, tmp_path):
        packet = _register_ready_packet(store)
        target = tmp_path / "would_write.txt"
        body, code = record_operator_decision_for_packet(
            store,
            packet.packet_id,
            {
                "decision": "DENY",
                "operator_id": "operator-1",
                "reason": "too risky",
            },
        )
        assert code == 200
        assert body["validation"]["safety_verdict"] == "DENIED"
        assert body["executed"] is False
        assert body["executor_called"] is False
        assert not target.exists()

    def test_expired_packet_cannot_be_approved(self, store, enabled_route):
        packet = _register_ready_packet(store, expires_at=_past_expires_at())
        body, code = record_operator_decision_for_packet(
            store,
            packet.packet_id,
            {
                "decision": "APPROVE",
                "operator_id": "operator-1",
                "reason": "late approval",
                "approved_scope": "write only",
                "packet_content_hash": compute_packet_content_hash(packet),
            },
        )
        assert code == 409
        assert body["error_code"] == ApprovalRouteErrorCode.PACKET_EXPIRED.value
        assert body["executed"] is False

    def test_approve_requires_exact_packet_hash(self, store, enabled_route):
        packet = _register_ready_packet(store)
        body, code = record_operator_decision_for_packet(
            store,
            packet.packet_id,
            {
                "decision": "APPROVE",
                "operator_id": "operator-1",
                "reason": "ok",
                "approved_scope": "write only",
                "packet_content_hash": "deadbeef",
            },
        )
        assert code == 409
        assert body["error_code"] == ApprovalRouteErrorCode.PACKET_HASH_MISMATCH.value

    def test_terminal_decision_blocks_second_decision(self, store, enabled_route):
        packet = _register_ready_packet(store)
        first_body, first_code = record_operator_decision_for_packet(
            store,
            packet.packet_id,
            {
                "decision": "DENY",
                "operator_id": "operator-1",
                "reason": "denied",
            },
        )
        assert first_code == 200
        second_body, second_code = record_operator_decision_for_packet(
            store,
            packet.packet_id,
            {
                "decision": "APPROVE",
                "operator_id": "operator-1",
                "reason": "retry",
                "approved_scope": "write only",
                "packet_content_hash": compute_packet_content_hash(packet),
            },
        )
        assert second_code == 409
        assert second_body["error_code"] == ApprovalRouteErrorCode.DECISION_ALREADY_RECORDED.value


class TestAuditTrail:
    def test_trail_is_append_only(self, store, enabled_route, tmp_path):
        packet = _register_ready_packet(store)
        record_operator_decision_for_packet(
            store,
            packet.packet_id,
            {
                "decision": "REQUEST_CHANGES",
                "operator_id": "operator-1",
                "reason": "add detail",
            },
        )
        record_operator_decision_for_packet(
            store,
            packet.packet_id,
            {
                "decision": "DENY",
                "operator_id": "operator-1",
                "reason": "still not acceptable",
            },
        )
        body, code = get_approval_decision_trail(store, packet.packet_id)
        assert code == 200
        assert body["decision_count"] == 2
        assert body["decisions"][0]["decision"] == "REQUEST_CHANGES"
        assert body["decisions"][1]["decision"] == "DENY"
        assert body["executor_called"] is False

        audit_path = tmp_path / "decisions.jsonl"
        assert audit_path.is_file()
        lines = [line for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(lines) == 2


class TestNoExecutionImports:
    def test_route_module_has_no_executor_calls(self):
        source = ROUTE_MODULE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden_names = {
            "execute_live_action",
            "run_for_proposal",
            "ImplementerAgent",
            "apply_mutation",
            "dispatch",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_names

    def test_route_module_does_not_import_server_or_core(self):
        source = ROUTE_MODULE.read_text(encoding="utf-8")
        assert "elysia.api.server" not in source
        assert "project_guardian.core" not in source


class TestServerRouteWiring:
    def test_server_live_action_routes_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED", raising=False)
        from elysia.api.server import RuntimeAPIServer
        from elysia.events import EventBus

        server = RuntimeAPIServer(status_provider=lambda: {}, event_bus=EventBus())
        client = server._app.test_client()
        response = client.get("/api/live-action/approval-packets/pending")
        assert response.status_code == 403
        payload = response.get_json()
        assert payload["error_code"] == ApprovalRouteErrorCode.APPROVAL_ROUTE_DISABLED.value
        assert payload["executed"] is False
        assert payload["executor_called"] is False

    def test_server_post_decision_does_not_execute(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ELYSIA_LIVE_ACTION_APPROVAL_ROUTE_ENABLED", "true")
        from elysia.api.server import RuntimeAPIServer
        from elysia.events import EventBus

        store = LiveActionApprovalRouteStore(audit_path=tmp_path / "api_decisions.jsonl")
        packet = _ready_packet()
        store.register_packet(packet, expires_at=_future_expires_at())

        server = RuntimeAPIServer(
            status_provider=lambda: {},
            event_bus=EventBus(),
            live_action_approval_store=store,
        )
        client = server._app.test_client()
        response = client.post(
            f"/api/live-action/approval-packets/{packet.packet_id}/decision",
            json={
                "decision": "APPROVE",
                "operator_id": "api-operator",
                "reason": "reviewed via api",
                "approved_scope": "write REPORTS/weekly.md only",
                "packet_content_hash": compute_packet_content_hash(packet),
            },
        )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["executed"] is False
        assert payload["executor_called"] is False
        assert payload["execution_permitted"] is False
        assert not (tmp_path / "approved_smoke.txt").exists()
