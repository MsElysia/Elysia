from dataclasses import replace
from datetime import datetime, timezone

from elysia_collective_seed.autopilot.executor_adapter import (
    InvocationEnvelope,
    TrustedExecutionState,
    dry_run_executor,
)

NOW = datetime(2026, 9, 16, 13, 0, tzinfo=timezone.utc)
SHA = "a" * 40


def _pair():
    envelope = InvocationEnvelope(
        task_id="AUTOPILOT-004-X1", task_digest="digest-1", worker_id="worker-1",
        provider_id="sandbox", claim_id="claim-1", lease_id="lease-1",
        lease_expires_at="2026-09-16T14:00:00+00:00", repository="MsElysia/Elysia",
        branch="chatgpt/autopilot-004-human-approval-ref-shape", expected_start_sha=SHA,
        requested_capabilities=("read_repo",), risk_class="low", attempt_id="attempt-1",
        task_risk_class="read_only", human_approval_ref="approval-7",
    )
    state = TrustedExecutionState(
        task_id=envelope.task_id, task_digest=envelope.task_digest, worker_id=envelope.worker_id,
        provider_id=envelope.provider_id, claim_id=envelope.claim_id, lease_id=envelope.lease_id,
        lease_expires_at=envelope.lease_expires_at, repository=envelope.repository,
        branch=envelope.branch, current_sha=SHA, approved_capabilities=("read_repo",),
        maximum_risk_class="medium", attempt_id=envelope.attempt_id,
        trusted_task_risk_class="read_only", human_approval_required=True,
        human_approval_ref="approval-7",
    )
    return envelope, state


def test_matching_nonempty_string_approval_ref_is_accepted():
    envelope, state = _pair()
    assert dry_run_executor(envelope, state, now=NOW).outcome == "would_execute"


def test_malformed_equal_approval_refs_fail_closed():
    envelope, state = _pair()
    malformed = (["forged"], {"forged": True}, ("forged",), 7, object(), "")
    for value in malformed:
        result = dry_run_executor(
            replace(envelope, human_approval_ref=value),
            replace(state, human_approval_ref=value),
            now=NOW,
        )
        assert result.outcome == "blocked"
        assert result.reason == "human_approval_malformed"


def test_one_sided_malformed_missing_and_mismatch_approval_refs_fail_closed():
    envelope, state = _pair()
    cases = (
        ([], "approval-7", "human_approval_malformed"),
        ("approval-7", {}, "human_approval_malformed"),
        (None, "approval-7", "human_approval_malformed"),
        ("approval-7", None, "human_approval_malformed"),
        ("", "approval-7", "human_approval_malformed"),
        ("approval-7", "", "human_approval_malformed"),
        ("approval-other", "approval-7", "human_approval_missing_or_mismatched"),
    )
    for supplied, trusted, reason in cases:
        result = dry_run_executor(
            replace(envelope, human_approval_ref=supplied),
            replace(state, human_approval_ref=trusted),
            now=NOW,
        )
        assert result.outcome == "blocked"
        assert result.reason == reason
