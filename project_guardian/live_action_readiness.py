"""Phase 2 passive live-mode readiness evaluation.

Checks whether prerequisites for limited live mode are satisfied.
Does not enable live mode, execute actions, or wire into runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple


class ReadinessStatus(str, Enum):
    """Overall or per-check readiness status."""

    READY = "READY"
    NOT_READY = "NOT_READY"
    BLOCKED = "BLOCKED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ReadinessCheck(str, Enum):
    """Individual readiness gate checks for limited live mode."""

    SAFE_OBSERVER_VERIFIED = "SAFE_OBSERVER_VERIFIED"
    STARTUP_STABLE = "STARTUP_STABLE"
    DIRTY_CORE_CLEANED = "DIRTY_CORE_CLEANED"
    DIRTY_SERVER_CLEANED = "DIRTY_SERVER_CLEANED"
    ALLOWLIST_IMPLEMENTED = "ALLOWLIST_IMPLEMENTED"
    APPROVAL_PACKET_IMPLEMENTED = "APPROVAL_PACKET_IMPLEMENTED"
    OPERATOR_DECISION_IMPLEMENTED = "OPERATOR_DECISION_IMPLEMENTED"
    AUDIT_IMPLEMENTED = "AUDIT_IMPLEMENTED"
    ROLLBACK_METADATA_IMPLEMENTED = "ROLLBACK_METADATA_IMPLEMENTED"
    LIVE_EXECUTOR_IMPLEMENTED = "LIVE_EXECUTOR_IMPLEMENTED"
    UI_OR_API_APPROVAL_ROUTE_IMPLEMENTED = "UI_OR_API_APPROVAL_ROUTE_IMPLEMENTED"
    HARMLESS_LIVE_ACTION_SMOKE_VERIFIED = "HARMLESS_LIVE_ACTION_SMOKE_VERIFIED"
    AUTONOMY_CONFIG_DEFAULT_DISABLED = "AUTONOMY_CONFIG_DEFAULT_DISABLED"
    FULL_RUNTIME_TESTS_CLASSIFIED = "FULL_RUNTIME_TESTS_CLASSIFIED"


DEFAULT_EVIDENCE: Dict[str, bool] = {
    ReadinessCheck.SAFE_OBSERVER_VERIFIED.value: True,
    ReadinessCheck.STARTUP_STABLE.value: True,
    ReadinessCheck.ALLOWLIST_IMPLEMENTED.value: True,
    ReadinessCheck.APPROVAL_PACKET_IMPLEMENTED.value: True,
    ReadinessCheck.OPERATOR_DECISION_IMPLEMENTED.value: True,
    ReadinessCheck.AUDIT_IMPLEMENTED.value: True,
    ReadinessCheck.ROLLBACK_METADATA_IMPLEMENTED.value: True,
    ReadinessCheck.AUTONOMY_CONFIG_DEFAULT_DISABLED.value: True,
    ReadinessCheck.DIRTY_CORE_CLEANED.value: True,
    ReadinessCheck.DIRTY_SERVER_CLEANED.value: True,
    ReadinessCheck.LIVE_EXECUTOR_IMPLEMENTED.value: False,
    ReadinessCheck.UI_OR_API_APPROVAL_ROUTE_IMPLEMENTED.value: False,
    ReadinessCheck.HARMLESS_LIVE_ACTION_SMOKE_VERIFIED.value: False,
    ReadinessCheck.FULL_RUNTIME_TESTS_CLASSIFIED.value: False,
}


@dataclass(frozen=True)
class ReadinessItem:
    """Result for a single readiness check."""

    check: ReadinessCheck
    passed: bool
    required: bool
    status: ReadinessStatus
    evidence: str
    blocker: bool
    notes: str


@dataclass(frozen=True)
class LiveModeReadinessReport:
    """Passive readiness report for limited live mode."""

    status: ReadinessStatus
    ready_for_limited_live_mode: bool
    items: Tuple[ReadinessItem, ...]
    blockers: Tuple[str, ...]
    next_required_actions: Tuple[str, ...]
    safety_verdict: str


_CHECK_CONFIG: Tuple[Tuple[ReadinessCheck, bool, bool, str, str], ...] = (
    (
        ReadinessCheck.SAFE_OBSERVER_VERIFIED,
        True,
        False,
        "Safe Observer dry-run verified",
        "Verify Safe Observer dry-run report exits SAFE with zero execution",
    ),
    (
        ReadinessCheck.STARTUP_STABLE,
        True,
        False,
        "Startup storage fallback baseline verified",
        "Verify startup health gate and storage fallback",
    ),
    (
        ReadinessCheck.DIRTY_CORE_CLEANED,
        True,
        True,
        "project_guardian/core.py dirty hunks permanently rejected; file matches HEAD",
        "Clean or safely commit quarantined project_guardian/core.py hunks",
    ),
    (
        ReadinessCheck.DIRTY_SERVER_CLEANED,
        True,
        True,
        "elysia/api/server.py dirty hunks permanently rejected; file matches HEAD",
        "Clean or safely commit quarantined elysia/api/server.py hunks",
    ),
    (
        ReadinessCheck.ALLOWLIST_IMPLEMENTED,
        True,
        False,
        "Passive live-action gate scaffolding implemented",
        "Implement passive live-action allowlist gate scaffolding",
    ),
    (
        ReadinessCheck.APPROVAL_PACKET_IMPLEMENTED,
        True,
        False,
        "Passive approval packet scaffolding implemented",
        "Implement passive approval packet scaffolding",
    ),
    (
        ReadinessCheck.OPERATOR_DECISION_IMPLEMENTED,
        True,
        False,
        "Passive operator decision scaffolding implemented",
        "Implement passive operator decision scaffolding",
    ),
    (
        ReadinessCheck.AUDIT_IMPLEMENTED,
        True,
        False,
        "Passive live-action audit scaffolding implemented",
        "Implement passive live-action audit scaffolding",
    ),
    (
        ReadinessCheck.ROLLBACK_METADATA_IMPLEMENTED,
        True,
        False,
        "Passive rollback metadata scaffolding implemented",
        "Implement passive rollback metadata scaffolding",
    ),
    (
        ReadinessCheck.LIVE_EXECUTOR_IMPLEMENTED,
        True,
        True,
        "Live executor not implemented",
        "Implement approval-gated live executor (future milestone)",
    ),
    (
        ReadinessCheck.UI_OR_API_APPROVAL_ROUTE_IMPLEMENTED,
        True,
        True,
        "UI/API approval route not implemented",
        "Implement operator UI or API approval route (future milestone)",
    ),
    (
        ReadinessCheck.HARMLESS_LIVE_ACTION_SMOKE_VERIFIED,
        True,
        True,
        "Harmless live-action smoke not verified",
        "Run and verify harmless live-action smoke test (future milestone)",
    ),
    (
        ReadinessCheck.AUTONOMY_CONFIG_DEFAULT_DISABLED,
        True,
        True,
        "config/autonomy.json remains enabled=false by design",
        "Keep config/autonomy.json disabled until explicit operator opt-in",
    ),
    (
        ReadinessCheck.FULL_RUNTIME_TESTS_CLASSIFIED,
        True,
        False,
        "Full runtime tests classified for safe vs live paths",
        "Classify full runtime test suite for safe vs live execution paths",
    ),
)


def _resolve_evidence(evidence: Optional[Mapping[str, bool]] = None) -> Dict[str, bool]:
    merged = dict(DEFAULT_EVIDENCE)
    if evidence:
        for key, value in evidence.items():
            merged[str(key)] = bool(value)
    return merged


def _item_status(passed: bool, is_blocker: bool) -> ReadinessStatus:
    if passed:
        return ReadinessStatus.READY
    if is_blocker:
        return ReadinessStatus.BLOCKED
    return ReadinessStatus.NOT_READY


def _overall_status(items: Tuple[ReadinessItem, ...]) -> ReadinessStatus:
    if any(item.status is ReadinessStatus.BLOCKED for item in items if item.required):
        return ReadinessStatus.BLOCKED
    if any(item.status is ReadinessStatus.NOT_READY for item in items if item.required):
        return ReadinessStatus.NOT_READY
    if any(item.status is ReadinessStatus.NEEDS_REVIEW for item in items if item.required):
        return ReadinessStatus.NEEDS_REVIEW
    return ReadinessStatus.READY


def evaluate_live_mode_readiness(
    evidence: Optional[Mapping[str, bool]] = None,
) -> LiveModeReadinessReport:
    """Evaluate passive readiness for limited live mode. Never grants execution permission."""
    resolved = _resolve_evidence(evidence)
    items: list[ReadinessItem] = []
    blockers: list[str] = []
    next_actions: list[str] = []

    for check, required, is_blocker, pass_note, fail_action in _CHECK_CONFIG:
        passed = bool(resolved.get(check.value, False))
        status = _item_status(passed, is_blocker)
        notes = pass_note if passed else fail_action
        item_blocker = required and is_blocker and not passed
        items.append(
            ReadinessItem(
                check=check,
                passed=passed,
                required=required,
                status=status,
                evidence=str(passed),
                blocker=item_blocker,
                notes=notes,
            )
        )
        if item_blocker:
            blockers.append(f"{check.value}: {fail_action}")
        elif required and not passed:
            next_actions.append(fail_action)

    item_tuple = tuple(items)
    all_required_pass = all(item.passed for item in item_tuple if item.required)
    ready_for_limited_live_mode = all_required_pass

    status = _overall_status(item_tuple)
    if not all_required_pass and status is ReadinessStatus.READY:
        status = ReadinessStatus.NOT_READY

    safety_verdict = (
        "READY_FOR_LIMITED_LIVE_MODE"
        if all_required_pass
        else "NOT_READY_FOR_LIVE_MODE"
    )

    return LiveModeReadinessReport(
        status=status,
        ready_for_limited_live_mode=ready_for_limited_live_mode,
        items=item_tuple,
        blockers=tuple(blockers),
        next_required_actions=tuple(dict.fromkeys(next_actions + blockers)),
        safety_verdict=safety_verdict,
    )


def serialize_live_mode_readiness_report(report: LiveModeReadinessReport) -> Dict[str, Any]:
    """Return a JSON-safe plain dict for a readiness report."""
    return {
        "status": report.status.value,
        "ready_for_limited_live_mode": report.ready_for_limited_live_mode,
        "items": [
            {
                "check": item.check.value,
                "passed": item.passed,
                "required": item.required,
                "status": item.status.value,
                "evidence": item.evidence,
                "blocker": item.blocker,
                "notes": item.notes,
            }
            for item in report.items
        ],
        "blockers": list(report.blockers),
        "next_required_actions": list(report.next_required_actions),
        "safety_verdict": report.safety_verdict,
    }
