# project_guardian/mutation_review_manager.py
# MutationReviewManager: Trust-Based Mutation Evaluation
# Reviews mutations based on trust scores and risk assessment

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
from threading import RLock
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid

try:
    from .trust_registry import TrustRegistry
    from .trust_policy_manager import TrustPolicyManager
    from .mutation_engine import MutationEngine, MutationProposal, MutationStatus
    from .trust_audit_log import TrustAuditLog, AuditEventType, AuditSeverity
    from .recovery_vault import RecoveryVault
except ImportError:
    from trust_registry import TrustRegistry
    from trust_policy_manager import TrustPolicyManager
    from mutation_engine import MutationEngine, MutationProposal, MutationStatus
    try:
        from trust_audit_log import TrustAuditLog, AuditEventType, AuditSeverity
    except ImportError:
        TrustAuditLog = None
        AuditEventType = None
        AuditSeverity = None
    try:
        from recovery_vault import RecoveryVault
    except ImportError:
        RecoveryVault = None

logger = logging.getLogger(__name__)


class ReviewDecision(Enum):
    """Review decision types."""
    APPROVE = "approve"
    REJECT = "reject"
    DEFER = "defer"  # Defer to human review
    REQUEST_CHANGES = "request_changes"


class RiskLevel(Enum):
    """Risk levels for mutations."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class MutationReview:
    """Represents a mutation review."""
    review_id: str
    mutation_id: str
    reviewed_at: datetime
    reviewer: str  # "system", "trust_registry", "policy_manager", "human"
    decision: ReviewDecision
    risk_level: RiskLevel
    confidence: float  # 0.0-1.0
    reasoning: str
    concerns: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)  # Conditions for approval
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "review_id": self.review_id,
            "mutation_id": self.mutation_id,
            "reviewed_at": self.reviewed_at.isoformat(),
            "reviewer": self.reviewer,
            "decision": self.decision.value,
            "risk_level": self.risk_level.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "concerns": self.concerns,
            "conditions": self.conditions,
            "metadata": self.metadata
        }


class MutationReviewManager:
    """
    Trust-based mutation evaluation and review.
    Uses trust scores, policies, and risk assessment to determine mutation safety.
    """
    
    def __init__(
        self,
        trust_registry: Optional[TrustRegistry] = None,
        trust_policy: Optional[TrustPolicyManager] = None,
        mutation_engine: Optional[MutationEngine] = None,
        audit_log: Optional[TrustAuditLog] = None,
        recovery_vault: Optional[RecoveryVault] = None,
        storage_path: str = "data/mutation_reviews.json",
        auto_approve_trust_threshold: float = 0.9,
        require_human_review_risk: RiskLevel = RiskLevel.HIGH
    ):
        """
        Initialize MutationReviewManager.
        
        Args:
            trust_registry: TrustRegistry instance
            trust_policy: TrustPolicyManager instance
            mutation_engine: MutationEngine instance
            audit_log: TrustAuditLog instance
            recovery_vault: RecoveryVault instance (for snapshots)
            storage_path: Storage path
            auto_approve_trust_threshold: Trust score threshold for auto-approval (0.0-1.0)
            require_human_review_risk: Risk level that requires human review
        """
        self.trust_registry = trust_registry
        self.trust_policy = trust_policy
        self.mutation_engine = mutation_engine
        self.audit_log = audit_log
        self.recovery_vault = recovery_vault
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.auto_approve_trust_threshold = auto_approve_trust_threshold
        self.require_human_review_risk = require_human_review_risk
        
        # Thread-safe operations
        self._lock = RLock()
        
        # Review registry
        self.reviews: Dict[str, MutationReview] = {}
        
        # Statistics
        self.stats = {
            "total_reviews": 0,
            "approved": 0,
            "rejected": 0,
            "deferred": 0,
            "high_risk_count": 0
        }
        
        # Load existing reviews
        self.load()
    
    def review_mutation(
        self,
        mutation_id: str,
        author: str = "Elysia-Self",
        require_snapshot: bool = True,
        ai_validator: Optional[Any] = None  # AIMutationValidator (avoid circular import)
    ) -> MutationReview:
        """
        Review a mutation proposal.
        
        Args:
            mutation_id: Mutation proposal ID
            author: Author of the mutation
            require_snapshot: If True, require recovery snapshot before approval
            ai_validator: Optional AIMutationValidator for AI-powered validation
            
        Returns:
            MutationReview with decision
        """
        if not self.mutation_engine:
            logger.error("MutationEngine not available")
            raise ValueError("MutationEngine required for review")
        
        proposal = self.mutation_engine.get_mutation(mutation_id)
        if not proposal:
            logger.error(f"Mutation proposal {mutation_id} not found")
            raise ValueError(f"Mutation {mutation_id} not found")
        
        review_id = str(uuid.uuid4())
        
        # Assess risk level
        risk_level = self._assess_risk(proposal)
        
        # Check trust-based evaluation
        trust_score = self._get_trust_score(author)
        
        # Policy evaluation
        policy_decision = self._evaluate_policy(proposal, risk_level)
        
        # AI validation (if available)
        ai_validation_result = None
        if ai_validator:
            try:
                import asyncio
                # Try to run AI validation (sync wrapper)
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If loop is running, skip for now (would need async review method)
                        logger.debug("Event loop running, skipping AI validation")
                    else:
                        ai_validation_result = loop.run_until_complete(
                            ai_validator.validate_mutation(proposal, proposal.original_code)
                        )
                        # Add AI validation to metadata
                        if ai_validation_result:
                            proposal.metadata["ai_validation"] = ai_validation_result.to_dict()
                except RuntimeError:
                    # No event loop, create one
                    ai_validation_result = asyncio.run(
                        ai_validator.validate_mutation(proposal, proposal.original_code)
                    )
                    if ai_validation_result:
                        proposal.metadata["ai_validation"] = ai_validation_result.to_dict()
            except Exception as e:
                logger.warning(f"AI validation failed: {e}")
        
        # Generate review
        review = self._generate_review(
            review_id=review_id,
            mutation_id=mutation_id,
            proposal=proposal,
            risk_level=risk_level,
            trust_score=trust_score,
            policy_decision=policy_decision,
            author=author,
            require_snapshot=require_snapshot,
            ai_validation_result=ai_validation_result
        )
        
        # Store review
        with self._lock:
            self.reviews[review_id] = review
            self.stats["total_reviews"] += 1
            
            if review.decision == ReviewDecision.APPROVE:
                self.stats["approved"] += 1
            elif review.decision == ReviewDecision.REJECT:
                self.stats["rejected"] += 1
            elif review.decision == ReviewDecision.DEFER:
                self.stats["deferred"] += 1
            
            if risk_level == RiskLevel.HIGH or risk_level == RiskLevel.CRITICAL:
                self.stats["high_risk_count"] += 1
            
            self.save()
        
        # Log review
        if self.audit_log and AuditEventType and AuditSeverity:
            severity = AuditSeverity.WARNING if risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL] else AuditSeverity.INFO
            self.audit_log.log_event(
                event_type=AuditEventType.SECURITY_ALERT,
                description=f"Mutation review: {mutation_id} - {review.decision.value}",
                severity=severity,
                actor=author,
                metadata={
                    "review_id": review_id,
                    "mutation_id": mutation_id,
                    "decision": review.decision.value,
                    "risk_level": risk_level.value,
                    "confidence": review.confidence
                }
            )
        
        # Create recovery snapshot if approved and required
        if review.decision == ReviewDecision.APPROVE and require_snapshot and self.recovery_vault:
            try:
                snapshot_id = self.recovery_vault.create_mutation_snapshot(
                    mutation_id=mutation_id,
                    target_module=proposal.target_module,
                    description=f"Pre-application snapshot for {mutation_id}"
                )
                review.metadata["snapshot_id"] = snapshot_id
                logger.info(f"Created recovery snapshot {snapshot_id} for mutation {mutation_id}")
            except Exception as e:
                logger.error(f"Failed to create snapshot for mutation {mutation_id}: {e}")
                # Consider requiring snapshot as condition
                review.conditions.append("Recovery snapshot required before application")
        
        logger.info(f"Mutation review completed: {mutation_id} -> {review.decision.value} (risk: {risk_level.value})")
        return review
    
    def _assess_risk(self, proposal: MutationProposal) -> RiskLevel:
        """
        Assess risk level of a mutation.
        
        Args:
            proposal: Mutation proposal
            
        Returns:
            RiskLevel
        """
        risk_score = 0.0
        
        # Code size risk
        code_size = len(proposal.proposed_code)
        if code_size > 10000:
            risk_score += 0.3
        elif code_size > 5000:
            risk_score += 0.2
        
        # Target module risk
        critical_modules = ["core", "trust", "security", "memory"]
        if any(module in proposal.target_module.lower() for module in critical_modules):
            risk_score += 0.3
        
        # Mutation type risk
        high_risk_types = ["refactor", "optimization"]
        if proposal.mutation_type in high_risk_types:
            risk_score += 0.2
        
        # Confidence risk (low confidence = higher risk)
        if proposal.confidence < 0.5:
            risk_score += 0.3
        elif proposal.confidence < 0.7:
            risk_score += 0.1
        
        # Determine risk level
        if risk_score >= 0.7:
            return RiskLevel.CRITICAL
        elif risk_score >= 0.5:
            return RiskLevel.HIGH
        elif risk_score >= 0.3:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def _get_trust_score(self, author: str) -> float:
        """Get trust score for mutation author."""
        if not self.trust_registry:
            return 0.5  # Default if no trust registry
        
        try:
            node_trust = self.trust_registry.get_node_trust(author)
            if node_trust:
                # Use mutation-specific trust if available, otherwise general trust
                return node_trust.get("trust_scores", {}).get("mutation", node_trust.get("overall_trust", 0.5))
        except Exception as e:
            logger.debug(f"Error getting trust score: {e}")
        
        return 0.5  # Default
    
    def _evaluate_policy(
        self,
        proposal: MutationProposal,
        risk_level: RiskLevel
    ) -> Dict[str, Any]:
        """Evaluate mutation against trust policies."""
        if not self.trust_policy:
            return {"allowed": True, "reason": "No policy manager"}
        
        try:
            action_data = {
                "action_type": "code_mutation",
                "target": proposal.target_module,
                "mutation_type": proposal.mutation_type,
                "risk_level": risk_level.value,
                "confidence": proposal.confidence
            }
            
            policy_result = self.trust_policy.evaluate_action(action_data)
            
            return {
                "allowed": policy_result.get("decision") != "deny",
                "reason": policy_result.get("reason", ""),
                "requires_review": policy_result.get("decision") == "review"
            }
        except Exception as e:
            logger.error(f"Policy evaluation error: {e}")
            return {"allowed": True, "reason": f"Policy evaluation error: {e}"}
    
    def _generate_review(
        self,
        review_id: str,
        mutation_id: str,
        proposal: MutationProposal,
        risk_level: RiskLevel,
        trust_score: float,
        policy_decision: Dict[str, Any],
        author: str,
        require_snapshot: bool,
        ai_validation_result: Optional[Any] = None  # ValidationResult
    ) -> MutationReview:
        """Generate mutation review decision."""
        decision = ReviewDecision.DEFER
        confidence = 0.5
        reasoning = ""
        concerns = []
        conditions = []
        
        # Decision logic
        if not policy_decision.get("allowed"):
            decision = ReviewDecision.REJECT
            reasoning = f"Policy violation: {policy_decision.get('reason', 'Unknown')}"
            concerns.append("Policy violation")
            confidence = 0.9
        
        elif risk_level == RiskLevel.CRITICAL:
            decision = ReviewDecision.DEFER
            reasoning = "Critical risk level requires human review"
            concerns.append("Critical risk level")
            confidence = 0.9
        
        elif risk_level == RiskLevel.HIGH:
            if self.require_human_review_risk == RiskLevel.HIGH:
                decision = ReviewDecision.DEFER
                reasoning = "High risk level requires human review"
                concerns.append("High risk level")
            else:
                # Can auto-approve if trust is high
                if trust_score >= self.auto_approve_trust_threshold:
                    decision = ReviewDecision.APPROVE
                    reasoning = f"High risk but high trust score ({trust_score:.2f}) allows auto-approval"
                    conditions.append("High risk mitigation")
                    confidence = trust_score
                else:
                    decision = ReviewDecision.DEFER
                    reasoning = f"High risk with insufficient trust ({trust_score:.2f} < {self.auto_approve_trust_threshold})"
                    concerns.append("Insufficient trust for high-risk mutation")
        
        elif risk_level == RiskLevel.MEDIUM:
            if trust_score >= self.auto_approve_trust_threshold:
                decision = ReviewDecision.APPROVE
                reasoning = f"Medium risk, high trust ({trust_score:.2f})"
                confidence = trust_score * 0.9
            elif trust_score >= 0.7:
                decision = ReviewDecision.APPROVE
                reasoning = f"Medium risk, moderate trust ({trust_score:.2f})"
                conditions.append("Monitor after application")
                confidence = trust_score * 0.8
            else:
                decision = ReviewDecision.REQUEST_CHANGES
                reasoning = f"Medium risk with low trust ({trust_score:.2f}) - needs improvements"
                concerns.append("Low trust score")
        
        else:  # LOW risk
            if trust_score >= 0.6:
                decision = ReviewDecision.APPROVE
                reasoning = f"Low risk, sufficient trust ({trust_score:.2f})"
                confidence = trust_score * 0.95
            else:
                decision = ReviewDecision.REQUEST_CHANGES
                reasoning = f"Even low-risk mutations need minimum trust ({trust_score:.2f} < 0.6)"
                concerns.append("Below minimum trust threshold")
        
        # Add snapshot condition if required
        if require_snapshot and not self.recovery_vault:
            conditions.append("Recovery snapshot required (but vault unavailable)")
        
        # Policy review requirement
        if policy_decision.get("requires_review"):
            if decision == ReviewDecision.APPROVE:
                decision = ReviewDecision.DEFER
                reasoning += " Policy requires review."
            conditions.append("Policy review required")
        
        # AI validation impact
        metadata = {
            "trust_score": trust_score,
            "policy_decision": policy_decision,
            "author": author
        }
        
        if ai_validation_result:
            # Store AI validation in metadata
            metadata["ai_validation"] = {
                "passed": ai_validation_result.passed,
                "confidence": ai_validation_result.confidence,
                "score": ai_validation_result.score,
                "issues_count": len(ai_validation_result.issues),
                "summary": ai_validation_result.summary
            }
            
            if not ai_validation_result.passed:
                # AI found issues - add to concerns
                critical_issues = [
                    issue for issue in ai_validation_result.issues
                    if issue.severity.value == "critical"
                ]
                error_issues = [
                    issue for issue in ai_validation_result.issues
                    if issue.severity.value == "error"
                ]
                
                if critical_issues:
                    concerns.append(f"AI Validation: {len(critical_issues)} critical issues found")
                    # Force defer if critical
                    if decision == ReviewDecision.APPROVE:
                        decision = ReviewDecision.DEFER
                        reasoning += f" AI validation found {len(critical_issues)} critical issues."
                
                if error_issues:
                    concerns.append(f"AI Validation: {len(error_issues)} errors found")
                
                # Lower confidence if AI validation failed
                confidence = min(confidence, ai_validation_result.confidence)
            else:
                # AI passed - boost confidence slightly
                confidence = min(1.0, confidence * 1.1)
            
            # Add AI recommendations
            if ai_validation_result.recommendations:
                conditions.extend(ai_validation_result.recommendations)
        
        return MutationReview(
            review_id=review_id,
            mutation_id=mutation_id,
            reviewed_at=datetime.now(),
            reviewer="system",
            decision=decision,
            risk_level=risk_level,
            confidence=confidence,
            reasoning=reasoning,
            concerns=concerns,
            conditions=conditions,
            metadata=metadata
        )
    
    def get_review(self, review_id: str) -> Optional[MutationReview]:
        """Get a review by ID."""
        return self.reviews.get(review_id)
    
    def get_reviews_for_mutation(self, mutation_id: str) -> List[MutationReview]:
        """Get all reviews for a mutation."""
        return [r for r in self.reviews.values() if r.mutation_id == mutation_id]
    
    def get_latest_review(self, mutation_id: str) -> Optional[MutationReview]:
        """Get the most recent review for a mutation."""
        reviews = self.get_reviews_for_mutation(mutation_id)
        if reviews:
            reviews.sort(key=lambda r: r.reviewed_at, reverse=True)
            return reviews[0]
        return None
    
    def approve_review(self, review_id: str, human_reviewer: str = "human") -> bool:
        """Approve a deferred review (human override)."""
        review = self.reviews.get(review_id)
        if not review:
            return False
        
        if review.decision != ReviewDecision.DEFER:
            logger.warning(f"Review {review_id} not deferred, cannot approve")
            return False
        
        # Update review
        review.decision = ReviewDecision.APPROVE
        review.reviewer = human_reviewer
        review.reasoning += f" Human approved by {human_reviewer}."
        review.metadata["human_approved"] = True
        review.metadata["human_approver"] = human_reviewer
        
        with self._lock:
            self.reviews[review_id] = review
            self.stats["approved"] += 1
            self.stats["deferred"] -= 1
            self.save()
        
        logger.info(f"Review {review_id} approved by human: {human_reviewer}")
        return True
    
    def reject_review(self, review_id: str, reason: str, reviewer: str = "human") -> bool:
        """Reject a review (human override)."""
        review = self.reviews.get(review_id)
        if not review:
            return False
        
        # Update review
        review.decision = ReviewDecision.REJECT
        review.reviewer = reviewer
        review.reasoning += f" Rejected by {reviewer}: {reason}"
        review.metadata["rejection_reason"] = reason
        review.metadata["rejected_by"] = reviewer
        
        with self._lock:
            self.reviews[review_id] = review
            if review.decision != ReviewDecision.REJECT:
                self.stats["rejected"] += 1
            if review.decision == ReviewDecision.DEFER:
                self.stats["deferred"] -= 1
            self.save()
        
        logger.info(f"Review {review_id} rejected by {reviewer}")
        return True
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get review manager statistics."""
        return {
            "total_reviews": self.stats["total_reviews"],
            "approved": self.stats["approved"],
            "rejected": self.stats["rejected"],
            "deferred": self.stats["deferred"],
            "high_risk_count": self.stats["high_risk_count"],
            "approval_rate": self.stats["approved"] / max(1, self.stats["total_reviews"]),
            "auto_approve_threshold": self.auto_approve_trust_threshold
        }
    
    def save(self):
        """Save review registry."""
        with self._lock:
            data = {
                "reviews": {
                    rid: review.to_dict()
                    for rid, review in self.reviews.items()
                },
                "stats": self.stats,
                "updated_at": datetime.now().isoformat()
            }
            
            try:
                with open(self.storage_path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save mutation reviews: {e}")
    
    def load(self):
        """Load review registry."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                reviews_data = data.get("reviews", {})
                for rid, review_dict in reviews_data.items():
                    try:
                        review = MutationReview(
                            review_id=review_dict["review_id"],
                            mutation_id=review_dict["mutation_id"],
                            reviewed_at=datetime.fromisoformat(review_dict["reviewed_at"]),
                            reviewer=review_dict["reviewer"],
                            decision=ReviewDecision(review_dict["decision"]),
                            risk_level=RiskLevel(review_dict["risk_level"]),
                            confidence=review_dict["confidence"],
                            reasoning=review_dict["reasoning"],
                            concerns=review_dict.get("concerns", []),
                            conditions=review_dict.get("conditions", []),
                            metadata=review_dict.get("metadata", {})
                        )
                        self.reviews[rid] = review
                    except Exception as e:
                        logger.error(f"Failed to load review {rid}: {e}")
                
                if "stats" in data:
                    self.stats.update(data["stats"])
            
            logger.info(f"Loaded {len(self.reviews)} mutation reviews")
        except Exception as e:
            logger.error(f"Failed to load mutation reviews: {e}")


# Example usage
if __name__ == "__main__":
    # Initialize components
    trust_registry = None  # Would be provided
    trust_policy = None  # Would be provided
    mutation_engine = None  # Would be provided
    
    review_manager = MutationReviewManager(
        trust_registry=trust_registry,
        trust_policy=trust_policy,
        mutation_engine=mutation_engine,
        auto_approve_trust_threshold=0.9
    )
    
    # Review a mutation
    # review = review_manager.review_mutation("mut_123")
    # print(f"Review decision: {review.decision.value}")
    # print(f"Risk level: {review.risk_level.value}")
    # print(f"Reasoning: {review.reasoning}")

