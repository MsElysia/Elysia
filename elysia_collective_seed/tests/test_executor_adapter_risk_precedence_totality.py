from dataclasses import replace
from datetime import datetime, timezone

from elysia_collective_seed.autopilot.executor_adapter import (
    InvocationEnvelope,
    TrustedExecutionState,
    dry_run_executor,
)

NOW = datetime(2026, 9, 16, 13, 0, tzinfo=timezone.utc)
SHA = "a" * 40


def pair():
    envelope = InvocationEnvelope(
        task_id="AUTOPILOT-004-X2", task_digest="digest-2", worker_id="worker-2",
        provider_id="sandbox", claim_id="claim-2", lease_id="lease-2",
        lease_expires_at="2026-09-16T14:00:00+00:00", repository="MsElysia/Elysia",
        branch="chatgpt/autopilot-004-risk-precedence-totality-repair", expected_start_sha=SHA,
        requested_capabilities=("read_repo", "run_tests"), risk_class="low",
        attempt_id="attempt-2",
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


def test_blocked_authoritative_task_risk_precedes_generic_risk_escalation():
    envelope, state = pair()
    for blocked_risk in ("repo_write", "external_write", "deployment", "sensitive_data", "privileged", "future_unknown"):
        supplied = replace(envelope, task_risk_class=blocked_risk, risk_class="critical")
        trusted = replace(state, trusted_task_risk_class=blocked_risk)
        result = dry_run_executor(supplied, trusted, now=NOW)
        assert result.outcome == "refused"
        assert result.reason == "task_risk_not_executable"


def test_malformed_trusted_capabilities_never_raise_on_early_refusals():
    envelope, state = pair()
    malformed = replace(state, approved_capabilities=("read_repo", None))
    cases = (
        (replace(envelope, worker_id="wrong"), malformed, "worker_mismatch"),
        (replace(envelope, lease_id="wrong"), malformed, "lease_mismatch"),
        (envelope, replace(malformed, worker_registered=False), "unregistered_worker"),
        (replace(envelope, branch="main"), replace(malformed, branch="main"), "non_isolated_branch"),
        (replace(envelope, expected_start_sha="not-a-sha"), replace(malformed, current_sha="not-a-sha"), "malformed_start_sha"),
    )
    for supplied, trusted, reason in cases:
        result = dry_run_executor(supplied, trusted, now=NOW)
        assert result.outcome == "refused"
        assert result.reason == reason
        assert result.approved_capabilities == ()


def test_malformed_trusted_capabilities_fail_closed_at_capability_gate():
    envelope, state = pair()
    malformed = replace(state, approved_capabilities=("read_repo", None))
    result = dry_run_executor(envelope, malformed, now=NOW)
    assert result.outcome == "refused"
    assert result.reason == "malformed_capability"
    assert result.approved_capabilities == ()
