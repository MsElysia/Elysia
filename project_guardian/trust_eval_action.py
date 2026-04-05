# project_guardian/trust_eval_action.py
# TrustEval-Action: Action-level Security Validation
# Based on Conversation 6 design specifications

import logging
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
from datetime import datetime
from .trust_policy_manager import TrustPolicyManager
from .trust_audit_log import TrustAuditLog, AuditEventType, AuditSeverity
from .trust_escalation_handler import TrustEscalationHandler

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Types of actions that can be validated."""
    NETWORK_REQUEST = "network_request"
    FILE_ACCESS = "file_access"
    ADMIN_COMMAND = "admin_command"
    DATABASE_QUERY = "database_query"
    SYSTEM_COMMAND = "system_command"
    MODULE_EXECUTION = "module_execution"


class SeverityLevel(Enum):
    """Severity levels for action validation."""
    CRITICAL = "critical"  # 80-100
    HIGH = "high"          # 70-79
    MEDIUM = "medium"      # 50-69
    LOW = "low"            # 0-49


class TrustEvalAction:
    """
    Guards and validates all system actions/commands that Elysia attempts.
    Ensures no unauthorized or unsafe operations occur.
    """
    
    def __init__(
        self,
        policy_manager: Optional[TrustPolicyManager] = None,
        audit_logger: Optional[TrustAuditLog] = None,
        escalation_handler: Optional[TrustEscalationHandler] = None
    ):
        self.policy = policy_manager or TrustPolicyManager()
        self.audit = audit_logger or TrustAuditLog()
        self.escalation = escalation_handler or TrustEscalationHandler(self.audit)
        
    def authorize_action(
        self,
        request_context: Dict[str, Any],
        action: Dict[str, Any],
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Main authorization interface for actions.
        
        Args:
            request_context: Context about the request (user_id, role, etc.)
            action: Action to validate (type, target, parameters)
            dry_run: If True, validate without executing
            
        Returns:
            Authorization result with verdict, severity, and reason
        """
        user_id = request_context.get("user_id", "system")
        action_type = action.get("type")
        action_target = action.get("target", "")
        action_params = action.get("parameters", {})
        
        # Determine action category
        if action_type in ["network", "api_call", "http_request"]:
            action_category = ActionType.NETWORK_REQUEST
        elif action_type in ["file_read", "file_write", "file_delete"]:
            action_category = ActionType.FILE_ACCESS
        elif action_type in ["admin", "system", "sudo"]:
            action_category = ActionType.ADMIN_COMMAND
        elif action_type in ["db_query", "database"]:
            action_category = ActionType.DATABASE_QUERY
        else:
            action_category = ActionType.MODULE_EXECUTION
            
        # Check if action is allowed
        is_allowed, reason, severity_score = self._evaluate_action(
            user_id, action_category, action_target, action_params
        )
        
        verdict = "ALLOW" if is_allowed else "DENY"
        severity_level = self._score_to_severity(severity_score)

        audit_evt = AuditEventType.ACTION_ALLOWED if is_allowed else AuditEventType.ACTION_DENIED
        audit_sev = AuditSeverity.WARNING if severity_score >= 70 else AuditSeverity.INFO
        self.audit.log_event(
            audit_evt,
            f"{verdict}: {action_target} — {reason}",
            severity=audit_sev,
            actor=user_id,
            action={
                "type": action_category.value,
                "target": action_target,
                "parameters": action_params,
            },
            result={
                "verdict": verdict,
                "severity_score": severity_score,
                "dry_run": dry_run,
                "severity_level": severity_level.value,
            },
        )
        
        # Escalate if severity is high enough
        if severity_score >= 70:
            self.escalation.flag_for_review(
                user_id=user_id,
                action=action,
                severity=severity_score
            )
            
        result = {
            "verdict": verdict,
            "allowed": is_allowed,
            "severity_score": severity_score,
            "severity_level": severity_level.value,
            "reason": reason,
            "dry_run": dry_run,
            "action_id": action.get("id", "unknown")
        }
        
        if not is_allowed:
            result["blocked"] = True
            logger.warning(f"Action denied: {action_target} - {reason} (severity: {severity_score})")
        else:
            logger.info(f"Action allowed: {action_target} (severity: {severity_score})")
            
        return result
        
    def _evaluate_action(
        self,
        user_id: str,
        action_type: ActionType,
        target: str,
        parameters: Dict[str, Any]
    ) -> Tuple[bool, str, int]:
        """
        Core permission check for an action.
        
        Returns:
            Tuple of (is_allowed, reason, severity_score)
        """
        policy = self.policy.current_policy
        
        # Check network requests
        if action_type == ActionType.NETWORK_REQUEST:
            return self._check_network_action(target, parameters, policy)
            
        # Check file access
        elif action_type == ActionType.FILE_ACCESS:
            return self._check_file_action(target, parameters, policy)
            
        # Check admin commands
        elif action_type == ActionType.ADMIN_COMMAND:
            return self._check_admin_action(user_id, target, parameters, policy)
            
        # Check database queries
        elif action_type == ActionType.DATABASE_QUERY:
            return self._check_database_action(target, parameters, policy)
            
        # Default: moderate security check
        else:
            return self._check_default_action(target, parameters, policy)
            
    def _check_network_action(
        self,
        target: str,
        parameters: Dict[str, Any],
        policy: Dict[str, Any]
    ) -> Tuple[bool, str, int]:
        """Check network request actions."""
        # Check blocked IP ranges
        blocked_ranges = policy.get("network", {}).get("blocked_ip_ranges", [])
        if any(target.startswith(ip_range) for ip_range in blocked_ranges):
            return (False, "Network request blocked: target in blocked IP range", 80)
            
        # Check allowed domains
        allowed_domains = policy.get("network", {}).get("allowed_domains", [])
        if allowed_domains:
            domain = target.split("/")[2] if "/" in target else target
            if not any(domain.endswith(allowed) for allowed in allowed_domains):
                return (False, "Network request blocked: domain not in allowed list", 75)
                
        # Check for dangerous protocols
        if target.startswith("file://") or target.startswith("jar://"):
            return (False, "Network request blocked: dangerous protocol", 85)
            
        return (True, "Network request allowed", 20)
        
    def _check_file_action(
        self,
        target: str,
        parameters: Dict[str, Any],
        policy: Dict[str, Any]
    ) -> Tuple[bool, str, int]:
        """Check file access actions."""
        restricted_paths = policy.get("filesystem", {}).get("restricted_paths", [])
        
        # Check if path is restricted
        for restricted in restricted_paths:
            if target.startswith(restricted):
                return (False, f"File access blocked: path in restricted list ({restricted})", 85)
                
        # Check for write operations in critical directories
        operation = parameters.get("operation", "read")
        critical_dirs = policy.get("filesystem", {}).get("critical_directories", [])
        
        if operation in ["write", "delete", "modify"]:
            for critical_dir in critical_dirs:
                if target.startswith(critical_dir):
                    return (False, f"Write operation blocked: target in critical directory ({critical_dir})", 90)
                    
        # Check for dangerous file types
        dangerous_extensions = policy.get("filesystem", {}).get("dangerous_extensions", [])
        if any(target.endswith(ext) for ext in dangerous_extensions):
            return (False, "File access blocked: dangerous file type", 70)
            
        return (True, "File access allowed", 15)
        
    def _check_admin_action(
        self,
        user_id: str,
        target: str,
        parameters: Dict[str, Any],
        policy: Dict[str, Any]
    ) -> Tuple[bool, str, int]:
        """Check administrative command actions."""
        # Check if user has admin role
        user_roles = policy.get("users", {}).get(user_id, {}).get("roles", [])
        if "admin" not in user_roles and "operator" not in user_roles:
            return (False, "Admin command blocked: insufficient role", 90)
            
        # Check blocked admin commands
        blocked_commands = policy.get("admin", {}).get("blocked_commands", [])
        if any(target.startswith(cmd) for cmd in blocked_commands):
            return (False, "Admin command blocked: command in blocked list", 95)
            
        # Check time-of-day restrictions
        time_restrictions = policy.get("admin", {}).get("time_restrictions", {})
        if time_restrictions:
            current_hour = datetime.now().hour
            allowed_hours = time_restrictions.get("allowed_hours", list(range(24)))
            if current_hour not in allowed_hours:
                return (False, "Admin command blocked: outside allowed time window", 60)
                
        return (True, "Admin command allowed", 30)
        
    def _check_database_action(
        self,
        target: str,
        parameters: Dict[str, Any],
        policy: Dict[str, Any]
    ) -> Tuple[bool, str, int]:
        """Check database query actions."""
        # Check for dangerous SQL patterns
        query = parameters.get("query", "").upper()
        dangerous_patterns = ["DROP", "DELETE", "TRUNCATE", "ALTER"]
        
        if any(pattern in query for pattern in dangerous_patterns):
            return (False, "Database query blocked: dangerous SQL pattern detected", 85)
            
        # Check if database is restricted
        restricted_databases = policy.get("database", {}).get("restricted_databases", [])
        if target in restricted_databases:
            return (False, "Database query blocked: database in restricted list", 80)
            
        return (True, "Database query allowed", 25)
        
    def _check_default_action(
        self,
        target: str,
        parameters: Dict[str, Any],
        policy: Dict[str, Any]
    ) -> Tuple[bool, str, int]:
        """Default security check for unknown action types."""
        # Basic check: allow if not explicitly restricted
        return (True, "Action allowed (default check)", 40)
        
    def _score_to_severity(self, score: int) -> SeverityLevel:
        """Convert severity score to severity level."""
        if score >= 80:
            return SeverityLevel.CRITICAL
        elif score >= 70:
            return SeverityLevel.HIGH
        elif score >= 50:
            return SeverityLevel.MEDIUM
        else:
            return SeverityLevel.LOW
            
    def is_action_allowed(
        self,
        user_id: str,
        action: Dict[str, Any]
    ) -> bool:
        """
        Simple check if an action is allowed.
        
        Args:
            user_id: User/component identifier
            action: Action to check
            
        Returns:
            True if allowed, False otherwise
        """
        context = {"user_id": user_id}
        result = self.authorize_action(context, action, dry_run=True)
        return result["allowed"]
        
    def refresh_policy(self):
        """Reload policy from TrustPolicyManager."""
        self.policy.load_policy()
        logger.info("Trust policy refreshed")


