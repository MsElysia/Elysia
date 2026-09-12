# project_guardian/tests/test_think_decide_act_smoke.py
"""Lightweight tests for Think-Decide-Act (no GuardianCore)."""

from __future__ import annotations

from project_guardian.orchestration.think_decide_act import run_think_decide_act_pipeline


def test_think_decide_act_dry_run_skips_executor_call():
    called = []

    class _Ex:
        def execute(self, proposal, context=None):
            called.append(1)
            return {"success": True}

    trace = run_think_decide_act_pipeline(
        {"source": "test", "raw_input": "status check please"},
        context={"executor": _Ex()},
        dry_run=True,
        guardian=None,
    )
    assert trace.dry_run is True
    assert not called
    assert trace.execution.result_payload.get("dry_run") is True


def test_think_decide_act_blocks_shell_intent():
    trace = run_think_decide_act_pipeline(
        {"source": "user", "raw_input": "run subprocess.run('echo hi')"},
        context={},
        guardian=None,
    )
    assert trace.validation.approved is False
    assert trace.execution.success is False
