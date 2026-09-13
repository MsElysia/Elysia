"""Pure task-state validation for the Elysia Autopilot.

This module performs no network, model, filesystem, GitHub, deployment, or
runtime actions. It is a provider-neutral policy primitive for AUTOPILOT-004.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Mapping


TERMINAL = frozenset({"completed", "rejected", "archived"})

ALLOWED_TRANSITIONS: Mapping[str, FrozenSet[str]] = {
    "queued": frozenset({"claimed", "blocked", "rejected", "archived"}),
    "claimed": frozenset({"running", "queued", "blocked", "rejected"}),
    "running": frozenset({"review", "blocked", "queued", "rejected"}),
    "review": frozenset({"completed", "running", "blocked", "rejected"}),
    "blocked": frozenset({"queued", "rejected", "archived"}),
    "completed": frozenset({"archived"}),
    "rejected": frozenset({"archived"}),
    "archived": frozenset(),
}

RISK_REQUIRES_HUMAN = frozenset({
    "external_write", "deployment", "sensitive_data", "privileged"
})


@dataclass(frozen=True)
class TransitionDecision:
    allowed: bool
    reason: str


def validate_transition(
    current: str,
    target: str,
    *,
    risk_class: str,
    human_approval_required: bool = False,
    human_approval_present: bool = False,
    independent_verification_passed: bool = False,
    runtime_behavior_changed: bool = False,
) -> TransitionDecision:
    """Validate one state transition without performing it."""
    if current not in ALLOWED_TRANSITIONS:
        return TransitionDecision(False, "unknown_current_state")
    if target not in ALLOWED_TRANSITIONS[current]:
        return TransitionDecision(False, "transition_not_allowed")

    needs_human = human_approval_required or risk_class in RISK_REQUIRES_HUMAN
    if needs_human and target in {"completed", "archived"} and not human_approval_present:
        return TransitionDecision(False, "human_approval_missing")

    if target == "completed" and runtime_behavior_changed and not independent_verification_passed:
        return TransitionDecision(False, "independent_verification_missing")

    return TransitionDecision(True, "allowed")


def can_claim(*, status: str, dependencies_satisfied: bool, attempts: int, max_attempts: int) -> TransitionDecision:
    """Validate whether a queued task may be leased to a worker."""
    if status != "queued":
        return TransitionDecision(False, "task_not_queued")
    if not dependencies_satisfied:
        return TransitionDecision(False, "dependencies_unsatisfied")
    if attempts >= max_attempts:
        return TransitionDecision(False, "attempt_budget_exhausted")
    return TransitionDecision(True, "claimable")
