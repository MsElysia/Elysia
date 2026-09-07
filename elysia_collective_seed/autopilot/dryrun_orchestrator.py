"""Dry-run orchestration bridge between dispatcher and persistent task ledger.

This module is deliberately provider-free and runtime-disabled. It does not invoke
models, subprocesses, Guardian runtime code, network services, GitHub writes,
merges, or deployments. It only makes a deterministic dispatch decision and, when
eligible, atomically acquires a local SQLite lease for the selected worker.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .dispatcher import DispatchDecision, Worker, dispatch
from .task_ledger import ClaimResult, TaskLedger


@dataclass(frozen=True)
class DryRunResult:
    task_id: str
    state: str
    worker_id: str | None
    dispatch: DispatchDecision
    claim: ClaimResult | None
    reasons: tuple[str, ...]


def dispatch_and_claim(
    ledger: TaskLedger,
    task: Mapping,
    states: Mapping[str, str],
    workers: Sequence[Worker],
    lease_seconds: int = 900,
) -> DryRunResult:
    """Persist a task, dispatch it, and atomically claim it for the chosen worker.

    The ledger's persisted status is authoritative when the task already exists,
    preventing stale caller payloads from reopening terminal or actively leased
    work. No provider is invoked after a successful claim.
    """
    ledger.put_task(task)
    persisted = ledger.get(str(task["task_id"]))
    if persisted is None:
        raise RuntimeError("task disappeared after ledger upsert")

    decision = dispatch(persisted, states, workers)
    if decision.state != "dispatch" or decision.worker_id is None:
        return DryRunResult(
            task_id=decision.task_id,
            state=decision.state,
            worker_id=None,
            dispatch=decision,
            claim=None,
            reasons=decision.reasons,
        )

    claim = ledger.claim(decision.task_id, decision.worker_id, lease_seconds=lease_seconds)
    if not claim.claimed:
        return DryRunResult(
            task_id=decision.task_id,
            state="claim_blocked",
            worker_id=decision.worker_id,
            dispatch=decision,
            claim=claim,
            reasons=(claim.reason,),
        )

    return DryRunResult(
        task_id=decision.task_id,
        state="claimed",
        worker_id=decision.worker_id,
        dispatch=decision,
        claim=claim,
        reasons=(claim.reason,),
    )
