"""Dry-run orchestration bridge between dispatcher and persistent task ledger.

This module is deliberately provider-free and runtime-disabled. It does not invoke
models, subprocesses, Guardian runtime code, network services, GitHub writes,
merges, or deployments. It only makes deterministic dispatch/completion decisions
and persists bounded local SQLite state transitions.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Mapping, Sequence

from .completion_validator import CompletionValidation, validate_completion
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


@dataclass(frozen=True)
class CompletionResult:
    task_id: str
    state: str
    worker_id: str
    validation: CompletionValidation
    applied: bool
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


def validate_and_apply_completion(
    ledger: TaskLedger,
    packet: Mapping,
    *,
    worker_id: str,
    required_checks: Sequence[str] = (),
) -> CompletionResult:
    """Validate a worker completion and apply only a bounded ledger transition.

    A worker's `completed` report does not make a task completed. It moves the
    task to `verifying`, preserving the independent-verifier gate. Partial/failed
    work returns to `queued`; blocked work becomes `blocked`; rejected work becomes
    terminal `rejected`. The ledger lease owner must match `worker_id`, so a stale
    or unrelated completion cannot mutate another worker's task.
    """
    task_id = str(packet.get("task_id", ""))
    persisted = ledger.get(task_id)
    required_checks = tuple(dict.fromkeys((*required_checks, *(persisted or {}).get("required_checks", []))))
    validation = validate_completion(
        packet,
        expected_task_id=task_id or None,
        required_checks=required_checks,
    )
    if not validation.valid or validation.task_id is None or validation.outcome is None:
        return CompletionResult(
            task_id=task_id,
            state="validation_rejected",
            worker_id=worker_id,
            validation=validation,
            applied=False,
            reasons=validation.reasons,
        )

    persisted = ledger.get(validation.task_id)
    if persisted is None:
        return CompletionResult(
            task_id=validation.task_id,
            state="completion_rejected",
            worker_id=worker_id,
            validation=validation,
            applied=False,
            reasons=("task_not_found",),
        )
    if persisted.get("claimed_by") != worker_id:
        return CompletionResult(
            task_id=validation.task_id,
            state="completion_rejected",
            worker_id=worker_id,
            validation=validation,
            applied=False,
            reasons=("lease_owner_mismatch",),
        )

    next_state = {
        "completed": "verifying",
        "partial": "queued",
        "blocked": "blocked",
        "failed": "queued",
        "rejected": "rejected",
    }[validation.outcome]
    if validation.outcome == "completed":
        # Schema-compatible older packets have no ID: bind them to a canonical
        # digest for identity. The digest identifies the packet; it is not write proof.
        canonical = json.dumps(dict(packet), sort_keys=True, separators=(",", ":"), allow_nan=False)
        digest = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        packet_id = packet.get("packet_id", digest)
        evidence = list(packet.get("evidence_refs", []))
        evidence.extend(ref for claim in packet.get("claims", []) for ref in claim.get("evidence", []))
        evidence.extend(packet.get("commits", []))
        evidence.extend(packet.get("pull_requests", []))
        evidence.append(digest)
        applied = ledger.submit_for_verification(
            validation.task_id,
            worker_id,
            packet_id,
            list(dict.fromkeys(evidence)),
            completion_checks=[{"name": check["name"], "result": check["result"]} for check in packet["checks"]],
            commits=list(packet.get("commits", [])),
            pull_requests=list(packet.get("pull_requests", [])),
            claims=[dict(claim) for claim in packet.get("claims", [])],
            packet_digest=digest,
        )
    else:
        applied = ledger.release(validation.task_id, worker_id, next_status=next_state)
    if not applied:
        return CompletionResult(
            task_id=validation.task_id,
            state="completion_rejected",
            worker_id=worker_id,
            validation=validation,
            applied=False,
            reasons=("lease_release_failed",),
        )
    return CompletionResult(
        task_id=validation.task_id,
        state=ledger.get(validation.task_id)["status"],
        worker_id=worker_id,
        validation=validation,
        applied=True,
        reasons=("completion_applied",),
    )