# Integration adapter for ElysiaLoop-Core
from .elysia_loop_core import BaseModuleAdapter


class TrustEvalActionAdapter(BaseModuleAdapter):
    """Adapter for TrustEval-Action module."""
    
    def __init__(self, trust_eval: TrustEvalAction):
        self.trust_eval = trust_eval
        
    def get_module_name(self) -> str:
        return "trust_eval_action"
        
    def get_capabilities(self) -> List[str]:
        return ["authorize_action", "is_action_allowed", "refresh_policy"]
        
    def execute(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if method == "authorize_action":
                request_context = payload.get("request_context", {})
                action = payload.get("action", {})
                dry_run = payload.get("dry_run", False)
                result = self.trust_eval.authorize_action(request_context, action, dry_run)
                return {"success": True, "result": result}
                
            elif method == "is_action_allowed":
                user_id = payload.get("user_id", "system")
                action = payload.get("action", {})
                is_allowed = self.trust_eval.is_action_allowed(user_id, action)
                return {"success": True, "allowed": is_allowed}
                
            elif method == "refresh_policy":
                self.trust_eval.refresh_policy()
                return {"success": True, "message": "Policy refreshed"}
                
            else:
                return {"success": False, "error": f"Unknown method: {method}"}
                
        except Exception as e:
            logger.error(f"TrustEval-Action error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

