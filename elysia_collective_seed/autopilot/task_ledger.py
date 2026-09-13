"""Provider-neutral Elysia autopilot task ledger core.

This module is intentionally local-only and runtime-disabled. It performs no network,
model, GitHub, Cursor, Codex, deployment, or external-write operations. It provides
deterministic state transitions that future worker adapters can call after the
canonical Guardian runtime has been reconciled.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional
import uuid


class TaskState(str, Enum):
    QUEUED = "queued"
    CLAIMED = "claimed"
    RUNNING = "running"
    VERIFYING = "verifying"
    ACCEPTED = "accepted"
    BLOCKED = "blocked"
    FAILED = "failed"
    HUMAN_REVIEW = "human_review"


TERMINAL = {TaskState.ACCEPTED, TaskState.FAILED}


@dataclass
class Lease:
    worker_id: str
    lease_id: str
    expires_at: str

    def expired(self, now: datetime) -> bool:
        return datetime.fromisoformat(self.expires_at) <= now


@dataclass
class Task:
    task_id: str
    objective: str
    acceptance_criteria: List[str]
    dependencies: List[str] = field(default_factory=list)
    risk_class: str = "automatic"
    requires_write: bool = False
    state: TaskState = TaskState.QUEUED
    lease: Optional[Lease] = None
    producer_worker_id: Optional[str] = None
    verifier_worker_id: Optional[str] = None
    evidence: List[str] = field(default_factory=list)
    blocked_reason: Optional[str] = None
    attempts: int = 0


class LedgerError(ValueError):
    pass


class TaskLedger:
    def __init__(self) -> None:
        self.tasks: Dict[str, Task] = {}
        self.audit: List[dict] = []

    def add(self, task: Task) -> None:
        if task.task_id in self.tasks:
            raise LedgerError(f"duplicate task_id: {task.task_id}")
        if task.task_id in task.dependencies:
            raise LedgerError("task cannot depend on itself")
        self.tasks[task.task_id] = task
        self._record(task.task_id, "added")

    def ready(self) -> List[Task]:
        ready: List[Task] = []
        for task in self.tasks.values():
            if task.state != TaskState.QUEUED:
                continue
            if all(self.tasks.get(dep) and self.tasks[dep].state == TaskState.ACCEPTED for dep in task.dependencies):
                ready.append(task)
        return sorted(ready, key=lambda t: t.task_id)

    def claim(self, task_id: str, worker_id: str, lease_minutes: int = 30, now: Optional[datetime] = None) -> Lease:
        now = now or datetime.now(timezone.utc)
        task = self._task(task_id)
        if task.state != TaskState.QUEUED:
            raise LedgerError(f"task not claimable from state {task.state}")
        if task not in self.ready():
            raise LedgerError("dependencies are not satisfied")
        lease = Lease(worker_id, str(uuid.uuid4()), (now + timedelta(minutes=lease_minutes)).isoformat())
        task.lease = lease
        task.state = TaskState.CLAIMED
        task.attempts += 1
        self._record(task_id, "claimed", worker_id=worker_id, lease_id=lease.lease_id)
        return lease

    def start(self, task_id: str, lease_id: str) -> None:
        task = self._leased(task_id, lease_id)
        if task.state != TaskState.CLAIMED:
            raise LedgerError("task must be claimed before start")
        task.state = TaskState.RUNNING
        self._record(task_id, "started", worker_id=task.lease.worker_id)

    def submit(self, task_id: str, lease_id: str, evidence: List[str]) -> None:
        task = self._leased(task_id, lease_id)
        if task.state != TaskState.RUNNING:
            raise LedgerError("task must be running before submit")
        if not evidence:
            raise LedgerError("completion evidence is required")
        task.evidence.extend(evidence)
        task.producer_worker_id = task.lease.worker_id
        task.lease = None
        task.state = TaskState.VERIFYING if task.requires_write else TaskState.ACCEPTED
        self._record(task_id, "submitted", next_state=task.state.value)

    def verify(self, task_id: str, verifier_worker_id: str, passed: bool, evidence: List[str]) -> None:
        task = self._task(task_id)
        if task.state != TaskState.VERIFYING:
            raise LedgerError("task is not awaiting verification")
        if verifier_worker_id == task.producer_worker_id:
            raise LedgerError("write task requires an independent verifier")
        if not evidence:
            raise LedgerError("verification evidence is required")
        task.verifier_worker_id = verifier_worker_id
        task.evidence.extend(evidence)
        task.state = TaskState.ACCEPTED if passed else TaskState.QUEUED
        self._record(task_id, "verified", verifier=verifier_worker_id, passed=passed, next_state=task.state.value)

    def block(self, task_id: str, reason: str) -> None:
        task = self._task(task_id)
        if task.state in TERMINAL:
            raise LedgerError("terminal task cannot be blocked")
        task.state = TaskState.BLOCKED
        task.blocked_reason = reason
        task.lease = None
        self._record(task_id, "blocked", reason=reason)

    def unblock(self, task_id: str) -> None:
        task = self._task(task_id)
        if task.state != TaskState.BLOCKED:
            raise LedgerError("only blocked tasks can be unblocked")
        task.state = TaskState.QUEUED
        task.blocked_reason = None
        self._record(task_id, "unblocked")

    def reap_expired_leases(self, now: Optional[datetime] = None) -> List[str]:
        now = now or datetime.now(timezone.utc)
        requeued: List[str] = []
        for task in self.tasks.values():
            if task.lease and task.lease.expired(now) and task.state in {TaskState.CLAIMED, TaskState.RUNNING}:
                task.lease = None
                task.state = TaskState.QUEUED
                requeued.append(task.task_id)
                self._record(task.task_id, "lease_expired_requeued")
        return sorted(requeued)

    def snapshot(self) -> dict:
        return {"tasks": {k: asdict(v) for k, v in self.tasks.items()}, "audit": list(self.audit)}

    def _task(self, task_id: str) -> Task:
        try:
            return self.tasks[task_id]
        except KeyError as exc:
            raise LedgerError(f"unknown task_id: {task_id}") from exc

    def _leased(self, task_id: str, lease_id: str) -> Task:
        task = self._task(task_id)
        if not task.lease or task.lease.lease_id != lease_id:
            raise LedgerError("invalid lease")
        return task

    def _record(self, task_id: str, event: str, **details: object) -> None:
        self.audit.append({"task_id": task_id, "event": event, **details})
