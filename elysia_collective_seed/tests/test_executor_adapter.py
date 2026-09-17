from dataclasses import replace
from datetime import datetime, timezone

from elysia_collective_seed.autopilot.executor_adapter import (
    InvocationEnvelope,
    TrustedExecutionState,
    dry_run_executor,
    reject_simulated_completion,
)

NOW = datetime(2026, 9, 16, 13, 0, tzinfo=timezone.utc)
SHA = "a" * 40


def pair():
    envelope = InvocationEnvelope(
        task_id="AUTOPILOT-004-X1", task_digest="digest-1", worker_id="worker-1",
        provider_id="sandbox", claim_id="claim-1", lease_id="lease-1",
        lease_expires_at="2026-09-16T14:00:00+00:00", repository="MsElysia/Elysia",
        branch="chatgpt/autopilot-004-disabled-executor-contract", expected_start_sha=SHA,
        requested_capabilities=("read_repo", "run_tests"), risk_class="low",
        attempt_id="attempt-1",
    )
    state = TrustedExecutionState(
        task_id=envelope.task_id, task_digest=envelope.task_digest, worker_id=envelope.worker_id,
        provider_id=envelope.provider_id, claim_id=envelope.claim_id, lease_id=envelope.lease_id,
        lease_expires_at=envelope.lease_expires_at, repository=envelope.repository,
        branch=envelope.branch, current_sha=SHA,
        approved_capabilities=("run_tests", "read_repo"), maximum_risk_class="medium",
        attempt_id=envelope.attempt_id,
    )
    return envelope, state


def test_valid_envelope_is_deterministic_and_only_would_execute():
    envelope, state = pair()
    first = dry_run_executor(envelope, state, now=NOW)
    second = dry_run_executor(envelope, state, now=NOW)
    assert first == second
    assert first.outcome == "would_execute"
    assert first.reason is None
    assert first.approved_capabilities == ("read_repo", "run_tests")
    assert "side_effects:none" in first.evidence


def test_identity_and_authority_mismatches_fail_closed():
    envelope, state = pair()
    cases = [
        (replace(envelope, task_digest="other"), state, "task_digest_mismatch"),
        (replace(envelope, worker_id="other"), state, "worker_mismatch"),
        (replace(envelope, provider_id="live"), state, "provider_mismatch"),
        (replace(envelope, claim_id="other"), state, "claim_mismatch"),
        (replace(envelope, lease_id="other"), state, "lease_mismatch"),
        (replace(envelope, repository="other/repo"), state, "repository_mismatch"),
        (replace(envelope, branch="other-branch"), state, "branch_mismatch"),
        (replace(envelope, expected_start_sha="b" * 40), state, "start_sha_mismatch"),
        (replace(envelope, attempt_id="other"), state, "attempt_mismatch"),
        (envelope, replace(state, worker_registered=False), "unregistered_worker"),
        (envelope, replace(state, claim_known=False), "unknown_claim"),
        (envelope, replace(state, lease_known=False), "unknown_lease"),
        (envelope, replace(state, attempt_unused=False), "attempt_reuse"),
        (replace(envelope, requested_capabilities=("read_repo", "git_write")), state, "capability_expansion"),
        (replace(envelope, risk_class="critical"), state, "risk_escalation"),
    ]
    for supplied, trusted, reason in cases:
        result = dry_run_executor(supplied, trusted, now=NOW)
        assert result.outcome == "refused", reason
        assert result.reason == reason


def test_stale_lease_nonisolated_branch_and_malformed_sha_refuse():
    envelope, state = pair()
    expired = replace(envelope, lease_expires_at="2026-09-16T12:00:00+00:00")
    expired_state = replace(state, lease_expires_at=expired.lease_expires_at)
    assert dry_run_executor(expired, expired_state, now=NOW).reason == "expired_lease"

    for protected in ("main", "master", "refs/heads/main", "refs/heads/master"):
        protected_envelope = replace(envelope, branch=protected)
        protected_state = replace(state, branch=protected)
        result = dry_run_executor(protected_envelope, protected_state, now=NOW)
        assert result.outcome == "refused", protected
        assert result.reason == "non_isolated_branch", protected

    bad_sha = replace(envelope, expected_start_sha="not-a-sha")
    bad_sha_state = replace(state, current_sha="not-a-sha")
    assert dry_run_executor(bad_sha, bad_sha_state, now=NOW).reason == "malformed_start_sha"


def test_ambiguous_or_unsupported_branch_refs_fail_closed():
    envelope, state = pair()
    bad_refs = (
        "refs/remotes/origin/main",
        "refs/tags/main",
        "refs/heads/refs/heads/master",
        "refs/heads/refs/tags/topic",
        "refs/heads/",
        "refs/",
    )
    for branch in bad_refs:
        supplied = replace(envelope, branch=branch)
        trusted = replace(state, branch=branch)
        result = dry_run_executor(supplied, trusted, now=NOW)
        assert result.outcome == "refused", branch
        assert result.reason == "non_isolated_branch", branch


def test_plain_and_single_heads_ref_isolated_branches_are_accepted():
    envelope, state = pair()
    for branch in ("feature/sandbox-safe", "refs/heads/feature/sandbox-safe"):
        supplied = replace(envelope, branch=branch)
        trusted = replace(state, branch=branch)
        result = dry_run_executor(supplied, trusted, now=NOW)
        assert result.outcome == "would_execute", branch
        assert result.reason is None, branch


def test_human_approval_is_blocking_and_exactly_bound():
    envelope, state = pair()
    state = replace(state, human_approval_required=True, human_approval_ref="approval-7")
    blocked = dry_run_executor(envelope, state, now=NOW)
    assert blocked.outcome == "blocked"
    assert blocked.reason == "human_approval_missing_or_mismatched"

    approved = dry_run_executor(replace(envelope, human_approval_ref="approval-7"), state, now=NOW)
    assert approved.outcome == "would_execute"


def test_dry_run_rejects_every_nonempty_completion_or_side_effect_claim():
    envelope, state = pair()
    result = dry_run_executor(envelope, state, now=NOW)
    claims = [
        {"commit_sha": "b" * 40, "task_completed": True},
        {"status": "completed"},
        {"completed": True},
        {"sha": "b" * 40},
        {"changes": ["file.txt"]},
        {"provider_success": True},
        {"verdict": "PASS"},
        {"unknown_future_completion_key": "anything"},
    ]
    for claim in claims:
        forged = reject_simulated_completion(result, claim)
        assert forged.outcome == "refused", claim
        assert forged.reason == "forged_completion_or_side_effect", claim
        assert "completion:forged_refused" in forged.evidence


def test_empty_completion_claim_cannot_upgrade_dry_run_result():
    envelope, state = pair()
    result = dry_run_executor(envelope, state, now=NOW)
    unchanged = reject_simulated_completion(result, {})
    assert unchanged == result
    assert unchanged.outcome == "would_execute"
