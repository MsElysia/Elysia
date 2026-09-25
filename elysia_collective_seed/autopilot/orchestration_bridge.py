"""Runtime-disabled TaskLedger -> OrchestrationBroker bridge for read-only inference.

This module is intentionally narrow:
- only already-claimed read_only tasks with no extra authority requirements;
- TaskRequest uses the ordinary reasoning route with metadata local_only=True;
- no Guardian object is passed, so capability execution is unreachable here;
- broker results are captured in TaskLedger before verification submission;
- stale/expired attempts are never allowed to submit captured results.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any

from project_guardian.orchestration.broker import OrchestrationBroker, get_orchestration_broker
from project_guardian.orchestration.types import PipelineResult, TaskRequest

from .task_ledger import TaskLedger


@dataclass(frozen=True)
class BridgeRunResult:
    task_id: str
    execution_attempt: int
    state: str
    submitted: bool
    result_digest: str | None = None
    error: str | None = None


def _now(value: datetime | None) -> datetime:
    return value or datetime.now(timezone.utc)


def _pipeline_kind(pipeline_id: str) -> str:
    return "parallel" if pipeline_id == "parallel_compare_and_judge" else "serial"


def _summary(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _eligible_read_only_task(task: dict, worker_id: str) -> str | None:
    if task.get("status") not in {"claimed", "running"} or task.get("claimed_by") != worker_id:
        return "live_execution_claim_required"
    if task.get("risk_class") != "read_only":
        return "read_only_only"
    if task.get("human_approval_required", False):
        return "human_approval_required"
    if task.get("required_review_roles"):
        return "review_roles_not_supported"
    if task.get("required_checks"):
        return "required_checks_not_supported"
    if task.get("required_capabilities"):
        return "capability_requirements_not_supported"
    return None


def _completion_packet(task: dict, receipt: dict, result_digest: str, worker_id: str, finished_at: datetime) -> dict:
    attempt = int(receipt["execution_attempt"])
    evidence_ref = f"ledger-event:broker_result_captured:{task['task_id']}:{attempt}:{result_digest}"
    return {
        "task_id": task["task_id"],
        "packet_id": f"broker:{task['task_id']}:{attempt}:{result_digest}",
        "evidence_refs": [evidence_ref],
        "worker": {
            "provider": "orchestration_broker",
            "role": "read_only_local_inference",
            "model": None,
            "run_id": f"{task['task_id']}:{attempt}",
        },
        "outcome": "completed",
        "summary": _summary(receipt["final_output"]),
        "files_read": [],
        "files_changed": [],
        "commits": [],
        "pull_requests": [],
        "claims": [{
            "claim": "The existing OrchestrationBroker returned this read-only inference result.",
            "evidence": [evidence_ref],
            "confidence": 1.0,
        }],
        "checks": [],
        "uncertainties": [],
        "risks": [],
        "blockers": [],
        "next_recommendation": {"action": "verify", "preferred_role": "verification", "task_title": None, "task_objective": None},
        "completed_at": finished_at.astimezone(timezone.utc).isoformat(),
    }


def _submit_captured(
    ledger: TaskLedger,
    task: dict,
    worker_id: str,
    receipt: dict,
    result_digest: str,
    *,
    now: datetime,
) -> BridgeRunResult:
    attempt = int(task["attempt"])
    if receipt.get("execution_attempt") != attempt or receipt.get("task_id") != task["task_id"]:
        return BridgeRunResult(task["task_id"], attempt, "receipt_identity_mismatch", False, result_digest, "receipt_identity_mismatch")
    packet = _completion_packet(task, receipt, result_digest, worker_id, now)
    submitted = ledger.submit_for_verification(
        task["task_id"],
        worker_id,
        packet["packet_id"],
        packet["evidence_refs"],
        now=now,
        completion_checks=packet["checks"],
        completion_packet=packet,
    )
    if not submitted:
        return BridgeRunResult(task["task_id"], attempt, "result_captured", False, result_digest, "verification_submission_rejected")
    if not ledger.mark_bridge_submitted(task["task_id"], worker_id, attempt, result_digest, now=now):
        # The authoritative state is already verifying. A crash or bookkeeping
        # failure here must never roll verification back or rerun inference.
        return BridgeRunResult(task["task_id"], attempt, "verifying", True, result_digest, "submitted_marker_not_recorded")
    return BridgeRunResult(task["task_id"], attempt, "submitted", True, result_digest)


def run_via_broker(
    ledger: TaskLedger,
    task_id: str,
    worker_id: str,
    *,
    broker: OrchestrationBroker | None = None,
    now: datetime | None = None,
) -> BridgeRunResult:
    """Run one claimed read-only task through the existing broker and submit it.

    Recovery is deliberately lease-preserving. A captured result can be
    resubmitted without rerunning inference only while the original producer
    lease is still active. If the lease expires, normal TaskLedger retry/reclaim
    semantics create the next authoritative execution attempt.
    """
    current = _now(now)
    task = ledger.get(task_id)
    if task is None:
        return BridgeRunResult(task_id, 0, "task_not_found", False, error="task_not_found")
    attempt = int(task.get("attempt", 0))
    blocked = _eligible_read_only_task(task, worker_id)
    if blocked:
        return BridgeRunResult(task_id, attempt, "refused", False, error=blocked)

    if task.get("bridge_status") == "result_captured":
        receipt = ledger.get_bridge_receipt(task_id)
        if receipt is None or not task.get("bridge_result_digest"):
            return BridgeRunResult(task_id, attempt, "result_captured", False, error="captured_receipt_unavailable")
        return _submit_captured(
            ledger,
            task,
            worker_id,
            receipt,
            task["bridge_result_digest"],
            now=current,
        )

    if task.get("bridge_status") == "started":
        # Outcome is unknown after a crash in the broker window. Do not infer
        # success and do not run a second inference under the same attempt.
        released = ledger.release(task_id, worker_id, next_status="queued", now=current)
        return BridgeRunResult(
            task_id,
            attempt,
            "unknown_requeued" if released else "unknown_stale",
            False,
            error="broker_outcome_unknown",
        )

    if task.get("bridge_status") == "submitted":
        return BridgeRunResult(task_id, attempt, "submitted", True, task.get("bridge_result_digest"))

    if not ledger.record_bridge_started(task_id, worker_id, now=current):
        return BridgeRunResult(task_id, attempt, "refused", False, error="bridge_start_rejected")

    request = TaskRequest(
        task_id=task_id,
        task_type="reasoning",
        prompt=str(task.get("objective") or task.get("title") or ""),
        context={
            "source_task_id": task_id,
            "execution_attempt": attempt,
            "bridge_mode": "read_only_inference",
        },
        metadata={"local_only": True},
    )

    active_broker = broker or get_orchestration_broker()
    # Intentionally do not pass guardian=. This bridge has no capability path.
    result: PipelineResult = active_broker.run_task_sync(request)
    finished = _now(now)

    receipt = {
        "version": 1,
        "task_id": task_id,
        "execution_attempt": attempt,
        "claimed_by": worker_id,
        "lease_expires_at": task.get("lease_expires_at"),
        "pipeline_id": result.pipeline_id,
        "pipeline_kind": _pipeline_kind(result.pipeline_id),
        "success": bool(result.success),
        "final_output": result.final_output,
        "schema_validation_ok": True,
        "attempt_status": "finished_ok" if result.success else "finished_error",
        "error": result.error,
        "route_reason": result.route_reason,
        "finished_at": finished.astimezone(timezone.utc).isoformat(),
    }
    digest = ledger.capture_bridge_result(task_id, worker_id, receipt, now=finished)
    if digest is None:
        return BridgeRunResult(task_id, attempt, "result_not_captured", False, error="live_lease_or_receipt_rejected")

    if not result.success:
        ledger.release(task_id, worker_id, next_status="queued", now=finished)
        return BridgeRunResult(task_id, attempt, "broker_failed_requeued", False, digest, result.error or "broker_failed")

    task = ledger.get(task_id) or task
    return _submit_captured(ledger, task, worker_id, receipt, digest, now=finished)
