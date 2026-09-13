"""Pytest-discoverable coverage for the pure AUTOPILOT task-state policy."""
from elysia_collective_seed.autopilot.task_state_machine import can_claim, validate_transition


def test_claim_requires_dependencies():
    assert can_claim(status="queued", dependencies_satisfied=True, attempts=0, max_attempts=3).allowed
    assert not can_claim(status="queued", dependencies_satisfied=False, attempts=0, max_attempts=3).allowed


def test_attempt_budget_is_enforced():
    result = can_claim(status="queued", dependencies_satisfied=True, attempts=3, max_attempts=3)
    assert not result.allowed
    assert result.reason == "attempt_budget_exhausted"


def test_runtime_completion_requires_verification():
    result = validate_transition("review", "completed", risk_class="repo_write", runtime_behavior_changed=True)
    assert not result.allowed
    assert result.reason == "independent_verification_missing"


def test_verified_runtime_completion_is_allowed():
    result = validate_transition(
        "review", "completed", risk_class="repo_write",
        runtime_behavior_changed=True, independent_verification_passed=True,
    )
    assert result.allowed


def test_high_authority_completion_requires_approval():
    result = validate_transition(
        "review", "completed", risk_class="deployment",
        independent_verification_passed=True,
    )
    assert not result.allowed
    assert result.reason == "human_approval_missing"


def test_shortcut_from_queue_to_complete_is_rejected():
    result = validate_transition("queued", "completed", risk_class="read_only")
    assert not result.allowed
    assert result.reason == "transition_not_allowed"


def test_unknown_state_is_rejected():
    result = validate_transition("mystery", "completed", risk_class="read_only")
    assert not result.allowed
    assert result.reason == "unknown_current_state"


def test_archived_is_terminal():
    result = validate_transition("archived", "queued", risk_class="read_only")
    assert not result.allowed
    assert result.reason == "transition_not_allowed"
