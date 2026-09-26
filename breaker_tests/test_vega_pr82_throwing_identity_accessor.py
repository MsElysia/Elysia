from datetime import datetime, timezone

from elysia_collective_seed.autopilot.orchestration_bridge import run_via_broker
from elysia_collective_seed.autopilot.task_ledger import TaskLedger


NOW = datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc)


def _task():
    return {
        "task_id": "ELY-TASK-VEGA-82-ACCESSOR",
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


class ThrowingIdentityResult:
    @property
    def task_id(self):
        raise RuntimeError("hostile task identity accessor executed")


class Broker:
    def run_task_sync(self, request):
        return ThrowingIdentityResult()


def test_throwing_result_identity_accessor_rejects_without_escaping(tmp_path):
    ledger = TaskLedger(tmp_path / "ledger.db")
    try:
        ledger.put_task(_task())
        assert ledger.claim("ELY-TASK-VEGA-82-ACCESSOR", "producer", now=NOW).claimed

        result = run_via_broker(
            ledger,
            "ELY-TASK-VEGA-82-ACCESSOR",
            "producer",
            broker=Broker(),
            now=NOW,
        )

        assert result.submitted is False
        assert result.error == "broker_task_identity_mismatch"
        assert ledger.get_bridge_receipt("ELY-TASK-VEGA-82-ACCESSOR") is None
        assert ledger.get("ELY-TASK-VEGA-82-ACCESSOR")["completion_submission"] is None
    finally:
        ledger.close()
