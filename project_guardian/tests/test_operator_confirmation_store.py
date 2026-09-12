# project_guardian/tests/test_operator_confirmation_store.py
"""Tests for operator confirmation store (data-only; no live execution)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from project_guardian.governance.operator_confirmation_store import (
    OperatorConfirmationStore,
    confirmation_to_guard_context,
    create_operator_confirmation,
    get_operator_confirmation,
    is_confirmation_valid_for_request,
    list_operator_confirmations,
    mark_operator_confirmation_used,
    revoke_operator_confirmation,
    sanitize_confirmation_record,
)


def _now() -> datetime:
    return datetime(2026, 5, 18, 12, 0, 0, tzinfo=timezone.utc)


def _valid_kwargs(**overrides):
    base = {
        "operator_id": "op1",
        "conversation_id": "control_panel",
        "dry_run_trace_id": "trace-abc",
        "confirmed_action_id": "act-123",
        "action_summary": "Invoke brain:noop",
        "action_type": "capability_invoke",
        "tool_name": "brain:noop",
        "risk_level": "low",
        "executor_allowlisted": True,
        "rollback_available": False,
        "prompt_contract_valid": True,
        "ttl_seconds": 900.0,
        "now": _now(),
        "confirmation_id": "conf_test_1",
    }
    base.update(overrides)
    return base


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    return tmp_path / "operator_confirmations.jsonl"


@pytest.fixture
def store(store_path: Path) -> OperatorConfirmationStore:
    return OperatorConfirmationStore(store_path)


def test_create_record_with_required_fields(store: OperatorConfirmationStore):
    rec, errors = store.create_operator_confirmation(**_valid_kwargs())
    assert errors == []
    assert rec is not None
    assert rec.operator_confirmation_id == "conf_test_1"
    assert rec.status == "pending"
    assert rec.dry_run_trace_id == "trace-abc"
    assert rec.confirmed_action_id == "act-123"
    assert store.store_path.is_file()


def test_record_persists_across_store_instances(store_path: Path):
    s1 = OperatorConfirmationStore(store_path)
    rec, _ = s1.create_operator_confirmation(**_valid_kwargs(confirmation_id="conf_persist"))
    assert rec is not None

    s2 = OperatorConfirmationStore(store_path)
    loaded = s2.get_operator_confirmation("conf_persist", now=_now())
    assert loaded is not None
    assert loaded.confirmed_action_id == "act-123"


def test_expired_confirmation_is_invalid(store: OperatorConfirmationStore):
    store.create_operator_confirmation(**_valid_kwargs(confirmation_id="conf_exp", ttl_seconds=60.0))
    later = _now() + timedelta(seconds=120)
    ok, reason = store.is_confirmation_valid_for_request(
        "conf_exp",
        dry_run_trace_id="trace-abc",
        confirmed_action_id="act-123",
        now=later,
    )
    assert ok is False
    assert reason == "expired"


def test_used_confirmation_is_invalid(store: OperatorConfirmationStore):
    store.create_operator_confirmation(**_valid_kwargs(confirmation_id="conf_used"))
    updated, status = store.mark_operator_confirmation_used("conf_used", now=_now())
    assert status == "ok"
    assert updated is not None
    assert updated.status == "used"
    assert updated.used_at

    ok, reason = store.is_confirmation_valid_for_request(
        "conf_used",
        dry_run_trace_id="trace-abc",
        confirmed_action_id="act-123",
        now=_now(),
    )
    assert ok is False
    assert reason == "already_used"


def test_revoked_confirmation_is_invalid(store: OperatorConfirmationStore):
    store.create_operator_confirmation(**_valid_kwargs(confirmation_id="conf_rev"))
    store.revoke_operator_confirmation("conf_rev", now=_now())
    ok, reason = store.is_confirmation_valid_for_request(
        "conf_rev",
        dry_run_trace_id="trace-abc",
        confirmed_action_id="act-123",
        now=_now(),
    )
    assert ok is False
    assert reason == "revoked"


def test_mismatched_dry_run_trace_id_invalid(store: OperatorConfirmationStore):
    store.create_operator_confirmation(**_valid_kwargs(confirmation_id="conf_trace"))
    ok, reason = store.is_confirmation_valid_for_request(
        "conf_trace",
        dry_run_trace_id="other-trace",
        confirmed_action_id="act-123",
        now=_now(),
    )
    assert ok is False
    assert reason == "dry_run_trace_mismatch"


def test_mismatched_confirmed_action_id_invalid(store: OperatorConfirmationStore):
    store.create_operator_confirmation(**_valid_kwargs(confirmation_id="conf_act"))
    ok, reason = store.is_confirmation_valid_for_request(
        "conf_act",
        dry_run_trace_id="trace-abc",
        confirmed_action_id="act-other",
        now=_now(),
    )
    assert ok is False
    assert reason == "confirmed_action_mismatch"


@pytest.mark.parametrize("risk", ["high", "blocked", "critical"])
def test_high_blocked_risk_invalid_at_create(store: OperatorConfirmationStore, risk: str):
    rec, errors = store.create_operator_confirmation(**_valid_kwargs(risk_level=risk, confirmation_id=f"conf_{risk}"))
    assert rec is None
    assert "risk_not_confirmable" in errors


def test_high_risk_invalid_even_if_record_existed(store_path: Path):
    """Synthetic row injection is not used; create rejects high risk."""
    store = OperatorConfirmationStore(store_path)
    rec, errors = store.create_operator_confirmation(**_valid_kwargs(risk_level="high"))
    assert rec is None
    assert errors


def test_autonomy_context_invalid_at_create(store: OperatorConfirmationStore):
    rec, errors = store.create_operator_confirmation(
        **_valid_kwargs(autonomy_context=True, confirmation_id="conf_auto")
    )
    assert rec is None
    assert "autonomy_context" in errors


def test_self_modification_invalid_unless_future_allowed(store: OperatorConfirmationStore):
    rec, errors = store.create_operator_confirmation(
        **_valid_kwargs(self_modification=True, confirmation_id="conf_self")
    )
    assert rec is None
    assert "self_modification" in errors

    rec2, errors2 = store.create_operator_confirmation(
        **_valid_kwargs(
            self_modification=True,
            confirmation_id="conf_self_ok",
            allow_self_modification_workflow=True,
        )
    )
    assert errors2 == []
    assert rec2 is not None
    ok, reason = store.is_confirmation_valid_for_request(
        "conf_self_ok",
        dry_run_trace_id="trace-abc",
        confirmed_action_id="act-123",
        allow_self_modification_workflow=True,
        now=_now(),
    )
    assert ok is True
    assert reason == "valid"


def test_secrets_are_redacted():
    raw = {
        "operator_confirmation_id": "c1",
        "action_summary": "ok",
        "metadata": {"api_key": "sk-secret1234567890", "note": "visible"},
        "message": "do not leak",
    }
    clean = sanitize_confirmation_record(raw)
    assert "sk-secret" not in str(clean.get("metadata", {}))
    assert "redacted" in str(clean.get("metadata", {}).get("api_key", ""))
    assert "redacted" in str(clean.get("message", ""))


def test_mark_used_is_recorded(store: OperatorConfirmationStore):
    store.create_operator_confirmation(**_valid_kwargs(confirmation_id="conf_mark"))
    rec, status = store.mark_operator_confirmation_used("conf_mark", now=_now())
    assert status == "ok"
    assert rec is not None
    assert rec.used_at
    loaded = store.get_operator_confirmation("conf_mark", now=_now())
    assert loaded is not None
    assert loaded.status == "used"


def test_listing_returns_sanitized_records(store: OperatorConfirmationStore):
    store.create_operator_confirmation(
        **_valid_kwargs(
            confirmation_id="conf_list",
            metadata={"password": "hunter2", "safe": "yes"},
        )
    )
    rows = store.list_operator_confirmations(conversation_id="control_panel", now=_now())
    assert len(rows) >= 1
    row = rows[0]
    assert row["operator_confirmation_id"] == "conf_list"
    meta = row.get("metadata") or {}
    assert "hunter2" not in str(meta)


def test_confirmation_to_guard_context_maps_expected_fields(store: OperatorConfirmationStore):
    rec, _ = store.create_operator_confirmation(**_valid_kwargs(confirmation_id="conf_ctx"))
    assert rec is not None
    ctx = confirmation_to_guard_context(rec, source_entrypoint="operator_chat")
    assert ctx["operator_confirmation_id"] == "conf_ctx"
    assert ctx["operator_confirmed"] is True
    assert ctx["dry_run_trace_id"] == "trace-abc"
    assert ctx["live_execution_tool_name"] == "brain:noop"
    assert ctx["medium_risk_approved"] is False
    assert ctx["executor_allowlisted"] is True


def test_no_live_execution_autonomy_shell_llm_calls():
    """Store module must not invoke shell, subprocess, autonomy, or LLM clients."""
    import project_guardian.governance.operator_confirmation_store as mod

    source = Path(mod.__file__).read_text(encoding="utf-8").lower()
    forbidden = (
        "subprocess",
        "os.system",
        "openai",
        "requests.get",
        "requests.post",
        "httpx",
        "run_autonomous",
        "brainpipeline.run",
    )
    for token in forbidden:
        assert token not in source, f"unexpected {token} in store module"


def test_medium_risk_requires_approval_on_use(store: OperatorConfirmationStore):
    store.create_operator_confirmation(
        **_valid_kwargs(
            confirmation_id="conf_med",
            risk_level="medium",
            medium_risk_approved=False,
        )
    )
    ok, reason = store.is_confirmation_valid_for_request(
        "conf_med",
        dry_run_trace_id="trace-abc",
        confirmed_action_id="act-123",
        medium_risk_approved=False,
        now=_now(),
    )
    assert ok is False
    assert reason == "medium_risk_approval_required"

    ok2, reason2 = store.is_confirmation_valid_for_request(
        "conf_med",
        dry_run_trace_id="trace-abc",
        confirmed_action_id="act-123",
        medium_risk_approved=True,
        now=_now(),
    )
    assert ok2 is True
    assert reason2 == "valid"


def test_module_level_helpers_use_custom_path(store_path: Path):
    rec, errors = create_operator_confirmation(store_path=store_path, **_valid_kwargs(confirmation_id="conf_mod"))
    assert errors == []
    assert rec is not None
    assert get_operator_confirmation("conf_mod", store_path=store_path, now=_now()) is not None
    assert list_operator_confirmations(store_path=store_path, limit=5)
