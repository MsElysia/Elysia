"""Runtime-disconnected source-of-authority contract for verifier admission.

This module models evidence a future trusted authentication/policy/history service
must supply. It performs no authentication, GitHub ingestion, network access,
admission, reducer routing, runtime/provider execution, or writes. These Python
objects are representations, not credentials or authority tokens.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional, Tuple

_EXACT_SHA = re.compile(r"^[0-9a-f]{40}$")
_FORBIDDEN_AUTH_METHODS = frozenset({"github-owner", "github-app", "github-user", "github-team"})


@dataclass(frozen=True, slots=True)
class AuthenticationReceipt:
    principal_id: str
    method: str
    event_ref: str
    issuer_ref: str
    authenticated_at_epoch_s: int
    expires_at_epoch_s: Optional[int]


@dataclass(frozen=True, slots=True)
class EligibilityReceipt:
    principal_id: str
    role: str
    contract: str
    product_sha: str
    policy_generation: int
    grant_ref: str
    issuer_ref: str
    expires_at_epoch_s: Optional[int]


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    sequence: int
    submission_id: str
    decision_ref: str
    product_sha: str
    contract: str
    principal_id: str
    policy_generation: int


@dataclass(frozen=True, slots=True)
class HistorySnapshot:
    source_ref: str
    generation: int
    entries: Tuple[HistoryEntry, ...]


@dataclass(frozen=True, slots=True)
class AdmissionSourceSnapshot:
    authentication: AuthenticationReceipt
    eligibility: EligibilityReceipt
    history: HistorySnapshot
    product_sha: str
    contract: str
    policy_generation: int


@dataclass(frozen=True, slots=True)
class SourceResolution:
    accepted: bool
    reason: str
    snapshot: Optional[AdmissionSourceSnapshot]


def _text(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def _integer(value: object) -> bool:
    return type(value) is int and value >= 0


def _sha(value: object) -> bool:
    return type(value) is str and _EXACT_SHA.fullmatch(value) is not None


def _expiry(value: object) -> bool:
    return value is None or _integer(value)


def _reject(reason: str) -> SourceResolution:
    return SourceResolution(False, reason, None)


def resolve_admission_sources(
    authentication: object,
    eligibility: object,
    history: object,
    *,
    product_sha: object,
    contract: object,
    policy_generation: object,
    now_epoch_s: object,
) -> SourceResolution:
    """Validate one immutable, exactly scoped source snapshot or reject closed."""
    if not _sha(product_sha) or not _text(contract) or not _integer(policy_generation) or not _integer(now_epoch_s):
        return _reject("invalid_expected_scope")
    if type(authentication) is not AuthenticationReceipt:
        return _reject("untrusted_authentication_source")
    if type(eligibility) is not EligibilityReceipt:
        return _reject("untrusted_eligibility_source")
    if type(history) is not HistorySnapshot:
        return _reject("untrusted_history_source")

    a = authentication
    if not all((_text(a.principal_id), _text(a.method), _text(a.event_ref), _text(a.issuer_ref),
                _integer(a.authenticated_at_epoch_s), _expiry(a.expires_at_epoch_s))):
        return _reject("malformed_authentication_receipt")
    if a.method.lower() in _FORBIDDEN_AUTH_METHODS:
        return _reject("github_identity_is_not_authentication")
    if a.authenticated_at_epoch_s > now_epoch_s:
        return _reject("future_authentication")
    if a.expires_at_epoch_s is not None and a.expires_at_epoch_s <= now_epoch_s:
        return _reject("expired_authentication")

    e = eligibility
    if not all((_text(e.principal_id), _text(e.role), _text(e.contract), _sha(e.product_sha),
                _integer(e.policy_generation), _text(e.grant_ref), _text(e.issuer_ref), _expiry(e.expires_at_epoch_s))):
        return _reject("malformed_eligibility_receipt")
    if e.principal_id != a.principal_id or e.role != "verifier":
        return _reject("principal_or_role_mismatch")
    if e.contract != contract or e.product_sha != product_sha:
        return _reject("eligibility_scope_mismatch")
    if e.policy_generation != policy_generation:
        return _reject("stale_policy_generation")
    if e.expires_at_epoch_s is not None and e.expires_at_epoch_s <= now_epoch_s:
        return _reject("expired_eligibility")

    h = history
    if not _text(h.source_ref) or not _integer(h.generation) or h.generation != policy_generation or type(h.entries) is not tuple:
        return _reject("malformed_history_snapshot")
    prior_sequence = -1
    seen: dict[str, tuple[str, str, str, int]] = {}
    for entry in h.entries:
        if type(entry) is not HistoryEntry:
            return _reject("malformed_history_entry")
        if not all((_integer(entry.sequence), _text(entry.submission_id), _text(entry.decision_ref),
                    _sha(entry.product_sha), _text(entry.contract), _text(entry.principal_id),
                    _integer(entry.policy_generation))):
            return _reject("malformed_history_entry")
        if entry.sequence <= prior_sequence:
            return _reject("non_append_only_history")
        prior_sequence = entry.sequence
        if entry.product_sha != product_sha or entry.contract != contract or entry.policy_generation != policy_generation:
            return _reject("history_scope_mismatch")
        identity = (entry.product_sha, entry.contract, entry.principal_id, entry.policy_generation)
        existing = seen.get(entry.submission_id)
        if existing is not None and existing != identity:
            return _reject("conflicting_history_replay")
        seen[entry.submission_id] = identity

    snapshot = AdmissionSourceSnapshot(a, e, h, product_sha, contract, policy_generation)
    return SourceResolution(True, "sources_bound", snapshot)
