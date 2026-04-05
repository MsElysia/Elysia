# project_guardian/mutation_router.py
# MutationRouter: Decision Routing for Mutations
# Routes mutations based on review decisions to appropriate handlers

import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from threading import Lock
from enum import Enum
from dataclasses import dataclass, field

try:
    from .mutation_review_manager import MutationReviewManager, ReviewDecision, MutationReview
    from .mutation_engine import MutationEngine, MutationProposal, MutationStatus
    from .trust_audit_log import TrustAuditLog, AuditEventType, AuditSeverity
except ImportError:
    from mutation_review_manager import MutationReviewManager, ReviewDecision, MutationReview
    from mutation_engine import MutationEngine, MutationProposal, MutationStatus
    try:
        from trust_audit_log import TrustAuditLog, AuditEventType, AuditSeverity
    except ImportError:
        TrustAuditLog = None
        AuditEventType = None
        AuditSeverity = None

logger = logging.getLogger(__name__)


class RouteStatus(Enum):
    """Route status."""
    PENDING = "pending"
    ROUTED = "routed"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class MutationRoute:
    """Represents a mutation route."""
    route_id: str
    mutation_id: str
    review_id: str
    route_status: RouteStatus
    target_handler: str  # "auto_apply", "human_review", "reject", "request_changes"
    routed_at: datetime
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class MutationRouter:
    """
    Routes mutations based on review decisions.
    Determines next steps for mutation proposals.
    """
    
    def __init__(
        self,
        review_manager: MutationReviewManager,
        mutation_engine: MutationEngine,
        audit_log: Optional[TrustAuditLog] = None
    ):
        """
        Initialize MutationRouter.
        
        Args:
            review_manager: MutationReviewManager instance
            mutation_engine: MutationEngine instance
            audit_log: TrustAuditLog instance
        """
        self.review_manager = review_manager
        self.mutation_engine = mutation_engine
        self.audit_log = audit_log
        
        # Thread-safe operations
        self._lock = Lock()
        
        # Route registry
        self.routes: Dict[str, MutationRoute] = {}
        
        # Handler registry
        self.handlers: Dict[str, callable] = {
            "auto_apply": self._handle_auto_apply,
            "human_review": self._handle_human_review,
            "reject": self._handle_reject,
            "request_changes": self._handle_request_changes
        }
    
    def route_mutation(
        self,
        mutation_id: str,
        review_id: Optional[str] = None
    ) -> MutationRoute:
        """
        Route a mutation based on review decision.
        
        Args:
            mutation_id: Mutation proposal ID
            review_id: Optional review ID (if None, uses latest review)
            
        Returns:
            MutationRoute
        """
        # Get or create review
        if review_id:
            review = self.review_manager.get_review(review_id)
        else:
            review = self.review_manager.get_latest_review(mutation_id)
        
        if not review:
            # Create new review
            review = self.review_manager.review_mutation(mutation_id)
        
        # Determine route based on review decision
        route_id = f"route_{mutation_id}_{review.review_id}"
        
        target_handler = self._determine_handler(review)
        
        route = MutationRoute(
            route_id=route_id,
            mutation_id=mutation_id,
            review_id=review.review_id,
            route_status=RouteStatus.PENDING,
            target_handler=target_handler,
            routed_at=datetime.now()
        )
        
        with self._lock:
            self.routes[route_id] = route
            route.route_status = RouteStatus.ROUTED
        
        # Execute route
        try:
            handler = self.handlers.get(target_handler)
            if handler:
                result = handler(mutation_id, review)
                route.result = result
                route.completed_at = datetime.now()
                route.route_status = RouteStatus.COMPLETED
            else:
                logger.error(f"Unknown handler: {target_handler}")
                route.route_status = RouteStatus.FAILED
                route.result = {"error": f"Unknown handler: {target_handler}"}
        except Exception as e:
            logger.error(f"Route execution failed: {e}", exc_info=True)
            route.route_status = RouteStatus.FAILED
            route.result = {"error": str(e)}
        
        logger.info(f"Mutation {mutation_id} routed to: {target_handler}")
        return route
    
    def _determine_handler(self, review: MutationReview) -> str:
        """
        Determine handler based on review decision.
        
        Args:
            review: Mutation review
            
        Returns:
            Handler name
        """
        if review.decision == ReviewDecision.APPROVE:
            return "auto_apply"
        elif review.decision == ReviewDecision.REJECT:
            return "reject"
        elif review.decision == ReviewDecision.DEFER:
            return "human_review"
        elif review.decision == ReviewDecision.REQUEST_CHANGES:
            return "request_changes"
        else:
            return "human_review"  # Default to human review
    
    def _handle_auto_apply(
        self,
        mutation_id: str,
        review: MutationReview
    ) -> Dict[str, Any]:
        """Handle auto-approval - apply mutation automatically."""
        logger.info(f"Auto-applying mutation: {mutation_id}")
        
        # Check if mutation is already applied
        proposal = self.mutation_engine.get_mutation(mutation_id)
        if not proposal:
            return {"success": False, "error": "Mutation not found"}
        
        if proposal.status == MutationStatus.APPLIED:
            return {"success": True, "message": "Mutation already applied"}
        
        # Approve and apply
        approved = self.mutation_engine.approve_proposal(mutation_id, reviewer="auto_router")
        if not approved:
            return {"success": False, "error": "Failed to approve mutation"}
        
        applied = self.mutation_engine.apply_mutation(mutation_id)
        
        if applied:
            # Log success
            if self.audit_log and AuditEventType and AuditSeverity:
                self.audit_log.log_event(
                    event_type=AuditEventType.SECURITY_ALERT,
                    description=f"Mutation auto-applied: {mutation_id}",
                    severity=AuditSeverity.INFO,
                    metadata={
                        "mutation_id": mutation_id,
                        "review_id": review.review_id,
                        "risk_level": review.risk_level.value
                    }
                )
            
            return {
                "success": True,
                "message": "Mutation applied successfully",
                "mutation_id": mutation_id,
                "snapshot_id": review.metadata.get("snapshot_id")
            }
        else:
            return {"success": False, "error": "Failed to apply mutation"}
    
    def _handle_human_review(
        self,
        mutation_id: str,
        review: MutationReview
    ) -> Dict[str, Any]:
        """Handle human review requirement - queue for human attention."""
        logger.info(f"Mutation {mutation_id} requires human review")
        
        # Update mutation status to REVIEWING
        proposal = self.mutation_engine.get_mutation(mutation_id)
        if proposal:
            proposal.status = MutationStatus.REVIEWING
        
        # Log for human review
        if self.audit_log and AuditEventType and AuditSeverity:
            self.audit_log.log_event(
                event_type=AuditEventType.SECURITY_ALERT,
                description=f"Mutation requires human review: {mutation_id}",
                severity=AuditSeverity.WARNING,
                metadata={
                    "mutation_id": mutation_id,
                    "review_id": review.review_id,
                    "risk_level": review.risk_level.value,
                    "concerns": review.concerns,
                    "reasoning": review.reasoning
                }
            )
        
        return {
            "success": True,
            "message": "Queued for human review",
            "mutation_id": mutation_id,
            "review_id": review.review_id,
            "requires_human": True,
            "concerns": review.concerns,
            "reasoning": review.reasoning
        }
    
    def _handle_reject(
        self,
        mutation_id: str,
        review: MutationReview
    ) -> Dict[str, Any]:
        """Handle rejection - reject mutation."""
        logger.info(f"Rejecting mutation: {mutation_id}")
        
        # Update mutation status to rejected
        mutation = self.mutation_engine.get_mutation(mutation_id)
        if mutation:
            mutation.status = MutationStatus.REJECTED
        
        if mutation:
            if self.audit_log and AuditEventType and AuditSeverity:
                self.audit_log.log_event(
                    event_type=AuditEventType.SECURITY_ALERT,
                    description=f"Mutation rejected: {mutation_id}",
                    severity=AuditSeverity.INFO,
                    metadata={
                        "mutation_id": mutation_id,
                        "review_id": review.review_id,
                        "reason": review.reasoning
                    }
                )
            
            return {
                "success": True,
                "message": "Mutation rejected",
                "mutation_id": mutation_id,
                "reason": review.reasoning
            }
        else:
            return {"success": False, "error": "Failed to reject mutation"}
    
    def _handle_request_changes(
        self,
        mutation_id: str,
        review: MutationReview
    ) -> Dict[str, Any]:
        """Handle request changes - return feedback for improvement."""
        logger.info(f"Requesting changes for mutation: {mutation_id}")
        
        # Update mutation with feedback
        proposal = self.mutation_engine.get_mutation(mutation_id)
        if proposal:
            proposal.metadata["change_request"] = {
                "concerns": review.concerns,
                "conditions": review.conditions,
                "suggested_improvements": review.reasoning
            }
        
        return {
            "success": True,
            "message": "Changes requested",
            "mutation_id": mutation_id,
            "concerns": review.concerns,
            "conditions": review.conditions,
            "suggestions": review.reasoning
        }
    
    def get_route(self, route_id: str) -> Optional[MutationRoute]:
        """Get a route by ID."""
        return self.routes.get(route_id)
    
    def get_routes_for_mutation(self, mutation_id: str) -> List[MutationRoute]:
        """Get all routes for a mutation."""
        return [r for r in self.routes.values() if r.mutation_id == mutation_id]
    
    def get_pending_human_reviews(self) -> List[MutationRoute]:
        """Get mutations pending human review."""
        return [
            r for r in self.routes.values()
            if r.target_handler == "human_review"
            and r.route_status == RouteStatus.COMPLETED
        ]


# Example usage
if __name__ == "__main__":
    # Initialize components
    review_manager = None  # Would be provided
    mutation_engine = None  # Would be provided
    
    router = MutationRouter(
        review_manager=review_manager,
        mutation_engine=mutation_engine
    )
    
    # Route a mutation
    # route = router.route_mutation("mut_123")
    # print(f"Route status: {route.route_status.value}")
    # print(f"Handler: {route.target_handler}")

