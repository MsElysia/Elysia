"""Phase 2 passive live-action allowlist and approval-gate validation.

This module classifies action risk and validates approval requests only.
It does not execute tools, call APIs, touch the browser, or wire into runtime.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class ActionRiskCategory(str, Enum):
    """Primary risk category for a proposed live action."""

    READ_ONLY = "READ_ONLY"
    WRITE_REPORT = "WRITE_REPORT"
    LOCAL_FILE_WRITE = "LOCAL_FILE_WRITE"
    LOCAL_FILE_MODIFY = "LOCAL_FILE_MODIFY"
    SHELL_COMMAND = "SHELL_COMMAND"
    NETWORK_REQUEST = "NETWORK_REQUEST"
    API_CALL = "API_CALL"
    BROWSER_OR_WEBSCOUT = "BROWSER_OR_WEBSCOUT"
    CODE_CHANGE = "CODE_CHANGE"
    PROPOSAL_IMPLEMENTATION = "PROPOSAL_IMPLEMENTATION"
    MEMORY_WRITE = "MEMORY_WRITE"
    CONFIG_CHANGE = "CONFIG_CHANGE"
    AUTONOMY_CONFIG_CHANGE = "AUTONOMY_CONFIG_CHANGE"


class AllowlistDecision(str, Enum):
    """Phase 2 allowlist decision for a risk category."""

    ALLOW_LOGGED = "ALLOW_LOGGED"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    BLOCKED = "BLOCKED"


# Phase 2 passive policy table (design: docs/PHASE2_LIVE_ACTION_ALLOWLIST_DESIGN.md).
PHASE2_POLICY: Dict[ActionRiskCategory, AllowlistDecision] = {
    ActionRiskCategory.READ_ONLY: AllowlistDecision.ALLOW_LOGGED,
    ActionRiskCategory.WRITE_REPORT: AllowlistDecision.REQUIRE_APPROVAL,
    ActionRiskCategory.MEMORY_WRITE: AllowlistDecision.REQUIRE_APPROVAL,
    ActionRiskCategory.LOCAL_FILE_WRITE: AllowlistDecision.REQUIRE_APPROVAL,
    ActionRiskCategory.LOCAL_FILE_MODIFY: AllowlistDecision.REQUIRE_APPROVAL,
    ActionRiskCategory.SHELL_COMMAND: AllowlistDecision.BLOCKED,
    ActionRiskCategory.NETWORK_REQUEST: AllowlistDecision.BLOCKED,
    ActionRiskCategory.API_CALL: AllowlistDecision.BLOCKED,
    ActionRiskCategory.BROWSER_OR_WEBSCOUT: AllowlistDecision.BLOCKED,
    ActionRiskCategory.CODE_CHANGE: AllowlistDecision.REQUIRE_APPROVAL,
    ActionRiskCategory.PROPOSAL_IMPLEMENTATION: AllowlistDecision.BLOCKED,
    ActionRiskCategory.CONFIG_CHANGE: AllowlistDecision.REQUIRE_APPROVAL,
    ActionRiskCategory.AUTONOMY_CONFIG_CHANGE: AllowlistDecision.BLOCKED,
}

# Categories that are always hard-blocked during early Phase 2 validation.
HARD_BLOCKED_CATEGORIES = frozenset(
    {
        ActionRiskCategory.AUTONOMY_CONFIG_CHANGE,
        ActionRiskCategory.PROPOSAL_IMPLEMENTATION,
        ActionRiskCategory.BROWSER_OR_WEBSCOUT,
        ActionRiskCategory.NETWORK_REQUEST,
        ActionRiskCategory.API_CALL,
    }
)


@dataclass(frozen=True)
class LiveActionApprovalRequest:
    """Structured approval packet for a proposed live action (passive data only)."""

    proposed_action: str
    reason: str
    risk_category: ActionRiskCategory
    target: str
    expected_result: str
    rollback_plan: str
    touches_autonomy_or_live_execution: bool
    writes_files: bool
    touches_network_api_or_browser: bool
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    allowlist_decision: Optional[AllowlistDecision] = None


@dataclass(frozen=True)
class LiveActionValidationResult:
    """Passive validation outcome; does not trigger execution."""

    allowed: bool
    requires_approval: bool
    blocked: bool
    decision: AllowlistDecision
    reasons: Tuple[str, ...]
    safety_verdict: str


def policy_decision_for_category(category: ActionRiskCategory) -> AllowlistDecision:
    """Return the Phase 2 policy decision for a risk category."""
    return PHASE2_POLICY[category]


def build_approval_request(
    *,
    proposed_action: str,
    reason: str,
    risk_category: ActionRiskCategory,
    target: str,
    expected_result: str,
    rollback_plan: str,
    touches_autonomy_or_live_execution: bool = False,
    writes_files: bool = False,
    touches_network_api_or_browser: bool = False,
    action_id: Optional[str] = None,
) -> LiveActionApprovalRequest:
    """Build an approval request with ``allowlist_decision`` from the policy table."""
    decision = policy_decision_for_category(risk_category)
    return LiveActionApprovalRequest(
        action_id=action_id or str(uuid.uuid4()),
        proposed_action=proposed_action,
        reason=reason,
        risk_category=risk_category,
        target=target,
        expected_result=expected_result,
        rollback_plan=rollback_plan,
        touches_autonomy_or_live_execution=touches_autonomy_or_live_execution,
        writes_files=writes_files,
        touches_network_api_or_browser=touches_network_api_or_browser,
        allowlist_decision=decision,
    )


def validate_live_action_request(request: LiveActionApprovalRequest) -> LiveActionValidationResult:
    """Validate an approval request against Phase 2 policy. Does not execute anything."""
    reasons: List[str] = []
    category = request.risk_category

    try:
        policy_decision = policy_decision_for_category(category)
    except KeyError:
        return LiveActionValidationResult(
            allowed=False,
            requires_approval=False,
            blocked=True,
            decision=AllowlistDecision.BLOCKED,
            reasons=("unknown_risk_category",),
            safety_verdict="BLOCKED",
        )

    if request.touches_autonomy_or_live_execution:
        reasons.append("touches_autonomy_or_live_execution")

    if category in HARD_BLOCKED_CATEGORIES:
        reasons.append(f"hard_block_category:{category.value}")

    if policy_decision is AllowlistDecision.BLOCKED:
        reasons.append(f"policy_blocked:{category.value}")

    if reasons:
        return LiveActionValidationResult(
            allowed=False,
            requires_approval=False,
            blocked=True,
            decision=AllowlistDecision.BLOCKED,
            reasons=tuple(reasons),
            safety_verdict="BLOCKED",
        )

    if policy_decision is AllowlistDecision.ALLOW_LOGGED:
        return LiveActionValidationResult(
            allowed=True,
            requires_approval=False,
            blocked=False,
            decision=AllowlistDecision.ALLOW_LOGGED,
            reasons=(),
            safety_verdict="SAFE",
        )

    return LiveActionValidationResult(
        allowed=False,
        requires_approval=True,
        blocked=False,
        decision=AllowlistDecision.REQUIRE_APPROVAL,
        reasons=(),
        safety_verdict="SAFE",
    )
