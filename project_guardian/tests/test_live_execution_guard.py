"""Unit tests for the fail-closed live-execution guard."""

from __future__ import annotations

import ast
import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from project_guardian.governance.live_execution_guard import (
    AUTONOMY_CONTEXT_DENIED,
    BLOCKED_RISK_DENIED,
    CONFIG_DISABLED,
    EXECUTOR_NOT_ALLOWLISTED,
    HIGH_RISK_DENIED,
    LIVE_EXECUTION_DISABLED,
    MEDIUM_RISK_REQUIRES_EXPLICIT_APPROVAL,
    MISSING_DRY_RUN_TRACE,
    MISSING_EXECUTOR_ALLOWLIST,
    MISSING_OPERATOR_CONFIRMATION,
    RAW_COMMAND_DENIED,
    ROLLBACK_REQUIRED_FOR_MUTATION,
    SELF_MODIFICATION_DENIED,
    STALE_DRY_RUN_TRACE,
    LiveExecutionRequest,
    evaluate_live_execution_request,
)


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "project_guardian" / "governance" / "live_execution_guard.py"


def _fresh_time() -> datetime:
    return datetime(2026, 5, 19, 18, 0, tzinfo=timezone.utc)


def _valid_request(**overrides) -> LiveExecutionRequest:
    now = _fresh_time()
    data = {
        "request_id": "req-1",
        "source_entrypoint": "operator_chat",
        "config_enabled": True,
        "entrypoint_enabled": True,
        "live_execution_enabled": True,
        "risk_level": "low",
        "action_type": "safe_noop",
        "target": "safe_noop",
        "executor_name": "safe_noop_executor",
        "executor_allowlist": ("safe_noop_executor",),
        "operator_confirmed": True,
        "operator_confirmation_id": "confirm-1",
        "dry_run_trace_id": "trace-1",
        "dry_run_trace_completed_at": now - timedelta(seconds=30),
        "now": now,
    }
    data.update(overrides)
    return LiveExecutionRequest(**data)


def _deny_reason(request: LiveExecutionRequest) -> tuple[str, ...]:
    decision = evaluate_live_execution_request(request)
    assert decision.allowed is False
    return decision.reasons


def test_default_deny():
    decision = evaluate_live_execution_request()
    assert decision.allowed is False
    assert CONFIG_DISABLED in decision.reasons
    assert LIVE_EXECUTION_DISABLED in decision.reasons


def test_config_disabled_deny():
    reasons = _deny_reason(_valid_request(config_enabled=False))
    assert CONFIG_DISABLED in reasons


def test_missing_operator_confirmation_deny():
    reasons = _deny_reason(_valid_request(operator_confirmed=False, operator_confirmation_id=""))
    assert MISSING_OPERATOR_CONFIRMATION in reasons


def test_missing_dry_run_trace_deny():
    reasons = _deny_reason(_valid_request(dry_run_trace_id="", dry_run_trace_completed_at=None))
    assert MISSING_DRY_RUN_TRACE in reasons


def test_stale_dry_run_trace_deny():
    now = _fresh_time()
    reasons = _deny_reason(
        _valid_request(
            dry_run_trace_completed_at=now - timedelta(seconds=901),
            now=now,
            dry_run_trace_ttl_seconds=900,
        )
    )
    assert STALE_DRY_RUN_TRACE in reasons


def test_high_risk_deny():
    reasons = _deny_reason(_valid_request(risk_level="high"))
    assert HIGH_RISK_DENIED in reasons


def test_blocked_risk_deny():
    reasons = _deny_reason(_valid_request(risk_level="blocked"))
    assert BLOCKED_RISK_DENIED in reasons


def test_medium_risk_requires_explicit_approval():
    reasons = _deny_reason(_valid_request(risk_level="medium", explicit_medium_risk_approval=False))
    assert MEDIUM_RISK_REQUIRES_EXPLICIT_APPROVAL in reasons

    decision = evaluate_live_execution_request(
        _valid_request(risk_level="medium", explicit_medium_risk_approval=True)
    )
    assert decision.allowed is True


def test_missing_executor_allowlist_deny():
    reasons = _deny_reason(_valid_request(executor_allowlist=()))
    assert MISSING_EXECUTOR_ALLOWLIST in reasons


def test_raw_command_deny():
    reasons = _deny_reason(
        _valid_request(
            action_type="shell_command",
            target="terminal",
            raw_text="powershell Remove-Item -Recurse C:\\temp",
        )
    )
    assert RAW_COMMAND_DENIED in reasons


def test_self_modification_deny():
    reasons = _deny_reason(_valid_request(is_self_modification=True))
    assert SELF_MODIFICATION_DENIED in reasons


def test_autonomy_context_deny():
    reasons = _deny_reason(_valid_request(source_entrypoint="autonomy", is_autonomy_context=True))
    assert AUTONOMY_CONTEXT_DENIED in reasons


def test_file_code_mutation_without_rollback_deny():
    reasons = _deny_reason(
        _valid_request(mutates_files=True, mutates_code=True, rollback_available=False, rollback_plan_id="")
    )
    assert ROLLBACK_REQUIRED_FOR_MUTATION in reasons


def test_valid_low_risk_request_allowed_only_when_config_says_live_execution_is_enabled():
    assert evaluate_live_execution_request(_valid_request()).allowed is True

    decision = evaluate_live_execution_request(_valid_request(live_execution_enabled=False))
    assert decision.allowed is False
    assert LIVE_EXECUTION_DISABLED in decision.reasons


def test_executor_not_in_allowlist_denied():
    reasons = _deny_reason(_valid_request(executor_name="other_executor"))
    assert EXECUTOR_NOT_ALLOWLISTED in reasons


def test_decision_serializable():
    decision = evaluate_live_execution_request(_valid_request())
    json.dumps(asdict(decision))
    json.dumps(decision.to_dict())


def test_module_contains_no_shell_subprocess_execution_calls():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))

    forbidden_imports = {"subprocess"}
    forbidden_calls = {
        ("os", "system"),
        ("subprocess", "run"),
        ("subprocess", "call"),
        ("subprocess", "check_call"),
        ("subprocess", "check_output"),
        ("subprocess", "Popen"),
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported = {alias.name.split(".", 1)[0] for alias in node.names}
            assert not (imported & forbidden_imports)
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".", 1)[0] not in forbidden_imports
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            base = node.func.value
            if isinstance(base, ast.Name):
                assert (base.id, node.func.attr) not in forbidden_calls
