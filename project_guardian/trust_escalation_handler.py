# project_guardian/trust_escalation_handler.py
# TrustEscalationHandler: Review Queue for Escalated Actions
# Based on TrustEval-Action Module Design

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from enum import Enum
from dataclasses import dataclass, field, asdict
import uuid

try:
    from .trust_audit_log import TrustAuditLog, AuditEventType, AuditSeverity
except ImportError:
    from trust_audit_log import TrustAuditLog, AuditEventType, AuditSeverity

logger = logging.getLogger(__name__)


class EscalationStatus(Enum):
    """Escalation status states."""
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class EscalationPriority(Enum):
    """Escalation priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class EscalationRequest:
    """Represents an escalation request for review."""
    escalation_id: str
    action_data: Dict[str, Any]
    evaluation_result: Dict[str, Any]
    policy_id: Optional[str]
    severity: str
    priority: EscalationPriority
    actor: Optional[str]
    timestamp: datetime
    status: EscalationStatus = EscalationStatus.PENDING
    review_notes: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    expiration_time: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "escalation_id": self.escalation_id,
            "action_data": self.action_data,
            "evaluation_result": self.evaluation_result,
            "policy_id": self.policy_id,
            "severity": self.severity,
            "priority": self.priority.value,
            "actor": self.actor,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status.value,
            "review_notes": self.review_notes,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "expiration_time": self.expiration_time.isoformat() if self.expiration_time else None,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EscalationRequest":
        """Create EscalationRequest from dictionary."""
        return cls(
            escalation_id=data["escalation_id"],
            action_data=data["action_data"],
            evaluation_result=data["evaluation_result"],
            policy_id=data.get("policy_id"),
            severity=data["severity"],
            priority=EscalationPriority(data["priority"]),
            actor=data.get("actor"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            status=EscalationStatus(data.get("status", "pending")),
            review_notes=data.get("review_notes"),
            reviewed_by=data.get("reviewed_by"),
            reviewed_at=datetime.fromisoformat(data["reviewed_at"]) if data.get("reviewed_at") else None,
            expiration_time=datetime.fromisoformat(data["expiration_time"]) if data.get("expiration_time") else None,
            metadata=data.get("metadata", {})
        )


class TrustEscalationHandler:
    """
    Manages review queue for escalated actions.
    Handles pending reviews, priority management, and review workflows.
    """
    
    def __init__(
        self,
        audit_log: Optional[TrustAuditLog] = None,
        storage_path: str = "data/escalation_queue.json",
        default_expiration_hours: int = 24,
        auto_expire: bool = True
    ):
        """
        Initialize TrustEscalationHandler.
        
        Args:
            audit_log: Optional TrustAuditLog instance for logging
            storage_path: Path to escalation queue storage
            default_expiration_hours: Default expiration time in hours
            auto_expire: If True, automatically expire old requests
        """
        self.audit_log = audit_log
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.default_expiration_hours = default_expiration_hours
        self.auto_expire = auto_expire
        
        # Thread-safe operations
        self._lock = Lock()
        
        # Escalation queue
        self.escalations: Dict[str, EscalationRequest] = {}
        
        # Statistics
        self.stats: Dict[str, int] = {
            "total_escalations": 0,
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "dismissed": 0,
            "expired": 0
        }
        
        # Load existing escalations
        self.load()
    
    def escalate_action(
        self,
        action_data: Dict[str, Any],
        evaluation_result: Dict[str, Any],
        policy_id: Optional[str] = None,
        actor: Optional[str] = None,
        expiration_hours: Optional[int] = None
    ) -> str:
        """
        Escalate an action for review.
        
        Args:
            action_data: Action data that was evaluated
            evaluation_result: Evaluation result from TrustPolicyManager
            policy_id: Policy ID that triggered escalation
            actor: Actor who attempted the action
            expiration_hours: Custom expiration time (uses default if None)
            
        Returns:
            Escalation ID
        """
        escalation_id = str(uuid.uuid4())
        
        # Determine priority from severity
        severity_str = evaluation_result.get("severity", "medium").lower()
        priority_map = {
            "critical": EscalationPriority.CRITICAL,
            "high": EscalationPriority.HIGH,
            "medium": EscalationPriority.MEDIUM,
            "low": EscalationPriority.LOW
        }
        priority = priority_map.get(severity_str, EscalationPriority.MEDIUM)
        
        # Calculate expiration
        expiration_hours = expiration_hours or self.default_expiration_hours
        expiration_time = datetime.now() + timedelta(hours=expiration_hours)
        
        escalation = EscalationRequest(
            escalation_id=escalation_id,
            action_data=action_data,
            evaluation_result=evaluation_result,
            policy_id=policy_id,
            severity=severity_str,
            priority=priority,
            actor=actor,
            timestamp=datetime.now(),
            expiration_time=expiration_time
        )
        
        with self._lock:
            self.escalations[escalation_id] = escalation
            self.stats["total_escalations"] += 1
            self.stats["pending"] += 1
            self.save()
        
        # Log escalation
        if self.audit_log:
            self.audit_log.log_event(
                event_type=AuditEventType.ACTION_ESCALATED,
                description=f"Action escalated for review: {escalation_id}",
                severity=AuditSeverity.WARNING if priority != EscalationPriority.CRITICAL else AuditSeverity.ERROR,
                actor=actor,
                action=action_data,
                policy_id=policy_id,
                result=evaluation_result,
                metadata={"escalation_id": escalation_id, "priority": priority.value}
            )
        
        logger.info(f"Action escalated: {escalation_id} (priority: {priority.value})")
        return escalation_id
    
    def get_pending_reviews(
        self,
        priority: Optional[EscalationPriority] = None,
        limit: int = 50
    ) -> List[EscalationRequest]:
        """
        Get pending review requests, sorted by priority.
        
        Args:
            priority: Filter by priority level
            limit: Maximum number of results
            
        Returns:
            List of pending escalation requests
        """
        # Cleanup expired if auto-expire enabled
        if self.auto_expire:
            self._expire_old_requests()
        
        with self._lock:
            pending = [
                e for e in self.escalations.values()
                if e.status == EscalationStatus.PENDING
            ]
            
            # Filter by priority if specified
            if priority:
                pending = [e for e in pending if e.priority == priority]
            
            # Sort by priority (CRITICAL first) and timestamp (oldest first)
            priority_order = {
                EscalationPriority.CRITICAL: 4,
                EscalationPriority.HIGH: 3,
                EscalationPriority.MEDIUM: 2,
                EscalationPriority.LOW: 1
            }
            
            pending.sort(
                key=lambda e: (
                    priority_order.get(e.priority, 0),
                    e.timestamp
                ),
                reverse=True
            )
            
            return pending[:limit]
    
    def review_escalation(
        self,
        escalation_id: str,
        decision: str,
        reviewer: str,
        notes: Optional[str] = None
    ) -> bool:
        """
        Review and decide on an escalation.
        
        Args:
            escalation_id: Escalation ID to review
            decision: Decision ("approve", "reject", "dismiss")
            reviewer: Reviewer identifier
            notes: Optional review notes
            
        Returns:
            True if review successful
        """
        with self._lock:
            escalation = self.escalations.get(escalation_id)
            if not escalation:
                logger.error(f"Escalation {escalation_id} not found")
                return False
            
            if escalation.status != EscalationStatus.PENDING:
                logger.warning(f"Escalation {escalation_id} already reviewed (status: {escalation.status.value})")
                return False
            
            # Update status
            decision_lower = decision.lower()
            if decision_lower == "approve":
                escalation.status = EscalationStatus.APPROVED
                self.stats["pending"] -= 1
                self.stats["approved"] += 1
            elif decision_lower == "reject":
                escalation.status = EscalationStatus.REJECTED
                self.stats["pending"] -= 1
                self.stats["rejected"] += 1
            elif decision_lower == "dismiss":
                escalation.status = EscalationStatus.DISMISSED
                self.stats["pending"] -= 1
                self.stats["dismissed"] += 1
            else:
                logger.error(f"Invalid decision: {decision}")
                return False
            
            escalation.review_notes = notes
            escalation.reviewed_by = reviewer
            escalation.reviewed_at = datetime.now()
            
            self.save()
        
        # Log review decision
        if self.audit_log:
            severity = AuditSeverity.INFO if decision_lower == "approve" else AuditSeverity.WARNING
            self.audit_log.log_event(
                event_type=AuditEventType.ACTION_REVIEWED,
                description=f"Escalation reviewed: {decision} - {escalation_id}",
                severity=severity,
                actor=reviewer,
                action=escalation.action_data,
                policy_id=escalation.policy_id,
                result={
                    "decision": decision,
                    "review_notes": notes,
                    "escalation_id": escalation_id
                }
            )
        
        logger.info(f"Escalation {escalation_id} reviewed: {decision} by {reviewer}")
        return True
    
    def approve_escalation(
        self,
        escalation_id: str,
        reviewer: str,
        notes: Optional[str] = None
    ) -> bool:
        """Approve an escalated action."""
        return self.review_escalation(escalation_id, "approve", reviewer, notes)
    
    def reject_escalation(
        self,
        escalation_id: str,
        reviewer: str,
        notes: Optional[str] = None
    ) -> bool:
        """Reject an escalated action."""
        return self.review_escalation(escalation_id, "reject", reviewer, notes)
    
    def dismiss_escalation(
        self,
        escalation_id: str,
        reviewer: str,
        notes: Optional[str] = None
    ) -> bool:
        """Dismiss an escalated action (not applicable)."""
        return self.review_escalation(escalation_id, "dismiss", reviewer, notes)
    
    def get_escalation(self, escalation_id: str) -> Optional[EscalationRequest]:
        """Get an escalation request by ID."""
        return self.escalations.get(escalation_id)
    
    def get_escalation_statistics(self) -> Dict[str, Any]:
        """
        Get escalation queue statistics.
        
        Returns:
            Statistics dictionary
        """
        with self._lock:
            by_priority = {}
            by_status = {}
            
            for escalation in self.escalations.values():
                # By priority
                priority = escalation.priority.value
                by_priority[priority] = by_priority.get(priority, 0) + 1
                
                # By status
                status = escalation.status.value
                by_status[status] = by_status.get(status, 0) + 1
            
            oldest_pending = None
            for escalation in self.escalations.values():
                if escalation.status == EscalationStatus.PENDING:
                    if oldest_pending is None or escalation.timestamp < oldest_pending:
                        oldest_pending = escalation.timestamp
            
            return {
                "total_escalations": self.stats["total_escalations"],
                "pending": self.stats["pending"],
                "approved": self.stats["approved"],
                "rejected": self.stats["rejected"],
                "dismissed": self.stats["dismissed"],
                "expired": self.stats["expired"],
                "by_priority": by_priority,
                "by_status": by_status,
                "oldest_pending": oldest_pending.isoformat() if oldest_pending else None
            }
    
    def _expire_old_requests(self):
        """Expire old escalation requests."""
        now = datetime.now()
        expired_count = 0
        
        with self._lock:
            for escalation in list(self.escalations.values()):
                if (
                    escalation.status == EscalationStatus.PENDING and
                    escalation.expiration_time and
                    now >= escalation.expiration_time
                ):
                    escalation.status = EscalationStatus.EXPIRED
                    self.stats["pending"] -= 1
                    self.stats["expired"] += 1
                    expired_count += 1
            
            if expired_count > 0:
                self.save()
                logger.info(f"Expired {expired_count} escalation requests")
    
    def clear_resolved(self, days: int = 7) -> int:
        """
        Clear resolved escalations older than specified days.
        
        Args:
            days: Days to keep resolved escalations
            
        Returns:
            Number of escalations cleared
        """
        cutoff = datetime.now() - timedelta(days=days)
        
        with self._lock:
            to_remove = []
            
            for escalation_id, escalation in self.escalations.items():
                if (
                    escalation.status in [
                        EscalationStatus.APPROVED,
                        EscalationStatus.REJECTED,
                        EscalationStatus.DISMISSED,
                        EscalationStatus.EXPIRED
                    ] and
                    escalation.reviewed_at and
                    escalation.reviewed_at < cutoff
                ):
                    to_remove.append(escalation_id)
            
            for escalation_id in to_remove:
                del self.escalations[escalation_id]
            
            if to_remove:
                self.save()
                logger.info(f"Cleared {len(to_remove)} resolved escalations")
            
            return len(to_remove)
    
    def save(self):
        """Save escalation queue to disk."""
        with self._lock:
            data = {
                "escalations": {
                    eid: escalation.to_dict()
                    for eid, escalation in self.escalations.items()
                },
                "stats": self.stats,
                "updated_at": datetime.now().isoformat()
            }
            
            try:
                with open(self.storage_path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save escalation queue: {e}")
    
    def load(self):
        """Load escalation queue from disk."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                escalations_data = data.get("escalations", {})
                
                for escalation_id, escalation_dict in escalations_data.items():
                    try:
                        escalation = EscalationRequest.from_dict(escalation_dict)
                        self.escalations[escalation_id] = escalation
                    except Exception as e:
                        logger.error(f"Failed to load escalation {escalation_id}: {e}")
                
                # Load stats if available
                if "stats" in data:
                    self.stats.update(data["stats"])
            
            logger.info(f"Loaded {len(self.escalations)} escalations")
            
            # Expire old requests on load
            if self.auto_expire:
                self._expire_old_requests()
            
        except Exception as e:
            logger.error(f"Failed to load escalation queue: {e}")


# Example usage
if __name__ == "__main__":
    # Create escalation handler
    handler = TrustEscalationHandler()
    
    # Escalate an action
    escalation_id = handler.escalate_action(
        action_data={"type": "mutation", "target": "critical_code.py"},
        evaluation_result={
            "decision": "escalate",
            "severity": "critical",
            "reason": "Critical code modification requires review"
        },
        policy_id="review_mutations",
        actor="module_xyz"
    )
    
    # Get pending reviews
    pending = handler.get_pending_reviews()
    print(f"Pending reviews: {len(pending)}")
    
    # Review escalation
    handler.approve_escalation(
        escalation_id,
        reviewer="human_admin",
        notes="Code review passed, mutation safe"
    )
    
    # Get statistics
    stats = handler.get_escalation_statistics()
    print(f"Statistics: {stats}")
