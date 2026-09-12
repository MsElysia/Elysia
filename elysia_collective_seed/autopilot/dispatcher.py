"""Provider-neutral deterministic dispatcher foundation.

Runtime-disabled: this module selects/validates work but does not invoke external
providers, execute project code, merge branches, or perform deployments.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

AUTO_RISKS = {"read_only", "sandbox_write", "repo_write"}
PROTECTED_RISKS = {"external_write", "deployment", "sensitive_data", "privileged"}
TERMINAL = {"completed", "rejected", "archived"}


@dataclass(frozen=True)
class Worker:
    worker_id: str
    provider: str
    capabilities: frozenset[str]
    risk_classes: frozenset[str]
    available: bool = True
    quality: float = 0.5
    cost: float = 0.5


@dataclass(frozen=True)
class DispatchDecision:
    task_id: str
    state: str
    worker_id: str | None
    reasons: tuple[str, ...]


def _deps_satisfied(task: Mapping, states: Mapping[str, str]) -> bool:
    return all(states.get(dep) == "completed" for dep in task.get("dependencies", []))


def _required_capabilities(task: Mapping) -> set[str]:
    caps = set(task.get("required_capabilities", []))
    task_class = task.get("task_class")
    if task_class:
        caps.add(str(task_class))
    return caps


def execution_policy_error(task: Mapping) -> str | None:
    """Validate admitted execution policy before using it as authority."""
    for field in ("dependencies", "allowed_workers", "required_capabilities"):
        values = task.get(field, [])
        if not isinstance(values, list) or any(not isinstance(value, str) or not value.strip() for value in values):
            return "invalid_execution_policy"
    if type(task.get("human_approval_required", False)) is not bool:
        return "invalid_execution_policy"
    if "task_class" in task and (not isinstance(task["task_class"], str) or not task["task_class"].strip()):
        return "invalid_execution_policy"
    risk = task.get("risk_class")
    if not isinstance(risk, str) or risk not in AUTO_RISKS | PROTECTED_RISKS:
        return "unknown_risk_class"
    if task.get("human_approval_required", False) or risk in PROTECTED_RISKS:
        return "authority_gate"
    return None


def eligible_workers(task: Mapping, workers: Iterable[Worker]) -> list[Worker]:
    required = _required_capabilities(task)
    risk = task["risk_class"]
    allowed = set(task.get("allowed_workers", []))
    result = []
    for worker in workers:
        if not worker.available or risk not in worker.risk_classes:
            continue
        if allowed and worker.worker_id not in allowed:
            continue
        if not required.issubset(worker.capabilities):
            continue
        result.append(worker)
    return result


def _score(worker: Worker, preferred: str | None) -> tuple[float, str]:
    # Deterministic: quality dominates, then lower cost; preferred worker gets a
    # small bounded bonus. worker_id is a stable final tie-breaker.
    score = worker.quality - (0.25 * worker.cost)
    if preferred and worker.worker_id == preferred:
        score += 0.10
    return score, worker.worker_id


def dispatch(task: Mapping, states: Mapping[str, str], workers: Sequence[Worker]) -> DispatchDecision:
    task_id = task["task_id"]
    status = task.get("status", "queued")
    if status in TERMINAL:
        return DispatchDecision(task_id, "not_dispatchable", None, ("terminal_task",))
    policy_error = execution_policy_error(task)
    if policy_error:
        return DispatchDecision(task_id, "human_gate" if policy_error == "authority_gate" else "blocked", None, (policy_error,))
    if not _deps_satisfied(task, states):
        return DispatchDecision(task_id, "blocked", None, ("dependencies_incomplete",))
    if int(task.get("attempt", 0)) >= int(task.get("max_attempts", 3)):
        return DispatchDecision(task_id, "blocked", None, ("attempt_limit_reached",))

    eligible = eligible_workers(task, workers)
    if not eligible:
        return DispatchDecision(task_id, "blocked", None, ("no_eligible_worker",))
    preferred = task.get("preferred_worker")
    chosen = max(eligible, key=lambda w: _score(w, preferred))
    return DispatchDecision(task_id, "dispatch", chosen.worker_id, ("eligible",))


def validate_followup(parent: Mapping, proposal: Mapping, open_tasks: Sequence[Mapping]) -> tuple[bool, tuple[str, ...]]:
    """Bound autonomous follow-up generation without granting new authority."""
    reasons: list[str] = []
    if proposal.get("risk_class") not in AUTO_RISKS:
        reasons.append("authority_expansion")
    if proposal.get("human_approval_required", False):
        reasons.append("human_gate")
    if not proposal.get("acceptance_criteria"):
        reasons.append("missing_acceptance_criteria")
    parent_sources = set(parent.get("source_refs", []))
    proposed_sources = set(proposal.get("source_refs", []))
    if not proposed_sources.issubset(parent_sources):
        reasons.append("source_scope_expansion")
    normalized = proposal.get("title", "").strip().casefold()
    if normalized and any(t.get("title", "").strip().casefold() == normalized for t in open_tasks):
        reasons.append("duplicate_open_task")
    return not reasons, tuple(reasons)
