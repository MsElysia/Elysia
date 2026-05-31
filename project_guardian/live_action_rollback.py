"""Phase 2 passive live-action rollback plan schema and validation.

Defines rollback metadata types and completeness validation only.
Does not execute rollback, touch files, or wire into runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple


class RollbackStrategy(str, Enum):
    """Passive rollback strategy label (no execution implied)."""

    NONE = "NONE"
    NOT_REQUIRED = "NOT_REQUIRED"
    MANUAL_ONLY = "MANUAL_ONLY"
    FILE_BACKUP = "FILE_BACKUP"
    FILE_RESTORE = "FILE_RESTORE"
    DELETE_CREATED_FILE = "DELETE_CREATED_FILE"
    REVERT_PATCH = "REVERT_PATCH"
    CONFIG_RESTORE = "CONFIG_RESTORE"
    STATE_SNAPSHOT = "STATE_SNAPSHOT"
    EXTERNAL_REVERSAL = "EXTERNAL_REVERSAL"


class RollbackAvailability(str, Enum):
    """Whether rollback can be performed for a proposed action."""

    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class LiveActionRollbackPlan:
    """Passive rollback plan metadata for a proposed live action."""

    action_id: str
    strategy: RollbackStrategy
    availability: RollbackAvailability
    target: str = ""
    backup_path: str = ""
    snapshot_id: str = ""
    manual_steps: Tuple[str, ...] = ()
    irreversible_risks: Tuple[str, ...] = ()
    estimated_complexity: str = ""
    notes: str = ""


@dataclass(frozen=True)
class LiveActionRollbackValidationResult:
    """Schema/completeness validation outcome for a rollback plan."""

    valid: bool
    availability: RollbackAvailability
    reasons: Tuple[str, ...]
    safety_verdict: str


def _nonempty(value: Optional[str]) -> bool:
    return bool(value and str(value).strip())


def _has_manual_steps(plan: LiveActionRollbackPlan) -> bool:
    return bool(plan.manual_steps and any(str(step).strip() for step in plan.manual_steps))


def validate_live_action_rollback_plan(
    plan: LiveActionRollbackPlan,
) -> LiveActionRollbackValidationResult:
    """Validate rollback plan schema/completeness only. Does not touch files or run commands."""
    reasons: list[str] = []

    def _missing(field: str) -> None:
        reasons.append(f"missing required field: {field}")

    strategy = plan.strategy

    if strategy is RollbackStrategy.NONE:
        if plan.availability is not RollbackAvailability.UNAVAILABLE:
            reasons.append("NONE strategy requires availability=UNAVAILABLE")
    elif strategy is RollbackStrategy.NOT_REQUIRED:
        if plan.availability is not RollbackAvailability.NOT_APPLICABLE:
            reasons.append("NOT_REQUIRED strategy requires availability=NOT_APPLICABLE")
    elif strategy is RollbackStrategy.FILE_BACKUP:
        if not _nonempty(plan.target):
            _missing("target")
        if not _nonempty(plan.backup_path):
            _missing("backup_path")
    elif strategy is RollbackStrategy.FILE_RESTORE:
        if not _nonempty(plan.target):
            _missing("target")
        if not _nonempty(plan.backup_path):
            _missing("backup_path")
    elif strategy is RollbackStrategy.DELETE_CREATED_FILE:
        if not _nonempty(plan.target):
            _missing("target")
    elif strategy is RollbackStrategy.REVERT_PATCH:
        if not _nonempty(plan.target):
            _missing("target")
    elif strategy is RollbackStrategy.CONFIG_RESTORE:
        if not _nonempty(plan.target):
            _missing("target")
        if not _nonempty(plan.backup_path):
            _missing("backup_path")
    elif strategy is RollbackStrategy.STATE_SNAPSHOT:
        if not _nonempty(plan.snapshot_id):
            _missing("snapshot_id")
    elif strategy is RollbackStrategy.EXTERNAL_REVERSAL:
        if not _has_manual_steps(plan):
            _missing("manual_steps")
    elif strategy is RollbackStrategy.MANUAL_ONLY:
        if not _has_manual_steps(plan):
            _missing("manual_steps")

    valid = not reasons
    safety_verdict = "SAFE" if valid else "UNSAFE"

    return LiveActionRollbackValidationResult(
        valid=valid,
        availability=plan.availability,
        reasons=tuple(reasons),
        safety_verdict=safety_verdict,
    )


def summarize_live_action_rollback_plan(plan: LiveActionRollbackPlan) -> Dict[str, Any]:
    """Return a JSON-safe plain dict summary of a rollback plan."""
    return {
        "action_id": plan.action_id,
        "strategy": plan.strategy.value,
        "availability": plan.availability.value,
        "target": plan.target,
        "backup_path": plan.backup_path,
        "snapshot_id": plan.snapshot_id,
        "manual_steps": list(plan.manual_steps),
        "irreversible_risks": list(plan.irreversible_risks),
        "estimated_complexity": plan.estimated_complexity,
        "notes": plan.notes,
    }
