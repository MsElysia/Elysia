"""Tests for configurable mutation review wiring helpers."""

from dataclasses import dataclass, field
from datetime import datetime
from types import SimpleNamespace

from project_guardian.ai_mutation_validator import configure_ai_validator_integration
from project_guardian.mutation_engine import MutationStatus
from project_guardian.mutation_review_manager import MutationReview, ReviewDecision, RiskLevel
from project_guardian.mutation_router import configure_mutation_router


@dataclass
class _MockProposal:
    status: MutationStatus = MutationStatus.PROPOSED
    metadata: dict = field(default_factory=dict)


class _MockMutationEngine:
    def __init__(self):
        self.proposal = _MockProposal()
        self.approvals = []
        self.applied = []

    def get_mutation(self, mutation_id):
        return self.proposal

    def review_mutation(self, mutation_id, approved, reviewer="system", notes=None):
        self.approvals.append((mutation_id, approved, reviewer, notes))
        if approved:
            self.proposal.status = MutationStatus.APPROVED
        return approved

    def apply_mutation(self, mutation_id):
        self.applied.append(mutation_id)
        if self.proposal.status != MutationStatus.APPROVED:
            return False
        self.proposal.status = MutationStatus.APPLIED
        return True


class _MockReviewManager:
    def __init__(self):
        self.mutation_engine = None
        self.captured_validator = None
        self.review = MutationReview(
            review_id="review-1",
            mutation_id="mut-1",
            reviewed_at=datetime.now(),
            reviewer="tester",
            decision=ReviewDecision.APPROVE,
            risk_level=RiskLevel.LOW,
            confidence=0.95,
            reasoning="Safe to auto-apply",
        )

    def get_review(self, review_id):
        return self.review if review_id == self.review.review_id else None

    def get_latest_review(self, mutation_id):
        return self.review if mutation_id == self.review.mutation_id else None

    def review_mutation(self, mutation_id, **kwargs):
        self.captured_validator = kwargs.get("ai_validator")
        return self.review


def test_configure_mutation_router_from_minimal_guardian():
    review_manager = _MockReviewManager()
    mutation_engine = _MockMutationEngine()
    guardian = SimpleNamespace(
        mutation_review_manager=review_manager,
        mutation_engine=mutation_engine,
    )

    router = configure_mutation_router(guardian=guardian)
    route = router.route_mutation("mut-1")

    assert review_manager.mutation_engine is mutation_engine
    assert route.result["success"] is True
    assert mutation_engine.proposal.status == MutationStatus.APPLIED
    assert mutation_engine.approvals == [("mut-1", True, "auto_router", None)]


def test_configure_ai_validator_integration_from_minimal_guardian():
    review_manager = _MockReviewManager()
    mutation_engine = _MockMutationEngine()
    guardian = SimpleNamespace(
        mutation_review_manager=review_manager,
        mutation_engine=mutation_engine,
    )
    validator = object()

    configured = configure_ai_validator_integration(
        guardian=guardian,
        ai_validator=validator,
    )
    review = configured.review_mutation("mut-1")

    assert configured is review_manager
    assert review_manager.mutation_engine is mutation_engine
    assert review is review_manager.review
    assert review_manager.captured_validator is validator
