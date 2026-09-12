# project_guardian/tests/test_operator_confirmation_visibility.py
"""Read-only operator confirmation governance visibility (no live execution)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from elysia.api.server import RuntimeAPIServer
from elysia.events import EventBus
from project_guardian.governance.operator_confirmation_store import (
    OperatorConfirmationStore,
    mark_operator_confirmation_used,
)

try:
    from project_guardian.governance.operator_confirmation_store import DEFAULT_STORE_PATH
except ImportError:
    from project_guardian.governance.operator_confirmation_store import (
        DEFAULT_CONFIRMATIONS_PATH as DEFAULT_STORE_PATH,
    )
from project_guardian.governance.operator_confirmation_visibility import (
    assert_response_has_no_forbidden_fields,
    build_operator_confirmation_detail_payload,
    build_operator_confirmations_list_payload,
)

_NOW = datetime(2026, 5, 18, 12, 0, 0, tzinfo=timezone.utc)


def _create(store_path: Path, conf_id: str = "conf_vis", **kw) -> None:
    store = OperatorConfirmationStore(store_path)
    params = {
        "operator_id": "op",
        "conversation_id": "panel",
        "dry_run_trace_id": "trace-1",
        "confirmed_action_id": "act-1",
        "action_summary": "Invoke brain:noop",
        "action_type": "capability_invoke",
        "tool_name": "brain:noop",
        "risk_level": "low",
        "executor_allowlisted": True,
        "confirmation_id": conf_id,
        "ttl_seconds": 3600,
        "now": _NOW,
    }
    params.update(kw)
    rec, errors = store.create_operator_confirmation(**params)
    assert errors == []
    assert rec is not None


def test_empty_store_returns_available_with_zero_counts(tmp_path):
    store_path = tmp_path / "missing.jsonl"
    body = build_operator_confirmations_list_payload(store_path=store_path)
    assert body["available"] is True
    assert body["read_only"] is True
    assert body["counts"] == {"pending": 0, "used": 0, "expired": 0, "revoked": 0, "invalid": 0}
    assert body["confirmations"] == []
    assert body["live_execution_enabled"] is False
    assert body["autonomy_enabled"] is False


def test_counts_by_status(tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    _create(store_path, "conf_pending")
    _create(store_path, "conf_exp", ttl_seconds=60.0)
    _create(store_path, "conf_used")
    _create(store_path, "conf_rev")
    mark_operator_confirmation_used("conf_used", store_path=store_path, now=_NOW)
    OperatorConfirmationStore(store_path).revoke_operator_confirmation("conf_rev", now=_NOW)

    body = build_operator_confirmations_list_payload(
        store_path=store_path,
        now=_NOW + timedelta(seconds=120),
    )

    assert body["counts"]["pending"] == 1
    assert body["counts"]["expired"] == 1
    assert body["counts"]["used"] == 1
    assert body["counts"]["revoked"] == 1


def test_list_returns_sanitized_confirmation_summaries(tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    _create(store_path, "conf_a")
    body = build_operator_confirmations_list_payload(store_path=store_path, limit=25, now=_NOW)
    assert len(body["confirmations"]) == 1
    row = body["confirmations"][0]
    assert row["operator_confirmation_id"] == "conf_a"
    assert row["status"] == "pending"
    assert row["dry_run_trace_id"] == "trace-1"
    assert "action_summary" in row


def test_detail_returns_sanitized_confirmation(tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    _create(store_path, "conf_detail")
    body, code = build_operator_confirmation_detail_payload(
        "conf_detail", store_path=store_path, now=_NOW
    )
    assert code == 200
    assert body["found"] is True
    assert body["confirmation"]["operator_confirmation_id"] == "conf_detail"


def test_expired_confirmation_reported_invalid(tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    _create(store_path, "conf_exp", ttl_seconds=60.0)
    later = _NOW + timedelta(seconds=120)
    body = build_operator_confirmations_list_payload(store_path=store_path, now=later)
    row = body["confirmations"][0]
    assert row["status"] == "expired"
    assert row["valid_now"] is False
    assert "expired" in row["validation_notes"][0]


def test_used_confirmation_reported_correctly(tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    _create(store_path, "conf_used")
    mark_operator_confirmation_used("conf_used", store_path=store_path, now=_NOW)
    body = build_operator_confirmations_list_payload(store_path=store_path, now=_NOW)
    row = body["confirmations"][0]
    assert row["status"] == "used"
    assert row["valid_now"] is False
    assert "used" in row["validation_notes"][0]


def test_revoked_confirmation_reported_correctly(tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    _create(store_path, "conf_rev")
    OperatorConfirmationStore(store_path).revoke_operator_confirmation("conf_rev", now=_NOW)
    body = build_operator_confirmations_list_payload(store_path=store_path, now=_NOW)
    assert body["confirmations"][0]["status"] == "revoked"


def test_secrets_are_redacted(tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    store = OperatorConfirmationStore(store_path)
    store.create_operator_confirmation(
        operator_id="op",
        conversation_id="c",
        dry_run_trace_id="t",
        confirmed_action_id="a",
        action_summary="token sk-secret1234567890",
        action_type="x",
        tool_name="brain:noop",
        metadata={"api_key": "sk-live-secret-value"},
        confirmation_id="conf_sec",
        now=_NOW,
    )
    body = build_operator_confirmations_list_payload(store_path=store_path)
    blob = json.dumps(body)
    assert "sk-live-secret-value" not in blob
    assert "sk-secret1234567890" not in blob


def test_raw_prompt_and_trace_fields_not_exposed(tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    _create(store_path)
    body = build_operator_confirmations_list_payload(store_path=store_path)
    assert_response_has_no_forbidden_fields(body)


def test_list_limit_enforced(tmp_path):
    store_path = tmp_path / "confirmations.jsonl"
    for index in range(4):
        _create(store_path, f"conf_limit_{index}")

    body = build_operator_confirmations_list_payload(store_path=store_path, limit=2, now=_NOW)

    assert body["total"] == 4
    assert body["returned"] == 2
    assert body["limit"] == 2
    assert len(body["confirmations"]) == 2


def test_endpoint_does_not_create_update_or_mark_used(tmp_path, monkeypatch):
    store_path = tmp_path / "confirmations.jsonl"
    _create(store_path, "conf_stable")
    monkeypatch.setattr(
        "project_guardian.governance.operator_confirmation_visibility.DEFAULT_STORE_PATH",
        store_path,
    )
    monkeypatch.setattr(
        "project_guardian.governance.operator_confirmation_store.DEFAULT_CONFIRMATIONS_PATH",
        store_path,
    )
    before_lines = len(store_path.read_text(encoding="utf-8").splitlines())

    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
    )
    client = server._app.test_client()
    r1 = client.get("/api/governance/operator-confirmations")
    r2 = client.get("/api/governance/operator-confirmations/conf_stable")
    assert r1.status_code == 200
    assert r2.status_code == 200

    after_lines = len(store_path.read_text(encoding="utf-8").splitlines())
    assert after_lines == before_lines
    rec = OperatorConfirmationStore(store_path).get_operator_confirmation("conf_stable", now=_NOW)
    assert rec is not None
    assert rec.status == "pending"


def test_live_execution_status_reports_false_by_default(tmp_path):
    body = build_operator_confirmations_list_payload(store_path=tmp_path / "empty.jsonl")
    assert body["live_execution_enabled"] is False
    assert body["dry_run"] is True
    assert body["brain_pipeline_enabled"] is False


def test_visibility_module_has_no_shell_llm_or_live_exec_calls():
    path = (
        Path(__file__).resolve().parents[1]
        / "governance"
        / "operator_confirmation_visibility.py"
    )
    text = path.read_text(encoding="utf-8").lower()
    for token in (
        "subprocess",
        "os.system",
        "openai",
        "requests.get",
        "requests.post",
        "httpx",
        "mark_operator_confirmation_used",
        "create_operator_confirmation",
        "evaluate_live_execution_request",
    ):
        assert token not in text


def test_runtime_api_list_endpoint(tmp_path, monkeypatch):
    store_path = tmp_path / "confirmations.jsonl"
    _create(store_path, "conf_api")
    monkeypatch.setattr(
        "project_guardian.governance.operator_confirmation_visibility.DEFAULT_STORE_PATH",
        store_path,
    )
    monkeypatch.setattr(
        "project_guardian.governance.operator_confirmation_store.DEFAULT_CONFIRMATIONS_PATH",
        store_path,
    )
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
    )
    r = server._app.test_client().get("/api/governance/operator-confirmations?limit=5")
    assert r.status_code == 200
    body = r.get_json()
    assert body["read_only"] is True
    assert body["live_execution_enabled"] is False
