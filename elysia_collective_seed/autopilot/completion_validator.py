"""Provider-neutral completion packet validation for AUTOPILOT-004.

This module is deliberately runtime-disabled and side-effect free. It validates the
minimum semantic contract required before a worker completion may be considered for
ledger state transition. It does not invoke providers, write GitHub state, execute
Guardian runtime code, merge, or deploy.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

OUTCOMES = {"completed", "partial", "blocked", "failed", "rejected"}
NEXT_ACTIONS = {"verify", "continue", "retry", "spawn_followup", "human_review", "archive", "none"}
CHECK_RESULTS = {"pass", "fail", "skip", "not_run"}


@dataclass(frozen=True)
class CompletionValidation:
    valid: bool
    task_id: str | None
    outcome: str | None
    reasons: tuple[str, ...]


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_completion(
    packet: Mapping,
    *,
    expected_task_id: str | None = None,
    required_checks: Sequence[str] = (),
) -> CompletionValidation:
    """Validate a completion packet without mutating persistent state.

    JSON Schema remains the structural source of truth. This function adds the
    semantic checks needed by the orchestrator before accepting a completion:
    task identity, meaningful worker attribution, known outcomes/actions, unique
    check names, required-check presence, and no failed required checks.
    """
    reasons: list[str] = []
    if "packet_id" in packet and not _nonempty_string(packet["packet_id"]):
        reasons.append("invalid_packet_id")
    for field in ("evidence_refs", "commits", "pull_requests"):
        if field in packet and (not isinstance(packet[field], list) or any(not _nonempty_string(ref) for ref in packet[field])):
            reasons.append(f"invalid_{field}")
    if "claims" in packet:
        claims = packet["claims"]
        if not isinstance(claims, list) or any(
            not isinstance(claim, Mapping)
            or not isinstance(claim.get("evidence"), list)
            or any(not _nonempty_string(ref) for ref in claim["evidence"])
            for claim in claims
        ):
            reasons.append("invalid_claim_evidence")
    task_id = packet.get("task_id")
    outcome = packet.get("outcome")

    if not _nonempty_string(task_id):
        reasons.append("invalid_task_id")
        task_id_s = None
    else:
        task_id_s = str(task_id)
        if expected_task_id is not None and task_id_s != expected_task_id:
            reasons.append("task_id_mismatch")

    if outcome not in OUTCOMES:
        reasons.append("invalid_outcome")
        outcome_s = None
    else:
        outcome_s = str(outcome)

    if not _nonempty_string(packet.get("summary")):
        reasons.append("missing_summary")

    worker = packet.get("worker")
    if not isinstance(worker, Mapping):
        reasons.append("invalid_worker")
    else:
        if not _nonempty_string(worker.get("provider")):
            reasons.append("missing_worker_provider")
        if not _nonempty_string(worker.get("role")):
            reasons.append("missing_worker_role")

    recommendation = packet.get("next_recommendation")
    if not isinstance(recommendation, Mapping) or recommendation.get("action") not in NEXT_ACTIONS:
        reasons.append("invalid_next_recommendation")

    checks = packet.get("checks")
    seen: dict[str, str] = {}
    if not isinstance(checks, list):
        reasons.append("invalid_checks")
    else:
        for check in checks:
            if not isinstance(check, Mapping) or not _nonempty_string(check.get("name")):
                reasons.append("invalid_check")
                continue
            name = str(check["name"])
            result = check.get("result")
            if result not in CHECK_RESULTS:
                reasons.append(f"invalid_check_result:{name}")
                continue
            if name in seen:
                reasons.append(f"duplicate_check:{name}")
            seen[name] = str(result)

    for name in required_checks:
        result = seen.get(name)
        if result is None:
            reasons.append(f"missing_required_check:{name}")
        elif result != "pass":
            reasons.append(f"required_check_not_passed:{name}:{result}")

    # A worker may report completed only when its own declared checks contain no
    # explicit failures. Independent verification remains a separate later gate.
    if outcome_s == "completed" and any(result == "fail" for result in seen.values()):
        reasons.append("completed_with_failed_check")

    return CompletionValidation(
        valid=not reasons,
        task_id=task_id_s,
        outcome=outcome_s,
        reasons=tuple(reasons),
    )
