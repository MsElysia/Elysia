# project_guardian/trust_audit_log.py
# TrustAuditLog: Security Event Logging and Audit Trails
# Based on TrustEval-Action Module Design

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from enum import Enum
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


class AuditEventType(Enum):
    """Types of audit events."""
    ACTION_DENIED = "action_denied"
    ACTION_ALLOWED = "action_allowed"
    ACTION_REVIEWED = "action_reviewed"
    ACTION_ESCALATED = "action_escalated"
    CONTENT_MODIFIED = "content_modified"
    CONTENT_BLOCKED = "content_blocked"
    POLICY_VIOLATION = "policy_violation"
    SECURITY_ALERT = "security_alert"
    POLICY_UPDATE = "policy_update"
    TRUST_CHANGE = "trust_change"


class AuditSeverity(Enum):
    """Audit event severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEntry:
    """Represents an audit log entry."""
    entry_id: str
    event_type: AuditEventType
    severity: AuditSeverity
    timestamp: datetime
    description: str
    actor: Optional[str] = None
    action: Optional[Dict[str, Any]] = None
    policy_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entry_id": self.entry_id,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
            "actor": self.actor,
            "action": self.action,
            "policy_id": self.policy_id,
            "result": self.result,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuditEntry":
        """Create AuditEntry from dictionary."""
        return cls(
            entry_id=data["entry_id"],
            event_type=AuditEventType(data["event_type"]),
            severity=AuditSeverity(data["severity"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            description=data["description"],
            actor=data.get("actor"),
            action=data.get("action"),
            policy_id=data.get("policy_id"),
            result=data.get("result"),
            metadata=data.get("metadata", {})
        )


class TrustAuditLog:
    """
    Security event logging and audit trail system.
    Tracks all security-relevant events, violations, and policy decisions.
    """
    
    def __init__(
        self,
        storage_path: str = "data/trust_audit_log.json",
        max_entries: int = 10000,
        retention_days: int = 90
    ):
        """
        Initialize TrustAuditLog.
        
        Args:
            storage_path: Path to audit log storage file
            max_entries: Maximum number of entries to keep in memory
            retention_days: Days to retain audit entries
        """
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries
        self.retention_days = retention_days
        
        # Thread-safe operations
        self._lock = Lock()
        
        # In-memory log (recent entries)
        self.entries: List[AuditEntry] = []
        
        # Statistics
        self.stats: Dict[str, int] = {
            "total_entries": 0,
            "actions_denied": 0,
            "actions_allowed": 0,
            "violations": 0,
            "escalations": 0
        }
        
        # Load existing entries
        self.load()
    
    def log_event(
        self,
        event_type: AuditEventType,
        description: str,
        severity: AuditSeverity = AuditSeverity.INFO,
        actor: Optional[str] = None,
        action: Optional[Dict[str, Any]] = None,
        policy_id: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log an audit event.
        
        Args:
            event_type: Type of event
            description: Event description
            severity: Event severity
            actor: Actor who triggered the event
            action: Action data that triggered the event
            policy_id: Related policy ID
            result: Evaluation or action result
            metadata: Additional metadata
            
        Returns:
            Entry ID
        """
        entry_id = f"audit_{datetime.now().timestamp()}_{len(self.entries)}"
        
        entry = AuditEntry(
            entry_id=entry_id,
            event_type=event_type,
            severity=severity,
            timestamp=datetime.now(),
            description=description,
            actor=actor,
            action=action,
            policy_id=policy_id,
            result=result,
            metadata=metadata or {}
        )
        
        with self._lock:
            self.entries.append(entry)
            
            # Update statistics
            self.stats["total_entries"] += 1
            
            if event_type == AuditEventType.ACTION_DENIED:
                self.stats["actions_denied"] += 1
            elif event_type == AuditEventType.ACTION_ALLOWED:
                self.stats["actions_allowed"] += 1
            elif event_type == AuditEventType.POLICY_VIOLATION:
                self.stats["violations"] += 1
            elif event_type == AuditEventType.ACTION_ESCALATED:
                self.stats["escalations"] += 1
            
            # Trim if too many entries
            if len(self.entries) > self.max_entries:
                self.entries = self.entries[-self.max_entries:]
            
            # Cleanup old entries periodically
            if len(self.entries) % 100 == 0:
                self._cleanup_old_entries()
        
        # Log to logger for critical events
        if severity == AuditSeverity.CRITICAL:
            logger.critical(f"AUDIT CRITICAL: {description}")
        elif severity == AuditSeverity.ERROR:
            logger.error(f"AUDIT ERROR: {description}")
        elif severity == AuditSeverity.WARNING:
            logger.warning(f"AUDIT WARNING: {description}")
        else:
            logger.info(f"AUDIT INFO: {description}")
        
        # Save periodically
        if len(self.entries) % 50 == 0:
            self.save()
        
        return entry_id
    
    def log_action_evaluation(
        self,
        action_data: Dict[str, Any],
        evaluation_result: Dict[str, Any],
        actor: Optional[str] = None
    ) -> str:
        """
        Log an action evaluation result.
        
        Args:
            action_data: Action data that was evaluated
            evaluation_result: Evaluation result from TrustPolicyManager
            actor: Actor who attempted the action
            
        Returns:
            Entry ID
        """
        decision = evaluation_result.get("decision", "unknown")
        policy_id = evaluation_result.get("matching_policies", [None])[0]
        severity_str = evaluation_result.get("severity", "medium")
        
        # Map decision to event type
        event_type_map = {
            "allow": AuditEventType.ACTION_ALLOWED,
            "deny": AuditEventType.ACTION_DENIED,
            "review": AuditEventType.ACTION_REVIEWED,
            "escalate": AuditEventType.ACTION_ESCALATED
        }
        
        event_type = event_type_map.get(decision, AuditEventType.ACTION_DENIED)
        
        # Map severity
        severity_map = {
            "low": AuditSeverity.INFO,
            "medium": AuditSeverity.WARNING,
            "high": AuditSeverity.ERROR,
            "critical": AuditSeverity.CRITICAL
        }
        
        severity = severity_map.get(severity_str.lower(), AuditSeverity.WARNING)
        
        description = f"Action {decision}: {evaluation_result.get('reason', 'No reason provided')}"
        
        return self.log_event(
            event_type=event_type,
            description=description,
            severity=severity,
            actor=actor,
            action=action_data,
            policy_id=policy_id,
            result=evaluation_result
        )
    
    def log_policy_violation(
        self,
        policy_id: str,
        violation_description: str,
        action_data: Optional[Dict[str, Any]] = None,
        actor: Optional[str] = None,
        severity: AuditSeverity = AuditSeverity.ERROR
    ) -> str:
        """
        Log a policy violation.
        
        Args:
            policy_id: Violated policy ID
            violation_description: Description of violation
            action_data: Action that caused violation
            actor: Actor who caused violation
            severity: Violation severity
            
        Returns:
            Entry ID
        """
        return self.log_event(
            event_type=AuditEventType.POLICY_VIOLATION,
            description=f"Policy violation ({policy_id}): {violation_description}",
            severity=severity,
            actor=actor,
            action=action_data,
            policy_id=policy_id
        )
    
    def log_content_modification(
        self,
        original_content: str,
        modified_content: str,
        reason: str,
        actor: Optional[str] = None
    ) -> str:
        """
        Log content modification (filtering/redaction).
        
        Args:
            original_content: Original content
            modified_content: Modified content
            reason: Reason for modification
            actor: Actor who triggered modification
            
        Returns:
            Entry ID
        """
        return self.log_event(
            event_type=AuditEventType.CONTENT_MODIFIED,
            description=f"Content modified: {reason}",
            severity=AuditSeverity.WARNING,
            actor=actor,
            metadata={
                "original_length": len(original_content),
                "modified_length": len(modified_content),
                "reason": reason
            }
        )
    
    def log_content_blocked(
        self,
        content: str,
        reason: str,
        actor: Optional[str] = None
    ) -> str:
        """
        Log content blocking.
        
        Args:
            content: Blocked content (may be truncated)
            reason: Reason for blocking
            actor: Actor who attempted to send content
            
        Returns:
            Entry ID
        """
        return self.log_event(
            event_type=AuditEventType.CONTENT_BLOCKED,
            description=f"Content blocked: {reason}",
            severity=AuditSeverity.WARNING,
            actor=actor,
            metadata={
                "content_length": len(content),
                "reason": reason,
                "content_preview": content[:100] if content else ""
            }
        )
    
    def query_entries(
        self,
        event_type: Optional[AuditEventType] = None,
        severity: Optional[AuditSeverity] = None,
        actor: Optional[str] = None,
        policy_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditEntry]:
        """
        Query audit log entries with filters.
        
        Args:
            event_type: Filter by event type
            severity: Filter by severity
            actor: Filter by actor
            policy_id: Filter by policy ID
            start_time: Start time filter
            end_time: End time filter
            limit: Maximum number of results
            
        Returns:
            List of matching audit entries
        """
        with self._lock:
            results = []
            
            for entry in reversed(self.entries):  # Most recent first
                # Apply filters
                if event_type and entry.event_type != event_type:
                    continue
                if severity and entry.severity != severity:
                    continue
                if actor and entry.actor != actor:
                    continue
                if policy_id and entry.policy_id != policy_id:
                    continue
                if start_time and entry.timestamp < start_time:
                    continue
                if end_time and entry.timestamp > end_time:
                    continue
                
                results.append(entry)
                
                if len(results) >= limit:
                    break
            
            return results
    
    def get_statistics(
        self,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get audit log statistics.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Statistics dictionary
        """
        cutoff = datetime.now() - timedelta(days=days)
        
        with self._lock:
            recent_entries = [e for e in self.entries if e.timestamp >= cutoff]
            
            by_type = {}
            by_severity = {}
            by_actor = {}
            
            for entry in recent_entries:
                # By type
                etype = entry.event_type.value
                by_type[etype] = by_type.get(etype, 0) + 1
                
                # By severity
                sev = entry.severity.value
                by_severity[sev] = by_severity.get(sev, 0) + 1
                
                # By actor
                if entry.actor:
                    by_actor[entry.actor] = by_actor.get(entry.actor, 0) + 1
            
            return {
                "total_entries": self.stats["total_entries"],
                "entries_in_period": len(recent_entries),
                "period_days": days,
                "actions_allowed": self.stats["actions_allowed"],
                "actions_denied": self.stats["actions_denied"],
                "violations": self.stats["violations"],
                "escalations": self.stats["escalations"],
                "by_event_type": by_type,
                "by_severity": by_severity,
                "by_actor": by_actor,
                "oldest_entry": self.entries[0].timestamp.isoformat() if self.entries else None,
                "newest_entry": self.entries[-1].timestamp.isoformat() if self.entries else None
            }
    
    def get_recent_violations(
        self,
        limit: int = 10
    ) -> List[AuditEntry]:
        """Get recent policy violations."""
        return self.query_entries(
            event_type=AuditEventType.POLICY_VIOLATION,
            limit=limit
        )
    
    def get_recent_escalations(
        self,
        limit: int = 10
    ) -> List[AuditEntry]:
        """Get recent escalations."""
        return self.query_entries(
            event_type=AuditEventType.ACTION_ESCALATED,
            limit=limit
        )
    
    def _cleanup_old_entries(self):
        """Remove entries older than retention period."""
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        
        with self._lock:
            original_count = len(self.entries)
            self.entries = [e for e in self.entries if e.timestamp >= cutoff]
            removed = original_count - len(self.entries)
            
            if removed > 0:
                logger.debug(f"Cleaned up {removed} old audit entries")
    
    def save(self):
        """Save audit log to disk."""
        with self._lock:
            # Save last 1000 entries
            entries_to_save = self.entries[-1000:] if len(self.entries) > 1000 else self.entries
            
            data = {
                "entries": [entry.to_dict() for entry in entries_to_save],
                "stats": self.stats,
                "updated_at": datetime.now().isoformat()
            }
            
            try:
                with open(self.storage_path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save audit log: {e}")
    
    def load(self):
        """Load audit log from disk."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                entries_data = data.get("entries", [])
                
                for entry_dict in entries_data:
                    try:
                        entry = AuditEntry.from_dict(entry_dict)
                        self.entries.append(entry)
                    except Exception as e:
                        logger.error(f"Failed to load audit entry: {e}")
                
                # Load stats if available
                if "stats" in data:
                    self.stats.update(data["stats"])
            
            logger.info(f"Loaded {len(self.entries)} audit entries")
            
            # Cleanup old entries on load
            self._cleanup_old_entries()
            
        except Exception as e:
            logger.error(f"Failed to load audit log: {e}")


# Example usage
if __name__ == "__main__":
    # Create audit log
    audit_log = TrustAuditLog()
    
    # Log an action evaluation
    audit_log.log_action_evaluation(
        action_data={"type": "mutation", "target": "code.py"},
        evaluation_result={
            "decision": "deny",
            "severity": "high",
            "reason": "Potentially dangerous code pattern"
        },
        actor="module_xyz"
    )
    
    # Get statistics
    stats = audit_log.get_statistics(days=7)
    print(f"Audit statistics: {stats}")
    
    # Query recent violations
    violations = audit_log.get_recent_violations(limit=5)
    print(f"Recent violations: {len(violations)}")
