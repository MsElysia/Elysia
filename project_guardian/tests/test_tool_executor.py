"""Focused tests for tool executor task delegation."""

from project_guardian.tool_executor import _execute_task


class _DirectGuardian:
    def __init__(self):
        self.calls = []

    def _execute_task(self, task_id, task_type, directives=None):
        self.calls.append(
            {
                "task_id": task_id,
                "task_type": task_type,
                "directives": directives,
            }
        )
        return {
            "status": "ok",
            "outcome": "executed",
            "task_id": task_id,
            "task_type": task_type,
        }


class _QueuedGuardian:
    def __init__(self):
        self.submissions = []

    def submit_task(
        self,
        task,
        task_data=None,
        *,
        priority=5,
        module="system",
        args=(),
        kwargs=None,
        timeout=None,
        dependencies=None,
        metadata=None,
    ):
        self.submissions.append(
            {
                "task": task,
                "task_data": task_data,
                "priority": priority,
                "module": module,
                "args": args,
                "kwargs": kwargs,
                "timeout": timeout,
                "dependencies": dependencies,
                "metadata": metadata,
            }
        )
        return "queued-task-1"


def test_execute_task_delegates_to_guardian_contract():
    guardian = _DirectGuardian()

    result = _execute_task(
        guardian,
        task_id="TASK-100",
        task_type="READ_ONLY_ANALYSIS",
        directives={"query": "inspect runtime health"},
    )

    assert result["status"] == "ok"
    assert result["executed"] is True
    assert result["task_id"] == "TASK-100"
    assert guardian.calls == [
        {
            "task_id": "TASK-100",
            "task_type": "READ_ONLY_ANALYSIS",
            "directives": {"query": "inspect runtime health"},
        }
    ]


def test_execute_task_queues_legacy_task_submission():
    guardian = _QueuedGuardian()

    result = _execute_task(
        guardian,
        task_id="TASK-200",
        task_type="APPLY_MUTATION",
        directives={"mutation_id": "mut-1"},
        priority=8,
        module="autonomy",
        kwargs={"dry_run": True},
    )

    assert result["status"] == "ok"
    assert result["queued"] is True
    assert result["task_id"] == "queued-task-1"

    submission = guardian.submissions[0]
    assert submission["task"] == "APPLY_MUTATION"
    assert submission["task_data"] == {
        "directives": {"mutation_id": "mut-1"},
        "task_id": "TASK-200",
    }
    assert submission["priority"] == 8
    assert submission["module"] == "autonomy"
    assert submission["kwargs"] == {"dry_run": True}
    assert submission["metadata"]["requested_task_id"] == "TASK-200"


def test_execute_task_returns_clear_error_without_real_execution_surface():
    result = _execute_task(
        object(),
        task_type="RUN_ACCEPTANCE",
        directives={"task_id": "TASK-300"},
    )

    assert result["status"] == "error"
    assert "No executable task contract available" in result["error"]
