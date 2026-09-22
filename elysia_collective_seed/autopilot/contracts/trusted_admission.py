"""Pure, runtime-disconnected verifier-admission contract.

This module does not authenticate credentials or ingest GitHub data. A future
trusted authentication boundary must supply the principal, eligibility registry,
policy inputs, and append-only prior-decision history. These freely constructible
Python objects are normative representations, never credentials or trust tokens.
The contract only validates their structural and scope bindings before
constructing a typed ``VerdictRecord``. Nothing here grants merge, deployment,
external-write, or human-governance authority. The separate governance-snapshot
model in ``admission.py`` remains unchanged and equally runtime-disconnected.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import re
from typing import Optional, Tuple

from .verdict_aggregation import Verdict, VerdictRecord


_EXACT_SHA = re.compile(r"^[0-9a-f]{40}$")
_EXACT_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class AdmissionStatus(str, Enum):
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    principal_id: str
    authentication_method: str
    authentication_event_ref: str
    authenticated_at_epoch_s: int
    policy_generation: int


@dataclass(frozen=True, slots=True)
class VerifierEligibility:
    grant_id: str
    principal_id: str
    role: str
    contracts: Tuple[str, ...]
    product_shas: Tuple[str, ...]
    policy_generation: int
    expires_at_epoch_s: Optional[int]
    issuer_ref: str


@dataclass(frozen=True, slots=True)
class AdmissionRequest:
    submission_id: str
    product_sha: str
    contract: str
    verdict: Verdict
    evidence_ref: str


@dataclass(frozen=True, slots=True)
class AdmissionAudit:
    submission_id: str
    principal_id: str
    policy_generation: int
    request_digest: str
    status: AdmissionStatus
    reason: str


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    audit: AdmissionAudit
    record: Optional[VerdictRecord]


def _exact_nonempty(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _exact_sha(value: object) -> bool:
    return type(value) is str and _EXACT_SHA.fullmatch(value) is not None


def _exact_digest(value: object) -> bool:
    return type(value) is str and _EXACT_DIGEST.fullmatch(value) is not None


def _exact_int(value: object) -> bool:
    return type(value) is int and value >= 0


def _safe_text(value: object) -> str:
    return value if type(value) is str else ""


def _reject(
    reason: str,
    *,
    request: object,
    principal: object,
    policy_generation: object,
    request_digest: str = "",
) -> AdmissionDecision:
    submission_id = _safe_text(request.submission_id) if type(request) is AdmissionRequest else ""
    principal_id = _safe_text(principal.principal_id) if type(principal) is AuthenticatedPrincipal else ""
    generation = policy_generation if _exact_int(policy_generation) else -1
    audit = AdmissionAudit(
        submission_id,
        principal_id,
        generation,
        request_digest,
        AdmissionStatus.REJECTED,
        reason,
    )
    return AdmissionDecision(audit, None)


def _request_digest(request: AdmissionRequest) -> str:
    fields = (
        request.submission_id,
        request.product_sha,
        request.contract,
        request.verdict.value,
        request.evidence_ref,
    )
    framed = b"".join(len(value.encode("utf-8")).to_bytes(8, "big") + value.encode("utf-8") for value in fields)
    return hashlib.sha256(framed).hexdigest()


def _valid_policy_tuple(values: object, *, sha_values: bool = False) -> bool:
    if type(values) is not tuple or not values:
        return False
    validator = _exact_sha if sha_values else _exact_nonempty
    return all(validator(value) for value in values) and len(set(values)) == len(values)


def _record_is_well_formed(record: object) -> bool:
    return (
        type(record) is VerdictRecord
        and _exact_nonempty(record.record_id)
        and _exact_sha(record.product_sha)
        and _exact_nonempty(record.contract)
        and _exact_nonempty(record.verifier_id)
        and type(record.verdict) is Verdict
        and _exact_nonempty(record.evidence_ref)
    )


def _prior_is_well_formed(decision: object) -> bool:
    if type(decision) is not AdmissionDecision or type(decision.audit) is not AdmissionAudit:
        return False
    audit = decision.audit
    if (
        not _exact_nonempty(audit.submission_id)
        or not _exact_nonempty(audit.principal_id)
        or not _exact_int(audit.policy_generation)
        or not _exact_digest(audit.request_digest)
        or type(audit.status) is not AdmissionStatus
        or not _exact_nonempty(audit.reason)
    ):
        return False
    if audit.status is AdmissionStatus.ADMITTED:
        return _record_is_well_formed(decision.record)
    return decision.record is None


def admit_verdict(
    principal: object,
    eligibility: object,
    request: object,
    *,
    expected_policy_generation: object,
    now_epoch_s: object,
    trusted_authentication_methods: object,
    prior_decisions: object = (),
) -> AdmissionDecision:
    """Admit one structurally bound request or return a fail-closed rejection."""
    if not _exact_int(expected_policy_generation) or not _exact_int(now_epoch_s):
        return _reject("invalid_policy_context", request=request, principal=principal, policy_generation=expected_policy_generation)
    if not _valid_policy_tuple(trusted_authentication_methods):
        return _reject("invalid_authentication_policy", request=request, principal=principal, policy_generation=expected_policy_generation)
    if type(principal) is not AuthenticatedPrincipal:
        return _reject("untrusted_principal_shape", request=request, principal=principal, policy_generation=expected_policy_generation)
    if type(eligibility) is not VerifierEligibility:
        return _reject("untrusted_eligibility_shape", request=request, principal=principal, policy_generation=expected_policy_generation)
    if type(request) is not AdmissionRequest:
        return _reject("untrusted_request_shape", request=request, principal=principal, policy_generation=expected_policy_generation)

    if (not _exact_nonempty(principal.principal_id) or not _exact_nonempty(principal.authentication_method) or not _exact_nonempty(principal.authentication_event_ref) or not _exact_int(principal.authenticated_at_epoch_s) or not _exact_int(principal.policy_generation)):
        return _reject("malformed_principal", request=request, principal=principal, policy_generation=expected_policy_generation)
    if principal.authentication_method not in trusted_authentication_methods:
        return _reject("untrusted_authentication_method", request=request, principal=principal, policy_generation=expected_policy_generation)
    if principal.authenticated_at_epoch_s > now_epoch_s:
        return _reject("future_authentication_event", request=request, principal=principal, policy_generation=expected_policy_generation)

    if (not _exact_nonempty(eligibility.grant_id) or not _exact_nonempty(eligibility.principal_id) or not _exact_nonempty(eligibility.role) or not _valid_policy_tuple(eligibility.contracts) or not _valid_policy_tuple(eligibility.product_shas, sha_values=True) or not _exact_int(eligibility.policy_generation) or (eligibility.expires_at_epoch_s is not None and not _exact_int(eligibility.expires_at_epoch_s)) or not _exact_nonempty(eligibility.issuer_ref)):
        return _reject("malformed_eligibility", request=request, principal=principal, policy_generation=expected_policy_generation)
    if eligibility.principal_id != principal.principal_id:
        return _reject("principal_eligibility_mismatch", request=request, principal=principal, policy_generation=expected_policy_generation)
    if eligibility.role != "verifier":
        return _reject("ineligible_role", request=request, principal=principal, policy_generation=expected_policy_generation)
    if principal.policy_generation != expected_policy_generation or eligibility.policy_generation != expected_policy_generation:
        return _reject("stale_policy_generation", request=request, principal=principal, policy_generation=expected_policy_generation)
    if eligibility.expires_at_epoch_s is not None and eligibility.expires_at_epoch_s <= now_epoch_s:
        return _reject("expired_eligibility", request=request, principal=principal, policy_generation=expected_policy_generation)

    if (not _exact_nonempty(request.submission_id) or not _exact_sha(request.product_sha) or not _exact_nonempty(request.contract) or type(request.verdict) is not Verdict or not _exact_nonempty(request.evidence_ref)):
        return _reject("malformed_request", request=request, principal=principal, policy_generation=expected_policy_generation)
    digest = _request_digest(request)
    if request.contract not in eligibility.contracts:
        return _reject("contract_not_eligible", request=request, principal=principal, policy_generation=expected_policy_generation, request_digest=digest)
    if request.product_sha not in eligibility.product_shas:
        return _reject("product_sha_not_eligible", request=request, principal=principal, policy_generation=expected_policy_generation, request_digest=digest)

    if type(prior_decisions) is not tuple:
        return _reject("invalid_prior_decision_history", request=request, principal=principal, policy_generation=expected_policy_generation, request_digest=digest)
    matching_prior: list[AdmissionDecision] = []
    for prior in prior_decisions:
        if not _prior_is_well_formed(prior):
            return _reject("invalid_prior_decision_history", request=request, principal=principal, policy_generation=expected_policy_generation, request_digest=digest)
        if prior.audit.submission_id != request.submission_id:
            continue
        if prior.audit.request_digest != digest:
            return _reject("conflicting_submission_id", request=request, principal=principal, policy_generation=expected_policy_generation, request_digest=digest)
        if prior.audit.principal_id != principal.principal_id or prior.audit.policy_generation != expected_policy_generation:
            return _reject("invalid_prior_decision_history", request=request, principal=principal, policy_generation=expected_policy_generation, request_digest=digest)
        if prior.audit.status is AdmissionStatus.ADMITTED:
            record = prior.record
            if (record is None or record.record_id != request.submission_id or record.product_sha != request.product_sha or record.contract != request.contract or record.verifier_id != principal.principal_id or record.verdict is not request.verdict or record.evidence_ref != request.evidence_ref):
                return _reject("invalid_prior_decision_history", request=request, principal=principal, policy_generation=expected_policy_generation, request_digest=digest)
        matching_prior.append(prior)
    if matching_prior:
        first = matching_prior[0]
        if any(prior != first for prior in matching_prior[1:]):
            return _reject("conflicting_prior_decisions", request=request, principal=principal, policy_generation=expected_policy_generation, request_digest=digest)
        return first

    record = VerdictRecord(request.submission_id, request.product_sha, request.contract, principal.principal_id, request.verdict, request.evidence_ref)
    audit = AdmissionAudit(request.submission_id, principal.principal_id, expected_policy_generation, digest, AdmissionStatus.ADMITTED, "all_bindings_valid")
    return AdmissionDecision(audit, record)
