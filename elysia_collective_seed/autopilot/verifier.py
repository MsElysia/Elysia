"""Deterministic, runtime-disabled verifier routing primitives.

This module never executes work or grants authority. It only determines whether
an independent verifier may claim review of producer evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .dispatcher import Worker


@dataclass(frozen=True)
class VerificationDecision:
    state: str
    worker_id: str | None
    producer_worker_id: str
    reasons: tuple[str, ...]


def select_verifier(
    *,
    producer_worker_id: str,
    producer_independence_group: str,
    workers: Iterable[Worker],
    independence_groups: dict[str, str],
    required_capabilities: frozenset[str] = frozenset({"verification"}),
    risk_class: str = "repo_write",
) -> VerificationDecision:
    """Select an eligible verifier that is independent of the producer.

    Fail closed when no independent verifier exists. The producer is excluded
    even if group metadata is absent or malformed.
    """
    eligible: list[Worker] = []
    for worker in workers:
        if not worker.available or worker.worker_id == producer_worker_id:
            continue
        if risk_class not in worker.risk_classes:
            continue
        if not required_capabilities.issubset(worker.capabilities):
            continue
        group = independence_groups.get(worker.worker_id)
        if not group or group == producer_independence_group:
            continue
        eligible.append(worker)

    if not eligible:
        return VerificationDecision(
            "blocked", None, producer_worker_id, ("no_independent_verifier",)
        )

    chosen = max(
        eligible,
        key=lambda worker: (worker.quality - 0.25 * worker.cost, worker.worker_id),
    )
    return VerificationDecision(
        "verification_claim",
        chosen.worker_id,
        producer_worker_id,
        ("independent_verifier",),
    )
