# project_guardian/trust_policy_manager.py
# TrustPolicyManager: Trust Policy and Rule Management
# Based on TrustEval-Action Module Design

import logging
import json
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
from pathlib import Path
from threading import Lock
from enum import Enum
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


class PolicyAction(Enum):
    """Policy actions."""
    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"
    ESCALATE = "escalate"


class PolicySeverity(Enum):
    """Policy severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TrustPolicy:
    """Represents a trust policy rule."""
    policy_id: str
    name: str
    description: str
    action: PolicyAction
    severity: PolicySeverity
    conditions: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    priority: int = 5  # 1-10, higher = checked first
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "policy_id": self.policy_id,
            "name": self.name,
            "description": self.description,
            "action": self.action.value,
            "severity": self.severity.value,
            "conditions": self.conditions,
            "enabled": self.enabled,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrustPolicy":
        """Create TrustPolicy from dictionary."""
        return cls(
            policy_id=data["policy_id"],
            name=data["name"],
            description=data["description"],
            action=PolicyAction(data["action"]),
            severity=PolicySeverity(data["severity"]),
            conditions=data.get("conditions", {}),
            enabled=data.get("enabled", True),
            priority=data.get("priority", 5),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            updated_at=datetime.fromisoformat(data.get("updated_at", datetime.now().isoformat())),
            metadata=data.get("metadata", {})
        )


class TrustPolicyManager:
    """
    Manages trust policies and rules for system safety.
    Implements Default Deny, Minimal Privilege, and Sandboxing patterns.
    """
    
    def __init__(
        self,
        storage_path: str = "data/trust_policies.json",
        default_deny: bool = True,
        config_path: Optional[str] = None,
    ):
        """
        Initialize TrustPolicyManager.
        
        Args:
            storage_path: Path to policy storage file
            default_deny: If True, default to deny when no policy matches
            config_path: Deprecated alias for storage_path (tests / legacy callers)
        """
        if config_path is not None:
            storage_path = config_path
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.default_deny = default_deny
        
        # Thread-safe operations
        self._lock = Lock()
        
        # Policy storage
        self.policies: Dict[str, TrustPolicy] = {}
        
        # Policy groups by category
        self.policy_groups: Dict[str, List[str]] = {}
        
        # Load policies
        self.load()
        
        # Initialize default policies if none exist
        if not self.policies:
            self._initialize_default_policies()

    @property
    def current_policy(self) -> Dict[str, Any]:
        """
        Nested policy dict expected by TrustEval-Action (:mod:`trust_eval_action`).
        Separate from dataclass policies in ``self.policies`` — provides stable keys
        for network/filesystem/admin/database checks.
        """
        return {
            "network": {
                "blocked_ip_ranges": [],
                "allowed_domains": [],
            },
            "filesystem": {
                "restricted_paths": [],
                "critical_directories": [],
                "dangerous_extensions": [],
            },
            "users": {
                "system": {"roles": ["admin", "operator"]},
            },
            "admin": {
                "blocked_commands": [],
                "time_restrictions": {},
            },
            "database": {
                "restricted_databases": [],
            },
        }

    def load_policy(self) -> None:
        """Alias for :meth:`load` (TrustEval-Action ``refresh_policy``)."""
        self.load()
    
    def _initialize_default_policies(self):
        """Initialize default security policies."""
        logger.info("Initializing default trust policies")
        
        default_policies = [
            {
                "policy_id": "default_deny_all",
                "name": "Default Deny All",
                "description": "Deny all actions by default unless explicitly allowed",
                "action": PolicyAction.DENY,
                "severity": PolicySeverity.CRITICAL,
                "priority": 1,
                "conditions": {"default": True}
            },
            {
                "policy_id": "allow_trusted_modules",
                "name": "Allow Trusted Modules",
                "description": "Allow actions from modules with high trust scores",
                "action": PolicyAction.ALLOW,
                "severity": PolicySeverity.LOW,
                "priority": 8,
                "conditions": {"trust_score": {"min": 0.8}}
            },
            {
                "policy_id": "review_mutations",
                "name": "Review Code Mutations",
                "description": "Require review for code mutation operations",
                "action": PolicyAction.REVIEW,
                "severity": PolicySeverity.HIGH,
                "priority": 7,
                "conditions": {"action_type": "mutation"}
            },
            {
                "policy_id": "escalate_critical",
                "name": "Escalate Critical Actions",
                "description": "Escalate critical security actions for human review",
                "action": PolicyAction.ESCALATE,
                "severity": PolicySeverity.CRITICAL,
                "priority": 9,
                "conditions": {"severity": "critical", "requires_human": True}
            }
        ]
        
        for policy_data in default_policies:
            policy = TrustPolicy(
                policy_id=policy_data["policy_id"],
                name=policy_data["name"],
                description=policy_data["description"],
                action=policy_data["action"],
                severity=policy_data["severity"],
                conditions=policy_data.get("conditions", {}),
                priority=policy_data.get("priority", 5)
            )
            self.policies[policy.policy_id] = policy
        
        self.save()
        logger.info(f"Initialized {len(default_policies)} default policies")
    
    def add_policy(
        self,
        policy_id: str,
        name: str,
        description: str,
        action: PolicyAction,
        severity: PolicySeverity,
        conditions: Optional[Dict[str, Any]] = None,
        priority: int = 5,
        enabled: bool = True
    ) -> bool:
        """
        Add a new trust policy.
        
        Args:
            policy_id: Unique policy identifier
            name: Policy name
            description: Policy description
            action: Policy action
            severity: Policy severity
            conditions: Policy conditions
            priority: Policy priority (1-10)
            enabled: Whether policy is enabled
            
        Returns:
            True if added successfully
        """
        with self._lock:
            if policy_id in self.policies:
                logger.warning(f"Policy {policy_id} already exists, updating")
            
            policy = TrustPolicy(
                policy_id=policy_id,
                name=name,
                description=description,
                action=action,
                severity=severity,
                conditions=conditions or {},
                priority=priority,
                enabled=enabled
            )
            
            self.policies[policy_id] = policy
            self.save()
            
            logger.info(f"Added policy: {name} ({policy_id})")
            return True
    
    def remove_policy(self, policy_id: str) -> bool:
        """
        Remove a policy.
        
        Args:
            policy_id: Policy ID
            
        Returns:
            True if removed successfully
        """
        with self._lock:
            if policy_id not in self.policies:
                logger.warning(f"Policy {policy_id} not found")
                return False
            
            # Don't allow removing default deny policy
            if policy_id == "default_deny_all" and self.default_deny:
                logger.error("Cannot remove default_deny_all policy")
                return False
            
            del self.policies[policy_id]
            self.save()
            
            logger.info(f"Removed policy: {policy_id}")
            return True
    
    def update_policy(
        self,
        policy_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        Update an existing policy.
        
        Args:
            policy_id: Policy ID
            updates: Update dictionary
            
        Returns:
            True if updated successfully
        """
        with self._lock:
            if policy_id not in self.policies:
                logger.error(f"Policy {policy_id} not found")
                return False
            
            policy = self.policies[policy_id]
            
            # Update fields
            if "name" in updates:
                policy.name = updates["name"]
            if "description" in updates:
                policy.description = updates["description"]
            if "action" in updates:
                policy.action = PolicyAction(updates["action"])
            if "severity" in updates:
                policy.severity = PolicySeverity(updates["severity"])
            if "conditions" in updates:
                policy.conditions.update(updates["conditions"])
            if "priority" in updates:
                policy.priority = updates["priority"]
            if "enabled" in updates:
                policy.enabled = updates["enabled"]
            if "metadata" in updates:
                policy.metadata.update(updates["metadata"])
            
            policy.updated_at = datetime.now()
            self.save()
            
            logger.info(f"Updated policy: {policy_id}")
            return True
    
    def evaluate_action(
        self,
        action_data: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate an action against all policies.
        Returns policy decision and matching policies.
        
        Args:
            action_data: Action data to evaluate
            context: Optional evaluation context
            
        Returns:
            Evaluation result dictionary
        """
        context = context or {}
        matching_policies = []
        
        # Get enabled policies sorted by priority (highest first)
        enabled_policies = [
            p for p in self.policies.values()
            if p.enabled
        ]
        enabled_policies.sort(key=lambda p: p.priority, reverse=True)
        
        # Evaluate against each policy
        for policy in enabled_policies:
            if self._matches_policy(policy, action_data, context):
                matching_policies.append(policy)
                
                # Return immediately if deny or escalate (highest priority)
                if policy.action == PolicyAction.DENY:
                    return {
                        "decision": "deny",
                        "action": PolicyAction.DENY,
                        "severity": policy.severity,
                        "matching_policies": [policy.policy_id],
                        "policy_name": policy.name,
                        "reason": policy.description
                    }
                elif policy.action == PolicyAction.ESCALATE:
                    return {
                        "decision": "escalate",
                        "action": PolicyAction.ESCALATE,
                        "severity": policy.severity,
                        "matching_policies": [policy.policy_id],
                        "policy_name": policy.name,
                        "reason": policy.description
                    }
                elif policy.action == PolicyAction.ALLOW:
                    # Allow, but continue checking for higher priority denies
                    continue
        
        # If we have matching allow policies, return allow
        allow_policies = [p for p in matching_policies if p.action == PolicyAction.ALLOW]
        if allow_policies:
            return {
                "decision": "allow",
                "action": PolicyAction.ALLOW,
                "severity": allow_policies[0].severity,
                "matching_policies": [p.policy_id for p in allow_policies],
                "policy_name": allow_policies[0].name
            }
        
        # If we have review policies, return review
        review_policies = [p for p in matching_policies if p.action == PolicyAction.REVIEW]
        if review_policies:
            return {
                "decision": "review",
                "action": PolicyAction.REVIEW,
                "severity": review_policies[0].severity,
                "matching_policies": [p.policy_id for p in review_policies],
                "policy_name": review_policies[0].name,
                "reason": review_policies[0].description
            }
        
        # Default deny if no policies match
        if self.default_deny:
            return {
                "decision": "deny",
                "action": PolicyAction.DENY,
                "severity": PolicySeverity.MEDIUM,
                "matching_policies": [],
                "reason": "No matching policy found, default deny"
            }
        
        # Default allow (less secure)
        return {
            "decision": "allow",
            "action": PolicyAction.ALLOW,
            "severity": PolicySeverity.LOW,
            "matching_policies": [],
            "reason": "No matching policy found, default allow"
        }
    
    def _matches_policy(
        self,
        policy: TrustPolicy,
        action_data: Dict[str, Any],
        context: Dict[str, Any]
    ) -> bool:
        """
        Check if action matches policy conditions.
        
        Args:
            policy: Policy to check
            action_data: Action data
            context: Evaluation context
            
        Returns:
            True if action matches policy
        """
        conditions = policy.conditions
        
        # Empty conditions means match all
        if not conditions:
            return True
        
        # Check each condition
        for key, condition_value in conditions.items():
            # Get value from action_data or context
            actual_value = action_data.get(key) or context.get(key)
            
            # Handle special "default" condition
            if key == "default" and condition_value is True:
                return True
            
            # Handle dictionary conditions (e.g., {"trust_score": {"min": 0.8}})
            if isinstance(condition_value, dict):
                if "min" in condition_value:
                    if not isinstance(actual_value, (int, float)) or actual_value < condition_value["min"]:
                        return False
                if "max" in condition_value:
                    if not isinstance(actual_value, (int, float)) or actual_value > condition_value["max"]:
                        return False
                if "equals" in condition_value:
                    if actual_value != condition_value["equals"]:
                        return False
            # Simple equality check
            elif actual_value != condition_value:
                return False
        
        return True
    
    def get_policy(self, policy_id: str) -> Optional[TrustPolicy]:
        """Get a policy by ID."""
        return self.policies.get(policy_id)
    
    def list_policies(
        self,
        enabled_only: bool = False,
        action: Optional[PolicyAction] = None
    ) -> List[TrustPolicy]:
        """
        List all policies with optional filtering.
        
        Args:
            enabled_only: If True, return only enabled policies
            action: Filter by action type
            
        Returns:
            List of policies
        """
        policies = list(self.policies.values())
        
        if enabled_only:
            policies = [p for p in policies if p.enabled]
        
        if action:
            policies = [p for p in policies if p.action == action]
        
        # Sort by priority
        policies.sort(key=lambda p: p.priority, reverse=True)
        
        return policies
    
    def get_current_policy_summary(self) -> Dict[str, Any]:
        """
        Get summary of current active policies.
        
        Returns:
            Policy summary dictionary
        """
        policies = self.list_policies(enabled_only=True)
        
        by_action = {}
        by_severity = {}
        
        for policy in policies:
            action = policy.action.value
            severity = policy.severity.value
            
            by_action[action] = by_action.get(action, 0) + 1
            by_severity[severity] = by_severity.get(severity, 0) + 1
        
        return {
            "total_policies": len(self.policies),
            "enabled_policies": len(policies),
            "default_deny": self.default_deny,
            "policies_by_action": by_action,
            "policies_by_severity": by_severity,
            "priority_range": {
                "min": min((p.priority for p in policies), default=0),
                "max": max((p.priority for p in policies), default=0)
            }
        }
    
    def save(self):
        """Save policies to disk."""
        with self._lock:
            data = {
                "policies": {
                    pid: policy.to_dict()
                    for pid, policy in self.policies.items()
                },
                "default_deny": self.default_deny,
                "updated_at": datetime.now().isoformat()
            }
            
            try:
                with open(self.storage_path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save policies: {e}")
    
    def load(self):
        """Load policies from disk."""
        if not self.storage_path.exists():
            return
        
        try:
            with open(self.storage_path, 'r') as f:
                data = json.load(f)
            
            with self._lock:
                self.default_deny = data.get("default_deny", True)
                policies_data = data.get("policies", {})
                
                for policy_id, policy_dict in policies_data.items():
                    try:
                        policy = TrustPolicy.from_dict(policy_dict)
                        self.policies[policy_id] = policy
                    except Exception as e:
                        logger.error(f"Failed to load policy {policy_id}: {e}")
            
            logger.info(f"Loaded {len(self.policies)} policies")
        except Exception as e:
            logger.error(f"Failed to load policies: {e}")


# Example usage
if __name__ == "__main__":
    # Create policy manager
    manager = TrustPolicyManager()
    
    # Evaluate an action
    result = manager.evaluate_action({
        "action_type": "mutation",
        "trust_score": 0.9
    })
    print(f"Evaluation result: {result}")
    
    # Get policy summary
    summary = manager.get_current_policy_summary()
    print(f"Policy summary: {summary}")
