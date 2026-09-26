from dataclasses import dataclass
from datetime import datetime, timezone

from elysia_collective_seed.autopilot.orchestration_bridge import run_via_broker
from elysia_collective_seed.autopilot.task_ledger import TaskLedger


NOW = datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc)


def _task():
    return {
        "task_id": "ELY-TASK-VEGA-82",
        "title": "Read-only diagnosis",
        "objective": "Diagnose a synthetic failure.",
        "status": "queued",
        "task_class": "analysis",
        "risk_class": "read_only",
        "acceptance_criteria": ["Return a diagnosis."],
        "required_capabilities": [],
        "required_checks": [],
        "required_review_roles": [],
        "human_approval_required": False,
        "max_attempts": 3,
    }


@dataclass
class ResultForAnotherTask:
    task_id: str = "ELY-TASK-UNRELATED"
    pipeline_id: str = "serial_plan_execute_review"
    success: bool = True
    final_output: str = "output from an unrelated task"
    route_reason: str = "synthetic"
    error: str | None = None


class MismatchedBroker:
    def run_task_sync(self, request):
        return ResultForAnotherTask()


def test_bridge_rejects_successful_result_bound_to_a_different_task(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    try:
        ledger.put_task(_task())
        assert ledger.claim("ELY-TASK-VEGA-82", "producer", now=NOW).claimed

        result = run_via_broker(
            ledger,
            "ELY-TASK-VEGA-82",
            "producer",
            broker=MismatchedBroker(),
            now=NOW,
        )

        assert result.submitted is False
        assert ledger.get("ELY-TASK-VEGA-82")["status"] != "verifying"
    finally:
        ledger.close()
