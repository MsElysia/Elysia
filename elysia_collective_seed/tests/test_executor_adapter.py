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
        attempt_id="attempt-1", task_risk_class="read_only",
    )
    state = TrustedExecutionState(
        task_id=envelope.task_id, task_digest=envelope.task_digest, worker_id=envelope.worker_id,
        provider_id=envelope.provider_id, claim_id=envelope.claim_id, lease_id=envelope.lease_id,
        lease_expires_at=envelope.lease_expires_at, repository=envelope.repository,
        branch=envelope.branch, current_sha=SHA,
        approved_capabilities=("run_tests", "read_repo"), maximum_risk_class="medium",
        attempt_id=envelope.attempt_id, trusted_task_risk_class="read_only",
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
        supplied = replace(envelope, branch=protected)
        trusted = replace(state, branch=protected)
        assert dry_run_executor(supplied, trusted, now=NOW).reason == "non_isolated_branch"
    bad_sha = replace(envelope, expected_start_sha="not-a-sha")
    assert dry_run_executor(bad_sha, replace(state, current_sha="not-a-sha"), now=NOW).reason == "malformed_start_sha"


def test_ambiguous_or_unsupported_branch_refs_fail_closed():
    envelope, state = pair()
    for branch in ("refs/remotes/origin/main", "refs/tags/main", "refs/heads/refs/heads/master", "refs/heads/refs/tags/topic", "refs/heads/", "refs/"):
        result = dry_run_executor(replace(envelope, branch=branch), replace(state, branch=branch), now=NOW)
        assert result.outcome == "refused"
        assert result.reason == "non_isolated_branch"


def test_plain_and_single_heads_ref_isolated_branches_are_accepted():
    envelope, state = pair()
    for branch in ("feature/sandbox-safe", "refs/heads/feature/sandbox-safe"):
        result = dry_run_executor(replace(envelope, branch=branch), replace(state, branch=branch), now=NOW)
        assert result.outcome == "would_execute"


def test_capability_containers_must_be_tuples_and_are_not_consumed():
    envelope, state = pair()

    def generated():
        yield "read_repo"
        yield "run_tests"

    malformed = ["read_reporun_tests", {"read_repo": True, "run_tests": True}, ["read_repo", "run_tests"], iter(("read_repo", "run_tests")), generated()]
    for value in malformed:
        result = dry_run_executor(replace(envelope, requested_capabilities=value), state, now=NOW)
        assert result.outcome == "refused"
        assert result.reason == "malformed_capability"
    for value in malformed:
        result = dry_run_executor(envelope, replace(state, approved_capabilities=value), now=NOW)
        assert result.outcome == "refused"
        assert result.reason == "malformed_capability"
        assert result.approved_capabilities == ()
    requested_gen = generated()
    approved_gen = generated()
    result = dry_run_executor(replace(envelope, requested_capabilities=requested_gen), replace(state, approved_capabilities=approved_gen), now=NOW)
    assert result.outcome == "refused"
    assert result.reason == "malformed_capability"
    assert tuple(requested_gen) == ("read_repo", "run_tests")
    assert tuple(approved_gen) == ("read_repo", "run_tests")
    duplicate_tuple = replace(envelope, requested_capabilities=("run_tests", "read_repo", "run_tests"))
    assert dry_run_executor(duplicate_tuple, state, now=NOW).outcome == "would_execute"


def test_task_packet_risk_is_bound_to_executor_authority_fail_closed():
    envelope, state = pair()
    sandbox_env = replace(envelope, task_risk_class="sandbox_write", risk_class="medium")
    sandbox_state = replace(state, trusted_task_risk_class="sandbox_write")
    assert dry_run_executor(sandbox_env, sandbox_state, now=NOW).outcome == "would_execute"
    downgraded = replace(sandbox_env, risk_class="low")
    assert dry_run_executor(downgraded, sandbox_state, now=NOW).reason == "task_risk_downgrade"
    mismatched = replace(sandbox_env, task_risk_class="read_only")
    assert dry_run_executor(mismatched, sandbox_state, now=NOW).reason == "task_risk_mismatch"
    for blocked_risk in ("repo_write", "external_write", "deployment", "sensitive_data", "privileged"):
        blocked_state = replace(state, trusted_task_risk_class=blocked_risk)
        supplied = replace(envelope, task_risk_class=blocked_risk, risk_class="critical")
        assert dry_run_executor(supplied, blocked_state, now=NOW).reason == "task_risk_not_executable"
    unknown_state = replace(state, trusted_task_risk_class="future_unknown")
    unknown = replace(envelope, task_risk_class="future_unknown")
    assert dry_run_executor(unknown, unknown_state, now=NOW).reason == "task_risk_not_executable"


def test_task_risk_binding_is_mandatory_before_would_execute():
    envelope, state = pair()
    cases = [
        (replace(envelope, task_risk_class=None), replace(state, trusted_task_risk_class=None), "task_risk_binding_missing"),
        (replace(envelope, task_risk_class=None), state, "task_risk_binding_incomplete"),
        (envelope, replace(state, trusted_task_risk_class=None), "task_risk_binding_incomplete"),
        (replace(envelope, task_risk_class="sandbox_write"), state, "task_risk_mismatch"),
    ]
    for supplied, trusted, reason in cases:
        result = dry_run_executor(supplied, trusted, now=NOW)
        assert result.outcome == "refused"
        assert result.reason == reason


def test_malformed_task_risk_bindings_fail_closed_without_raising():
    envelope, state = pair()
    malformed_values = ([], {}, "")
    for value in malformed_values:
        result = dry_run_executor(replace(envelope, task_risk_class=value), replace(state, trusted_task_risk_class=value), now=NOW)
        assert result.outcome == "refused"
        assert result.reason == "malformed_task_risk_binding"
    one_sided = dry_run_executor(replace(envelope, task_risk_class=[]), state, now=NOW)
    assert one_sided.outcome == "refused"
    assert one_sided.reason == "malformed_task_risk_binding"


def test_trusted_authority_booleans_require_exact_bool_type():
    envelope, state = pair()
    fields = ("worker_registered", "claim_known", "lease_known", "attempt_unused", "human_approval_required")
    malformed_values = ("false", "true", 0, 1, None, [], {})
    for field in fields:
        for value in malformed_values:
            result = dry_run_executor(envelope, replace(state, **{field: value}), now=NOW)
            assert result.outcome == "refused", (field, value)
            assert result.reason == "malformed_trusted_boolean", (field, value)
    assert dry_run_executor(envelope, replace(state, worker_registered=False), now=NOW).reason == "unregistered_worker"
    assert dry_run_executor(envelope, replace(state, claim_known=False), now=NOW).reason == "unknown_claim"
    assert dry_run_executor(envelope, replace(state, lease_known=False), now=NOW).reason == "unknown_lease"
    assert dry_run_executor(envelope, replace(state, attempt_unused=False), now=NOW).reason == "attempt_reuse"
    assert dry_run_executor(envelope, replace(state, human_approval_required=False), now=NOW).outcome == "would_execute"


def test_human_approval_is_blocking_and_exactly_bound():
    envelope, state = pair()
    state = replace(state, human_approval_required=True, human_approval_ref="approval-7")
    assert dry_run_executor(envelope, state, now=NOW).outcome == "blocked"
    assert dry_run_executor(replace(envelope, human_approval_ref="approval-7"), state, now=NOW).outcome == "would_execute"


def test_dry_run_rejects_every_nonempty_completion_or_side_effect_claim():
    envelope, state = pair()
    result = dry_run_executor(envelope, state, now=NOW)
    claims = [{"commit_sha": "b" * 40, "task_completed": True}, {"status": "completed"}, {"completed": True}, {"sha": "b" * 40}, {"changes": ["file.txt"]}, {"provider_success": True}, {"verdict": "PASS"}, {"unknown_future_completion_key": "anything"}]
    for claim in claims:
        forged = reject_simulated_completion(result, claim)
        assert forged.outcome == "refused"
        assert forged.reason == "forged_completion_or_side_effect"


def test_empty_completion_claim_cannot_upgrade_dry_run_result():
    envelope, state = pair()
    result = dry_run_executor(envelope, state, now=NOW)
    assert reject_simulated_completion(result, {}) == result
