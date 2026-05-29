"""Phase 1a contract tests for dry-run autonomy safety (tests-first; no production wiring).

Defines expected behavior from docs/DRY_RUN_AUTONOMY_PHASE1_PLAN.md. Tests that require
Phase 1b+ production hooks are marked xfail until wiring lands.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from unittest.mock import patch

import pytest

from project_guardian.governance.live_execution_guard import (
    AUTONOMY_CONTEXT_DENIED,
    LiveExecutionRequest,
    evaluate_live_execution_request,
)

ROOT = Path(__file__).resolve().parents[2]
AUTONOMY_CONFIG = ROOT / "config" / "autonomy.json"
PHASE1_PLAN = ROOT / "docs" / "DRY_RUN_AUTONOMY_PHASE1_PLAN.md"
CORE_PATH = ROOT / "project_guardian" / "core.py"
UI_PANEL_PATH = ROOT / "project_guardian" / "ui_control_panel.py"
API_SERVER_PATH = ROOT / "project_guardian" / "api_server.py"
SMOKE_SCRIPT = ROOT / "scripts" / "run_safe_stack_smoke_tests.py"
PHASE1_CONTRACT_TEST = "project_guardian/tests/test_dry_run_autonomy_phase1_contract.py"

PHASE1_XFAIL_REASON = (
    "Phase 1b+ autonomy dry-run guard not wired in production yet "
    "(see docs/DRY_RUN_AUTONOMY_PHASE1_PLAN.md)"
)

AUTONOMY_SENSITIVE_TASK_ROOTS: frozenset[str] = frozenset(
    {
        "mutation_router",
        "mutation_engine",
        "implementer_core",
        "tool_executor",
        "run_autonomous_cycle",
    }
)

PHASE1_WIRING_MARKERS: frozenset[str] = frozenset(
    {
        "run_brain_pipeline_for_autonomy",
        "_autonomy_phase1_dry_run",
        "dry_run_only",
        "autonomy_dry_run_audit",
        "append_autonomy_dry_run_audit",
        "ELYSIA_AUTONOMY_KILL",
        "max_cycles_per_request",
    }
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _phase1_autonomy_guard_wired() -> bool:
    """True when core.py exposes the planned Phase 1 dry-run guard hooks."""
    if not CORE_PATH.is_file():
        return False
    text = _read_text(CORE_PATH)
    has_dry_run_wrapper = any(
        m in text
        for m in (
            "run_brain_pipeline_for_autonomy",
            "_autonomy_phase1_dry_run",
            "dry_run_only",
        )
    )
    has_audit_or_kill = any(
        m in text
        for m in (
            "autonomy_dry_run_audit",
            "append_autonomy_dry_run_audit",
            "ELYSIA_AUTONOMY_KILL",
        )
    )
    return has_dry_run_wrapper and has_audit_or_kill


def _function_body(module_path: Path, func_name: str) -> str:
    tree = ast.parse(_read_text(module_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            lines = _read_text(module_path).splitlines()
            segment = lines[node.lineno - 1 : node.end_lineno]
            return "\n".join(segment)
    raise AssertionError(f"{func_name} not found in {module_path}")


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location("run_safe_stack_smoke_tests", SMOKE_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- 1. config default off (PASS) ---


def test_autonomy_config_defaults_enabled_false() -> None:
    assert AUTONOMY_CONFIG.is_file(), "committed config/autonomy.json missing"
    data = json.loads(_read_text(AUTONOMY_CONFIG))
    assert data.get("enabled") is False


# --- 2. plan document (PASS) ---


def test_phase1_plan_document_exists_and_mandates_dry_run_only() -> None:
    assert PHASE1_PLAN.is_file()
    text = _read_text(PHASE1_PLAN).lower()
    assert "dry-run-only autonomy" in text or "dry-run only" in text
    assert "no side effects" in text
    assert "autonomy_context_denied" in text or "autonomy_context=true" in text
    assert "do not run autonomy until phase 1 tests pass" in text


# --- 3. execute-cycle guard (contract + xfail when wired expectation) ---


def test_execute_cycle_route_exists_and_documents_cycle_entry() -> None:
    text = _read_text(UI_PANEL_PATH)
    assert "/api/autonomy/execute-cycle" in text
    assert "run_autonomous_cycle" in text


@pytest.mark.xfail(
    _phase1_autonomy_guard_wired() is False,
    reason=PHASE1_XFAIL_REASON,
    strict=False,
)
def test_execute_cycle_must_not_execute_tools_without_phase1_guard() -> None:
    """When Phase 1 guard is wired, execute-cycle must return dry_run and never execute tools."""
    assert _phase1_autonomy_guard_wired()
    route_body = _function_body(UI_PANEL_PATH, "execute_autonomy_cycle")
    assert "dry_run" in route_body
    assert 'result.get("executed"' in route_body


# --- 4. execute_capability in dry-run (PASS disabled; xfail enabled dry-run) ---


def test_run_autonomous_cycle_disabled_never_calls_execute_capability() -> None:
    from project_guardian.core import GuardianCore

    calls: List[Any] = []

    def _boom(*_a: Any, **_k: Any) -> None:
        calls.append(True)
        raise AssertionError("execute_capability_kind must not run when autonomy disabled")

    stub = object.__new__(GuardianCore)
    stub._load_autonomy_config = lambda: {"enabled": False}  # type: ignore[method-assign]

    with patch(
        "project_guardian.capability_execution.execute_capability_kind",
        side_effect=_boom,
    ):
        out = GuardianCore.run_autonomous_cycle(stub)

    assert out.get("executed") is False
    assert calls == []


@pytest.mark.xfail(
    _phase1_autonomy_guard_wired() is False,
    reason=PHASE1_XFAIL_REASON,
    strict=False,
)
def test_run_autonomous_cycle_dry_run_mode_never_calls_execute_capability() -> None:
    from project_guardian.core import GuardianCore

    calls: List[Any] = []

    def _track(*_a: Any, **_k: Any) -> Dict[str, Any]:
        calls.append(True)
        return {"ok": False}

    stub = object.__new__(GuardianCore)
    stub._load_autonomy_config = lambda: {  # type: ignore[method-assign]
        "enabled": True,
        "dry_run_only": True,
        "allowed_actions": ["use_capability/test"],
        "max_actions_per_hour": 40,
        "allow_dynamic_capability_actions": True,
    }
    stub.get_next_action = lambda: {  # type: ignore[method-assign]
        "action": "use_capability/test",
        "can_auto_execute": True,
        "metadata": {},
    }
    stub._load_mistral_decider_config = lambda: {}  # type: ignore[method-assign]
    stub._autonomy_action_times = []  # type: ignore[attr-defined]

    with patch(
        "project_guardian.capability_execution.execute_capability_kind",
        side_effect=_track,
    ):
        out = GuardianCore.run_autonomous_cycle(stub)

    assert out.get("executed") is False
    assert out.get("dry_run") is True
    assert calls == []


def test_autonomy_dry_run_only_false_is_non_overridable_in_phase1() -> None:
    from project_guardian.autonomy_dry_run_guard import autonomy_dry_run_only

    assert autonomy_dry_run_only({"dry_run_only": False}) is True
    assert autonomy_dry_run_only({"enabled": True, "dry_run_only": False}) is True


def test_run_autonomous_cycle_dry_run_only_false_never_calls_execute_capability() -> None:
    from project_guardian.core import GuardianCore

    calls: List[Any] = []

    def _track(*_a: Any, **_k: Any) -> Dict[str, Any]:
        calls.append(True)
        return {"ok": False}

    stub = object.__new__(GuardianCore)
    stub._load_autonomy_config = lambda: {  # type: ignore[method-assign]
        "enabled": True,
        "dry_run_only": False,
        "allowed_actions": ["use_capability/test"],
        "max_actions_per_hour": 40,
        "allow_dynamic_capability_actions": True,
    }
    stub.get_next_action = lambda: {  # type: ignore[method-assign]
        "action": "use_capability/test",
        "can_auto_execute": True,
        "metadata": {},
    }
    stub._load_mistral_decider_config = lambda: {}  # type: ignore[method-assign]
    stub._autonomy_action_times = []  # type: ignore[attr-defined]

    with patch(
        "project_guardian.capability_execution.execute_capability_kind",
        side_effect=_track,
    ):
        out = GuardianCore.run_autonomous_cycle(stub)

    assert out.get("executed") is False
    assert out.get("dry_run") is True
    assert out.get("reason") == "dry_run_only"
    assert calls == []


# --- 5. mutation denied in dry-run (xfail) ---


@pytest.mark.xfail(
    _phase1_autonomy_guard_wired() is False,
    reason=PHASE1_XFAIL_REASON,
    strict=False,
)
def test_mutation_path_denied_in_autonomy_dry_run() -> None:
    body = _function_body(CORE_PATH, "run_autonomous_cycle")
    assert "consider_mutation" not in body or "dry_run_only" in body
    assert "_autonomy_phase1_dry_run" in body or "dry_run_only" in body


# --- 6. proposal implement denied (PASS static) ---


def test_proposal_implementation_not_reachable_from_run_autonomous_cycle() -> None:
    body = _function_body(CORE_PATH, "run_autonomous_cycle")
    assert "run_for_proposal" not in body
    assert "ImplementerAgent" not in body


# --- 7. subprocess/shell denied from cycle body (PASS static) ---


def test_subprocess_shell_denied_in_run_autonomous_cycle_body() -> None:
    body = _function_body(CORE_PATH, "run_autonomous_cycle")
    assert "subprocess.run" not in body
    assert "os.system" not in body
    assert "powershell" not in body.lower()


# --- 8. live_execution_guard autonomy context (PASS policy; xfail wiring) ---


def test_live_execution_guard_denies_autonomy_context() -> None:
    decision = evaluate_live_execution_request(
        LiveExecutionRequest(
            is_autonomy_context=True,
            source_entrypoint="autonomy",
            config_enabled=True,
            entrypoint_enabled=True,
            live_execution_enabled=True,
            risk_level="low",
            operator_confirmed=True,
            operator_confirmation_id="c1",
            executor_name="safe_noop_executor",
            executor_allowlist=("safe_noop_executor",),
            dry_run_trace_id="t1",
            dry_run_trace_completed_at="2026-05-25T12:00:00+00:00",
        )
    )
    assert decision.allowed is False
    assert AUTONOMY_CONTEXT_DENIED in decision.reasons


@pytest.mark.xfail(
    _phase1_autonomy_guard_wired() is False,
    reason=PHASE1_XFAIL_REASON,
    strict=False,
)
def test_run_autonomous_cycle_calls_live_execution_guard_with_autonomy_context() -> None:
    body = _function_body(CORE_PATH, "run_autonomous_cycle")
    assert "apply_live_execution_guard" in body or "apply_live_execution_guard_to_context" in body
    assert "autonomy_context" in body or "is_autonomy_context" in body


# --- 9. audit record (xfail) ---


@pytest.mark.xfail(
    _phase1_autonomy_guard_wired() is False,
    reason=PHASE1_XFAIL_REASON,
    strict=False,
)
def test_autonomy_cycle_emits_or_prepares_audit_record() -> None:
    text = _read_text(CORE_PATH)
    assert "autonomy_dry_run_audit" in text or "append_autonomy_dry_run_audit" in text


# --- 10. loop budget (PASS baseline; xfail strict cap) ---


def test_run_autonomous_cycle_invokes_get_next_action_at_most_once() -> None:
    body = _function_body(CORE_PATH, "run_autonomous_cycle")
    assert body.count("get_next_action(") <= 1


@pytest.mark.xfail(
    _phase1_autonomy_guard_wired() is False,
    reason=PHASE1_XFAIL_REASON,
    strict=False,
)
def test_loop_budget_enforces_one_bounded_cycle_per_request() -> None:
    text = _read_text(CORE_PATH)
    assert "max_cycles_per_request" in text


# --- 11. kill switch (xfail) ---


@pytest.mark.xfail(
    _phase1_autonomy_guard_wired() is False,
    reason=PHASE1_XFAIL_REASON,
    strict=False,
)
def test_kill_switch_prevents_autonomy_cycle() -> None:
    from project_guardian.core import GuardianCore

    calls: List[Any] = []

    def _track(*_a: Any, **_k: Any) -> Dict[str, Any]:
        calls.append(True)
        return {"ok": False}

    stub = object.__new__(GuardianCore)
    stub._load_autonomy_config = lambda: {"enabled": True, "allowed_actions": ["x"]}  # type: ignore[method-assign]
    stub.get_next_action = lambda: {"action": "x", "can_auto_execute": True}  # type: ignore[method-assign]
    stub._load_mistral_decider_config = lambda: {}  # type: ignore[method-assign]
    stub._autonomy_action_times = []  # type: ignore[attr-defined]

    with patch.dict(os.environ, {"ELYSIA_AUTONOMY_KILL": "1"}, clear=False):
        with patch(
            "project_guardian.capability_execution.execute_capability_kind",
            side_effect=_track,
        ):
            out = GuardianCore.run_autonomous_cycle(stub)

    assert out.get("executed") is False
    assert out.get("reason") == "kill_switch" or out.get("dry_run") is True
    assert calls == []


# --- 12. POST /api/tasks sensitive roots (PASS contract; xfail enforcement) ---


def test_contract_defines_sensitive_api_task_roots_for_autonomy_gating() -> None:
    assert AUTONOMY_SENSITIVE_TASK_ROOTS >= {
        "mutation_router",
        "mutation_engine",
        "implementer_core",
        "tool_executor",
    }


def test_api_task_resolution_roots_include_sensitive_surfaces() -> None:
    """Inventory: sensitive roots exist today and must be gated in Phase 1b+."""
    text = _read_text(API_SERVER_PATH)
    for root in AUTONOMY_SENSITIVE_TASK_ROOTS:
        if root == "run_autonomous_cycle":
            continue
        assert f'"{root}"' in text


@pytest.mark.xfail(
    _phase1_autonomy_guard_wired() is False,
    reason=PHASE1_XFAIL_REASON,
    strict=False,
)
def test_post_api_tasks_denies_sensitive_roots_in_autonomy_context() -> None:
    text = _read_text(API_SERVER_PATH)
    assert "autonomy_context" in text or "AUTONOMY_SENSITIVE" in text
    assert "_deny_autonomy_sensitive_task" in text or "_task_denied_in_autonomy_context" in text


# --- 13. safe-stack smoke gate (PASS) ---


def test_safe_stack_smoke_includes_phase1_contract_tests() -> None:
    mod = _load_smoke_module()
    declared = set(mod.declared_test_paths())
    assert PHASE1_CONTRACT_TEST in declared
    resolved = mod.resolve_smoke_test_paths(ROOT)
    assert PHASE1_CONTRACT_TEST in resolved


def test_safe_stack_smoke_script_lists_phase1_contract_in_required_paths() -> None:
    text = _read_text(SMOKE_SCRIPT)
    assert PHASE1_CONTRACT_TEST in text


# --- 14. Phase 1d-B dry-run decision trace (observation only) ---

DECISION_TRACE_REQUIRED_FIELDS: frozenset[str] = frozenset(
    {
        "trace_id",
        "timestamp",
        "source",
        "cycle_id",
        "proposed_action",
        "proposed_action_kind",
        "proposed_action_summary",
        "dry_run",
        "executed",
        "block_reasons",
        "live_execution_guard",
        "capability_called",
        "mutation_called",
        "proposal_implementation_called",
        "legacy_executor_reached",
        "notes",
    }
)


def _dry_run_stub(*, dry_run_only: bool):
    from project_guardian.core import GuardianCore

    stub = object.__new__(GuardianCore)
    stub._load_autonomy_config = lambda: {  # type: ignore[method-assign]
        "enabled": True,
        "dry_run_only": dry_run_only,
        "allowed_actions": ["use_capability/test"],
        "max_actions_per_hour": 40,
        "allow_dynamic_capability_actions": True,
    }
    stub.get_next_action = lambda: {  # type: ignore[method-assign]
        "action": "use_capability/test",
        "can_auto_execute": True,
        "metadata": {},
    }
    stub._load_mistral_decider_config = lambda: {}  # type: ignore[method-assign]
    stub._autonomy_action_times = []  # type: ignore[attr-defined]
    return stub


def test_decision_trace_helper_builds_required_fields_with_invariants() -> None:
    from project_guardian.autonomy_dry_run_guard import build_dry_run_decision_trace

    trace = build_dry_run_decision_trace(
        cycle_id="cyc-1",
        source="run_autonomous_cycle",
        proposed_action="use_capability/test",
        guard_meta={"allowed": False, "reasons": ["live_execution_disabled"]},
        extra_block_reasons=["dry_run_only"],
    )

    assert DECISION_TRACE_REQUIRED_FIELDS <= set(trace.keys())
    assert trace["dry_run"] is True
    assert trace["executed"] is False
    assert trace["capability_called"] is False
    assert trace["mutation_called"] is False
    assert trace["proposal_implementation_called"] is False
    assert trace["legacy_executor_reached"] is False
    assert trace["proposed_action_kind"] == "use_capability"
    assert "live_execution_disabled" in trace["block_reasons"]
    assert "dry_run_only" in trace["block_reasons"]
    # Must be JSON-serializable (no side effects, no live objects).
    json.dumps(trace)


@pytest.mark.xfail(
    _phase1_autonomy_guard_wired() is False,
    reason=PHASE1_XFAIL_REASON,
    strict=False,
)
def test_run_autonomous_cycle_emits_decision_trace_without_executing() -> None:
    from project_guardian.core import GuardianCore

    calls: List[Any] = []

    def _track(*_a: Any, **_k: Any) -> Dict[str, Any]:
        calls.append(True)
        raise AssertionError("execute_capability_kind must not run in Phase 1 dry-run")

    stub = _dry_run_stub(dry_run_only=True)

    with patch(
        "project_guardian.capability_execution.execute_capability_kind",
        side_effect=_track,
    ):
        out = GuardianCore.run_autonomous_cycle(stub)

    assert calls == []
    assert out.get("executed") is False
    assert out.get("dry_run") is True

    trace = out.get("decision_trace")
    assert isinstance(trace, dict)
    assert DECISION_TRACE_REQUIRED_FIELDS <= set(trace.keys())
    assert trace["dry_run"] is True
    assert trace["executed"] is False
    assert trace["capability_called"] is False
    assert trace["mutation_called"] is False
    assert trace["proposal_implementation_called"] is False
    assert trace["legacy_executor_reached"] is False
    assert trace["proposed_action"] == "use_capability/test"


@pytest.mark.xfail(
    _phase1_autonomy_guard_wired() is False,
    reason=PHASE1_XFAIL_REASON,
    strict=False,
)
def test_decision_trace_dry_run_only_false_still_blocks_execution() -> None:
    from project_guardian.core import GuardianCore

    calls: List[Any] = []

    def _track(*_a: Any, **_k: Any) -> Dict[str, Any]:
        calls.append(True)
        raise AssertionError("execute_capability_kind must not run even with dry_run_only=False")

    stub = _dry_run_stub(dry_run_only=False)

    with patch(
        "project_guardian.capability_execution.execute_capability_kind",
        side_effect=_track,
    ):
        out = GuardianCore.run_autonomous_cycle(stub)

    assert calls == []
    assert out.get("executed") is False
    assert out.get("dry_run") is True
    assert out.get("reason") == "dry_run_only"

    trace = out.get("decision_trace")
    assert isinstance(trace, dict)
    assert trace["dry_run"] is True
    assert trace["executed"] is False
    assert trace["legacy_executor_reached"] is False
    assert "dry_run_only" in trace["block_reasons"]


# --- 15. Phase 1d-B.2 dry-run trace summary (observation only) ---

SUMMARY_REQUIRED_FIELDS: frozenset[str] = frozenset(
    {
        "summary_id",
        "trace_id",
        "source",
        "proposed_action_kind",
        "proposed_action_summary",
        "outcome",
        "blocked",
        "block_reasons",
        "safety_summary",
        "execution_summary",
        "human_summary",
    }
)


def _sample_decision_trace() -> Dict[str, Any]:
    from project_guardian.autonomy_dry_run_guard import build_dry_run_decision_trace

    return build_dry_run_decision_trace(
        cycle_id="cyc-summary-1",
        source="run_autonomous_cycle",
        proposed_action="use_capability/test",
        guard_meta={"allowed": False, "reasons": ["live_execution_disabled"]},
        extra_block_reasons=["dry_run_only"],
    )


def test_summarize_decision_trace_is_serializable_and_reports_invariants() -> None:
    from project_guardian.autonomy_dry_run_guard import summarize_dry_run_decision_trace

    trace = _sample_decision_trace()
    summary = summarize_dry_run_decision_trace(trace)

    assert SUMMARY_REQUIRED_FIELDS <= set(summary.keys())
    json.dumps(summary)

    assert summary["blocked"] is True
    assert summary["outcome"] == "dry_run_blocked_not_executed"
    assert summary["execution_summary"]["dry_run"] is True
    assert summary["execution_summary"]["executed"] is False
    assert summary["safety_summary"] == {
        "capability_called": False,
        "mutation_called": False,
        "proposal_implementation_called": False,
        "legacy_executor_reached": False,
    }
    assert "live_execution_disabled" in summary["block_reasons"]
    assert "dry_run_only" in summary["block_reasons"]
    assert summary["proposed_action_kind"] == "use_capability"


def test_summarize_decision_trace_does_not_mutate_input() -> None:
    from project_guardian.autonomy_dry_run_guard import summarize_dry_run_decision_trace
    import copy

    trace = _sample_decision_trace()
    before = copy.deepcopy(trace)
    summarize_dry_run_decision_trace(trace)
    assert trace == before


def test_summarize_decision_trace_tolerates_missing_fields() -> None:
    from project_guardian.autonomy_dry_run_guard import summarize_dry_run_decision_trace

    summary = summarize_dry_run_decision_trace({})
    assert SUMMARY_REQUIRED_FIELDS <= set(summary.keys())
    json.dumps(summary)
    # Empty trace: no execution recorded => treated as dry-run blocked/not executed.
    assert summary["execution_summary"]["executed"] is False
    assert summary["blocked"] is True


@pytest.mark.xfail(
    _phase1_autonomy_guard_wired() is False,
    reason=PHASE1_XFAIL_REASON,
    strict=False,
)
def test_run_autonomous_cycle_result_contains_decision_trace_summary() -> None:
    from project_guardian.core import GuardianCore

    calls: List[Any] = []

    def _track(*_a: Any, **_k: Any) -> Dict[str, Any]:
        calls.append(True)
        raise AssertionError("execute_capability_kind must not run in Phase 1 dry-run")

    stub = _dry_run_stub(dry_run_only=False)

    with patch(
        "project_guardian.capability_execution.execute_capability_kind",
        side_effect=_track,
    ):
        out = GuardianCore.run_autonomous_cycle(stub)

    assert calls == []
    assert out.get("executed") is False
    assert out.get("dry_run") is True

    summary = out.get("decision_trace_summary")
    assert isinstance(summary, dict)
    assert SUMMARY_REQUIRED_FIELDS <= set(summary.keys())
    json.dumps(summary)
    assert summary["blocked"] is True
    assert summary["outcome"] == "dry_run_blocked_not_executed"
    assert summary["execution_summary"]["executed"] is False
    assert summary["safety_summary"]["capability_called"] is False
    assert summary["safety_summary"]["legacy_executor_reached"] is False


# --- 16. Phase 1d-B.3 dry-run decision report (observation only) ---

REPORT_REQUIRED_FIELDS: frozenset[str] = frozenset(
    {
        "report_id",
        "generated_at",
        "source",
        "cycle_id",
        "status",
        "proposed_action",
        "proposed_action_kind",
        "proposed_action_summary",
        "dry_run",
        "executed",
        "blocked",
        "block_reasons",
        "safety_checks",
        "execution_checks",
        "human_summary",
        "raw_trace",
        "raw_summary",
    }
)


def _sample_dry_run_result() -> Dict[str, Any]:
    from project_guardian.autonomy_dry_run_guard import (
        build_dry_run_decision_trace,
        summarize_dry_run_decision_trace,
    )

    trace = build_dry_run_decision_trace(
        cycle_id="cyc-report-1",
        source="run_autonomous_cycle",
        proposed_action="use_capability/test",
        guard_meta={"allowed": False, "reasons": ["live_execution_disabled"]},
        extra_block_reasons=["dry_run_only"],
    )
    summary = summarize_dry_run_decision_trace(trace)
    return {
        "executed": False,
        "action": "use_capability/test",
        "reason": "dry_run_only",
        "dry_run": True,
        "cycle_id": "cyc-report-1",
        "decision_trace": trace,
        "decision_trace_summary": summary,
    }


def test_build_dry_run_report_is_serializable_and_preserves_invariants() -> None:
    from project_guardian.autonomy_dry_run_guard import build_dry_run_decision_report

    result = _sample_dry_run_result()
    report = build_dry_run_decision_report(result=result)

    assert REPORT_REQUIRED_FIELDS <= set(report.keys())
    json.dumps(report)

    assert report["dry_run"] is True
    assert report["executed"] is False
    assert report["blocked"] is True
    assert report["status"] == "dry_run_blocked_not_executed"
    assert report["safety_checks"] == {
        "capability_called": False,
        "mutation_called": False,
        "proposal_implementation_called": False,
        "legacy_executor_reached": False,
    }
    assert report["execution_checks"]["executed"] is False
    assert report["execution_checks"]["dry_run"] is True
    assert "dry_run_only" in report["block_reasons"]
    assert report["proposed_action"] == "use_capability/test"
    assert report["proposed_action_kind"] == "use_capability"
    assert isinstance(report["raw_trace"], dict)
    assert isinstance(report["raw_summary"], dict)


def test_build_dry_run_report_does_not_mutate_input() -> None:
    from project_guardian.autonomy_dry_run_guard import build_dry_run_decision_report
    import copy

    result = _sample_dry_run_result()
    before = copy.deepcopy(result)
    build_dry_run_decision_report(result=result)
    assert result == before


def test_build_dry_run_report_tolerates_missing_fields() -> None:
    from project_guardian.autonomy_dry_run_guard import build_dry_run_decision_report

    report = build_dry_run_decision_report(result={})
    assert REPORT_REQUIRED_FIELDS <= set(report.keys())
    json.dumps(report)
    assert report["executed"] is False
    assert report["dry_run"] is True
    assert report["blocked"] is True


@pytest.mark.xfail(
    _phase1_autonomy_guard_wired() is False,
    reason=PHASE1_XFAIL_REASON,
    strict=False,
)
def test_run_autonomous_cycle_result_contains_dry_run_report() -> None:
    from project_guardian.core import GuardianCore

    calls: List[Any] = []

    def _track(*_a: Any, **_k: Any) -> Dict[str, Any]:
        calls.append(True)
        raise AssertionError("execute_capability_kind must not run in Phase 1 dry-run")

    stub = _dry_run_stub(dry_run_only=False)

    with patch(
        "project_guardian.capability_execution.execute_capability_kind",
        side_effect=_track,
    ):
        out = GuardianCore.run_autonomous_cycle(stub)

    assert calls == []
    assert out.get("executed") is False
    assert out.get("dry_run") is True

    report = out.get("dry_run_report")
    assert isinstance(report, dict)
    assert REPORT_REQUIRED_FIELDS <= set(report.keys())
    json.dumps(report)
    assert report["dry_run"] is True
    assert report["executed"] is False
    assert report["blocked"] is True
    assert report["safety_checks"]["capability_called"] is False
    assert report["safety_checks"]["mutation_called"] is False
    assert report["safety_checks"]["proposal_implementation_called"] is False
    assert report["safety_checks"]["legacy_executor_reached"] is False
