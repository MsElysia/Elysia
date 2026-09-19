"""Pure exact-SHA verifier verdict aggregation for AUTOPILOT-GOV #46.

This module intentionally accepts only typed records already admitted by a trusted
caller. It performs no GitHub ingestion, authentication, runtime activation, or
external I/O. Invalidation/retraction/supersession is audit-only in this first
product and can never change routing authority.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re
from typing import Iterable, Tuple, Union

_EXACT_SHA = re.compile(r"^[0-9a-f]{40}$")

class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    PENDING = "PENDING"
    NEEDS_REVIEW = "NEEDS_REVIEW"

class RoutingState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    PENDING = "PENDING"
    FAIL_CLOSED = "FAIL_CLOSED"

@dataclass(frozen=True, slots=True)
class VerdictRecord:
    record_id: str
    product_sha: str
    contract: str
    verifier_id: str
    verdict: Verdict
    evidence_ref: str

@dataclass(frozen=True, slots=True)
class AuditRecord:
    record_id: str
    product_sha: str
    contract: str
    action: str
    target_record_id: str
    evidence_ref: str

Record = Union[VerdictRecord, AuditRecord]

@dataclass(frozen=True, slots=True)
class AggregationResult:
    product_sha: str
    contract: str
    routing_state: RoutingState
    conflict: bool
    history: Tuple[Record, ...]
    reasons: Tuple[str, ...]

def _is_exact_sha(value: object) -> bool:
    return isinstance(value, str) and _EXACT_SHA.fullmatch(value) is not None

def _record_key(record: Record) -> tuple[str, str, str, str, str, str]:
    if isinstance(record, VerdictRecord):
        return (record.product_sha, record.contract, record.record_id, "verdict", record.verifier_id, f"{record.verdict.value}:{record.evidence_ref}")
    return (record.product_sha, record.contract, record.record_id, "audit", record.action, f"{record.target_record_id}:{record.evidence_ref}")

def _validate_record(record: Record) -> str | None:
    if type(record) not in (VerdictRecord, AuditRecord):
        return "untyped_or_unadmitted_record"
    for value in (record.record_id, record.contract, record.evidence_ref):
        if not isinstance(value, str) or not value.strip():
            return "malformed_record_identity"
    if not _is_exact_sha(record.product_sha):
        return "malformed_product_sha"
    if isinstance(record, VerdictRecord):
        if not isinstance(record.verifier_id, str) or not record.verifier_id.strip():
            return "malformed_verifier_identity"
        if not isinstance(record.verdict, Verdict):
            return "unknown_verdict"
    else:
        if not isinstance(record.action, str) or not record.action.strip():
            return "malformed_audit_action"
        if not isinstance(record.target_record_id, str) or not record.target_record_id.strip():
            return "malformed_audit_target"
    return None

def aggregate_verdict(records: Iterable[Record], *, product_sha: str, contract: str) -> AggregationResult:
    if not _is_exact_sha(product_sha):
        raise ValueError("product_sha must be an exact lowercase 40-hex SHA")
    if not isinstance(contract, str) or not contract.strip():
        raise ValueError("contract must be non-empty")
    materialized = tuple(records)
    reasons: list[str] = []
    seen: dict[str, Record] = {}
    valid_records: list[Record] = []
    for record in materialized:
        problem = _validate_record(record)
        if problem:
            reasons.append(problem)
            continue
        valid_records.append(record)
        prior = seen.get(record.record_id)
        if prior is not None and prior != record:
            reasons.append(f"conflicting_record_id:{record.record_id}")
        else:
            seen[record.record_id] = record
    history = tuple(sorted(valid_records, key=_record_key))
    if reasons:
        return AggregationResult(product_sha, contract, RoutingState.FAIL_CLOSED, True, history, tuple(sorted(set(reasons))))
    scoped = [r for r in valid_records if isinstance(r, VerdictRecord) and r.product_sha == product_sha and r.contract == contract]
    verdicts = {r.verdict for r in scoped}
    if Verdict.FAIL in verdicts:
        state = RoutingState.FAIL
    elif Verdict.PASS in verdicts:
        state = RoutingState.PASS
    else:
        state = RoutingState.PENDING
    conflict = Verdict.FAIL in verdicts and any(v != Verdict.FAIL for v in verdicts)
    return AggregationResult(product_sha, contract, state, conflict, history, ())

def aggregate_candidate_gate(
    technical_results: Iterable[AggregationResult],
    *,
    human_governance_required: bool,
    expected_product_sha: str,
    required_contracts: Iterable[str],
) -> str:
    # Governance is zero-touch dominant over every technical input.
    if type(human_governance_required) is not bool or human_governance_required:
        return "BLOCKED_BY_HUMAN_GOVERNANCE"

    # Trusted candidate identity/completeness inputs are validated before
    # technical evidence can earn any PASS credit.
    if not _is_exact_sha(expected_product_sha):
        return "BLOCKED_BY_TECHNICAL_VERDICT"
    try:
        required = tuple(required_contracts)
    except (TypeError, ValueError):
        return "BLOCKED_BY_TECHNICAL_VERDICT"
    if (
        not required
        or any(not isinstance(c, str) or not c.strip() for c in required)
        or len(set(required)) != len(required)
    ):
        return "BLOCKED_BY_TECHNICAL_VERDICT"
    required_set = set(required)

    try:
        results = tuple(technical_results)
    except (TypeError, ValueError):
        return "BLOCKED_BY_TECHNICAL_VERDICT"
    seen_contracts: set[str] = set()
    for result in results:
        if type(result) is not AggregationResult:
            return "BLOCKED_BY_TECHNICAL_VERDICT"
        if not _is_exact_sha(result.product_sha) or result.product_sha != expected_product_sha:
            return "BLOCKED_BY_TECHNICAL_VERDICT"
        if not isinstance(result.contract, str) or not result.contract.strip():
            return "BLOCKED_BY_TECHNICAL_VERDICT"
        if not isinstance(result.routing_state, RoutingState):
            return "BLOCKED_BY_TECHNICAL_VERDICT"
        if result.contract not in required_set or result.contract in seen_contracts:
            return "BLOCKED_BY_TECHNICAL_VERDICT"
        seen_contracts.add(result.contract)

    if any(r.routing_state in (RoutingState.FAIL, RoutingState.FAIL_CLOSED) for r in results):
        return "BLOCKED_BY_TECHNICAL_VERDICT"
    if seen_contracts != required_set:
        return "PENDING"
    if any(r.routing_state is not RoutingState.PASS for r in results):
        return "PENDING"
    return "TECHNICALLY_PASSING_NOT_MERGE_AUTHORIZED"
