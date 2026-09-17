"""Deterministic, side-effect-free executor adapter simulation.

This module validates an invocation envelope against trusted control-plane state.
It never invokes a provider, subprocess, network, Git, GitHub, or Guardian runtime.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Iterable, Mapping, Optional, Tuple

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_ALLOWED_RISKS = ("low", "medium", "high", "critical")


@dataclass(frozen=True)
class InvocationEnvelope:
    task_id: str
    task_digest: str
    worker_id: str
    provider_id: str
    claim_id: str
    lease_id: str
    lease_expires_at: str
    repository: str
    branch: str
    expected_start_sha: str
    requested_capabilities: Tuple[str, ...]
    risk_class: str
    attempt_id: str
    human_approval_ref: Optional[str] = None


@dataclass(frozen=True)
class TrustedExecutionState:
    task_id: str
    task_digest: str
    worker_id: str
    provider_id: str
    claim_id: str
    lease_id: str
    lease_expires_at: str
    repository: str
    branch: str
    current_sha: str
    approved_capabilities: Tuple[str, ...]
    maximum_risk_class: str
    attempt_id: str
    human_approval_required: bool = False
    human_approval_ref: Optional[str] = None
    worker_registered: bool = True
    claim_known: bool = True
    lease_known: bool = True
    attempt_unused: bool = True


@dataclass(frozen=True)
class DryRunResult:
    task_id: str
    worker_id: str
    claim_id: str
    lease_id: str
    attempt_id: str
    outcome: str
    reason: Optional[str]
    repository: str
    branch: str
    expected_start_sha: str
    approved_capabilities: Tuple[str, ...]
    evidence: Tuple[str, ...]


def _parse_time(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _isolated_branch(branch: str) -> bool:
    if not isinstance(branch, str) or not branch:
        return False
    canonical = branch.removeprefix("refs/heads/")
    return canonical not in {"main", "master"}


def _normalize_caps(values: Iterable[str]) -> Tuple[str, ...]:
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError("malformed_capability")
    return tuple(sorted(set(values)))


def _result(envelope: InvocationEnvelope, state: TrustedExecutionState, outcome: str, reason: Optional[str], evidence: Iterable[str]) -> DryRunResult:
    return DryRunResult(
        task_id=envelope.task_id,
        worker_id=envelope.worker_id,
        claim_id=envelope.claim_id,
        lease_id=envelope.lease_id,
        attempt_id=envelope.attempt_id,
        outcome=outcome,
        reason=reason,
        repository=envelope.repository,
        branch=envelope.branch,
        expected_start_sha=envelope.expected_start_sha,
        approved_capabilities=_normalize_caps(state.approved_capabilities),
        evidence=tuple(evidence),
    )


def dry_run_executor(envelope: InvocationEnvelope, state: TrustedExecutionState, *, now: datetime) -> DryRunResult:
    """Validate one invocation without performing any external or mutable action."""
    if now.tzinfo is None:
        return _result(envelope, state, "refused", "naive_clock", ("clock:invalid",))
    now = now.astimezone(timezone.utc)

    required = (
        envelope.task_id, envelope.task_digest, envelope.worker_id, envelope.provider_id,
        envelope.claim_id, envelope.lease_id, envelope.lease_expires_at,
        envelope.repository, envelope.branch, envelope.expected_start_sha,
        envelope.risk_class, envelope.attempt_id,
    )
    if any(not isinstance(value, str) or not value for value in required):
        return _result(envelope, state, "refused", "missing_or_malformed_binding", ("binding:invalid",))

    exact_pairs = (
        (envelope.task_id, state.task_id, "task_id_mismatch"),
        (envelope.task_digest, state.task_digest, "task_digest_mismatch"),
        (envelope.worker_id, state.worker_id, "worker_mismatch"),
        (envelope.provider_id, state.provider_id, "provider_mismatch"),
        (envelope.claim_id, state.claim_id, "claim_mismatch"),
        (envelope.lease_id, state.lease_id, "lease_mismatch"),
        (envelope.repository, state.repository, "repository_mismatch"),
        (envelope.branch, state.branch, "branch_mismatch"),
        (envelope.expected_start_sha, state.current_sha, "start_sha_mismatch"),
        (envelope.attempt_id, state.attempt_id, "attempt_mismatch"),
    )
    for supplied, trusted, reason in exact_pairs:
        if supplied != trusted:
            return _result(envelope, state, "refused", reason, (f"refusal:{reason}",))

    if not state.worker_registered:
        return _result(envelope, state, "refused", "unregistered_worker", ("worker:unregistered",))
    if not state.claim_known:
        return _result(envelope, state, "refused", "unknown_claim", ("claim:unknown",))
    if not state.lease_known:
        return _result(envelope, state, "refused", "unknown_lease", ("lease:unknown",))
    if not state.attempt_unused:
        return _result(envelope, state, "refused", "attempt_reuse", ("attempt:reused",))
    if not _isolated_branch(envelope.branch):
        return _result(envelope, state, "refused", "non_isolated_branch", ("branch:not_isolated",))
    if not _SHA40.fullmatch(envelope.expected_start_sha):
        return _result(envelope, state, "refused", "malformed_start_sha", ("sha:invalid",))

    supplied_expiry = _parse_time(envelope.lease_expires_at)
    trusted_expiry = _parse_time(state.lease_expires_at)
    if supplied_expiry is None or trusted_expiry is None or supplied_expiry != trusted_expiry:
        return _result(envelope, state, "refused", "lease_expiry_mismatch", ("lease:expiry_invalid",))
    if trusted_expiry <= now:
        return _result(envelope, state, "refused", "expired_lease", ("lease:expired",))

    try:
        requested = _normalize_caps(envelope.requested_capabilities)
        approved = _normalize_caps(state.approved_capabilities)
    except (TypeError, ValueError):
        return _result(envelope, state, "refused", "malformed_capability", ("capability:invalid",))
    if not set(requested).issubset(approved):
        return _result(envelope, state, "refused", "capability_expansion", ("authority:capability_expansion",))

    if envelope.risk_class not in _ALLOWED_RISKS or state.maximum_risk_class not in _ALLOWED_RISKS:
        return _result(envelope, state, "refused", "malformed_risk_class", ("risk:invalid",))
    if _ALLOWED_RISKS.index(envelope.risk_class) > _ALLOWED_RISKS.index(state.maximum_risk_class):
        return _result(envelope, state, "refused", "risk_escalation", ("authority:risk_escalation",))

    if state.human_approval_required:
        if not state.human_approval_ref or envelope.human_approval_ref != state.human_approval_ref:
            return _result(envelope, state, "blocked", "human_approval_missing_or_mismatched", ("approval:blocked",))

    evidence = (
        "mode:dry_run_only",
        "side_effects:none",
        "authority:trusted_state_only",
        f"task_digest:{state.task_digest}",
        f"start_sha:{state.current_sha}",
    )
    return _result(envelope, state, "would_execute", None, evidence)


def reject_simulated_completion(result: DryRunResult, completion_claim: Mapping[str, object]) -> DryRunResult:
    """Fail closed on every non-empty completion/result claim in the disabled slice.

    The dry-run adapter has no authority to attest completion or side effects, so it
    intentionally defines no harmless completion metadata vocabulary. An empty
    mapping is the only claim that can preserve a ``would_execute`` decision.
    """
    if completion_claim:
        return DryRunResult(
            task_id=result.task_id, worker_id=result.worker_id, claim_id=result.claim_id,
            lease_id=result.lease_id, attempt_id=result.attempt_id, outcome="refused",
            reason="forged_completion_or_side_effect", repository=result.repository,
            branch=result.branch, expected_start_sha=result.expected_start_sha,
            approved_capabilities=result.approved_capabilities,
            evidence=result.evidence + ("completion:forged_refused",),
        )
    return result
