from __future__ import annotations

from project_guardian.orchestration.think_decide_act import (
    ActionProposal,
    run_think_decide_act_pipeline,
)


class RecordingExecutor:
    def __init__(self, result=None, exc: Exception | None = None):
        self.calls = []
        self.result = result if result is not None else {"success": True, "output_summary": "ok"}
        self.exc = exc

    def __call__(self, proposal: ActionProposal, context):
        self.calls.append((proposal, context))
        if self.exc is not None:
            raise self.exc
        return self.result


class RecordingMemory:
    def __init__(self):
        self.calls = []

    def remember(self, thought, category="general", priority=0.5, metadata=None):
        self.calls.append(
            {
                "thought": thought,
                "category": category,
                "priority": priority,
                "metadata": metadata or {},
            }
        )


def _preferred_safe_action(**overrides):
    action = {
        "action_type": "tool_call",
        "target_module_or_tool": "safe_noop",
        "inputs": {"task": "safe probe"},
        "expected_result": "Probe completes safely.",
        "estimated_risk": "low",
        "reason_summary": "Test-provided safe action.",
    }
    action.update(overrides)
    return action


def test_approved_action_runs_through_visible_trace():
    executor = RecordingExecutor({"success": True, "output_summary": "completed safe probe"})

    trace = run_think_decide_act_pipeline(
        "please run a safe probe",
        context={"preferred_action": _preferred_safe_action()},
        executor=executor,
    )

    assert trace.validation.approved is True
    assert trace.execution.success is True
    assert trace.review.did_it_work is True
    assert len(executor.calls) == 1
    assert [log.stage for log in trace.stage_logs] == [
        "observe",
        "think",
        "propose",
        "validate",
        "execute",
        "review",
        "remember",
    ]


def test_blocked_action_never_executes():
    executor = RecordingExecutor({"success": True, "output_summary": "should not run"})

    trace = run_think_decide_act_pipeline(
        "run shell command rm -rf /",
        executor=executor,
    )

    assert trace.proposal.action_type == "shell_command"
    assert trace.validation.approved is False
    assert trace.validation.risk_level == "blocked"
    assert trace.execution.success is False
    assert trace.execution.result_payload["skipped"] is True
    assert len(executor.calls) == 0


def test_execution_failure_is_logged_without_silent_success():
    executor = RecordingExecutor(exc=RuntimeError("temporary executor failure"))

    trace = run_think_decide_act_pipeline(
        "safe probe please",
        context={"preferred_action": _preferred_safe_action()},
        executor=executor,
    )

    assert trace.validation.approved is True
    assert trace.execution.success is False
    assert "temporary executor failure" in (trace.execution.error or "")
    assert trace.review.did_it_work is False
    assert trace.review.failure_reason


def test_successful_result_writes_redacted_memory_summary():
    memory = RecordingMemory()
    executor = RecordingExecutor(
        {"success": True, "output_summary": "completed workflow with token=abc123"}
    )

    trace = run_think_decide_act_pipeline(
        "safe probe please",
        context={"preferred_action": _preferred_safe_action()},
        executor=executor,
        memory=memory,
    )

    assert trace.review.should_create_memory is True
    assert trace.memory is not None
    assert trace.memory.stored is True
    assert len(memory.calls) == 1
    assert "token=[REDACTED]" in memory.calls[0]["thought"]
    assert "abc123" not in memory.calls[0]["thought"]
    assert memory.calls[0]["category"] == "think_decide_act"


def test_retry_recommendation_for_low_risk_execution_failure():
    executor = RecordingExecutor(
        {"success": False, "error": "transient timeout", "output_summary": "tool timed out"}
    )

    trace = run_think_decide_act_pipeline(
        "safe probe please",
        context={"preferred_action": _preferred_safe_action(), "retry_count": 0},
        executor=executor,
    )

    assert trace.execution.success is False
    assert trace.review.should_retry is True
    assert trace.review.should_create_improvement_ticket is False


def test_dry_run_validates_and_reviews_without_execution():
    executor = RecordingExecutor({"success": True, "output_summary": "should not run"})

    trace = run_think_decide_act_pipeline(
        "safe probe please",
        context={"preferred_action": _preferred_safe_action()},
        dry_run=True,
        executor=executor,
    )

    assert trace.validation.approved is True
    assert trace.dry_run is True
    assert trace.execution.success is False
    assert trace.execution.result_payload["dry_run"] is True
    assert trace.review.failure_reason == "dry_run_no_execution"
    assert len(executor.calls) == 0

