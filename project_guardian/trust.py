# project_guardian/trust.py
# Trust Management System for Project Guardian

import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass
from .memory import MemoryCore

# Action constants - single source of truth for action names
# Used by all gateways to ensure consistent action strings
NETWORK_ACCESS = "network_access"
FILE_WRITE = "file_write"
SUBPROCESS_EXECUTION = "subprocess_execution"
GOVERNANCE_MUTATION = "governance_mutation"

# Legacy action strings (deprecated, but still supported for backward compatibility)
# These are NOT constants - they are legacy strings that may be used by older code.
# New code MUST use the constants above.
LEGACY_ACTIONS = {
    "mutation": "mutation",  # Legacy - prefer GOVERNANCE_MUTATION for governance mutations
    "data_access": "data_access",  # Legacy - no constant defined yet
    "system_change": SUBPROCESS_EXECUTION,  # Legacy alias for SUBPROCESS_EXECUTION
    "file_operation": FILE_WRITE,  # Legacy alias for FILE_WRITE
}


@dataclass
class TrustDecision:
    """
    Structured decision from TrustMatrix gate.
    
    Attributes:
        allowed: Whether action is allowed
        decision: "allow" | "deny" | "review"
        reason_code: Machine-readable reason code
        message: Human-readable message
        risk_score: Risk score (0.0 to 1.0), optional
    """
    allowed: bool
    decision: str  # "allow" | "deny" | "review"
    reason_code: str
    message: str
    risk_score: Optional[float] = None
    
    def __post_init__(self):
        """Validate decision values"""
        if self.decision not in ["allow", "deny", "review"]:
            raise ValueError(f"Invalid decision: {self.decision}. Must be 'allow', 'deny', or 'review'")
        if self.risk_score is not None and not (0.0 <= self.risk_score <= 1.0):
            raise ValueError(f"Invalid risk_score: {self.risk_score}. Must be between 0.0 and 1.0")

# Import extracted modules if available
try:
    import sys
    extracted_path = Path(__file__).parent.parent / "extracted_modules"
    if extracted_path.exists():
        sys.path.insert(0, str(extracted_path))
        from trust_consultation_system import TrustConsultationSystem
        from adversarial_ai_self_improvement import AdversarialAISelfImprovement
        EXTRACTED_MODULES_AVAILABLE = True
    else:
        EXTRACTED_MODULES_AVAILABLE = False
        TrustConsultationSystem = None
        AdversarialAISelfImprovement = None
except ImportError:
    EXTRACTED_MODULES_AVAILABLE = False
    TrustConsultationSystem = None
    AdversarialAISelfImprovement = None

class TrustMatrix:
    """
    Dynamic trust scoring and decay system for Project Guardian.
    Manages trust levels for different components and actions.
    """
    
    def __init__(self, memory: MemoryCore):
        self.memory = memory
        self.trust: Dict[str, float] = {}
        self.trust_history: List[Dict[str, Any]] = []
        self.decay_rate = 0.01  # Default decay rate per update
        
        # Initialize extracted modules if available
        if EXTRACTED_MODULES_AVAILABLE:
            try:
                # Initialize Trust Consultation System
                initial_trust = 0.8178  # 81.78% post-tuning from conversations
                self.consultation_system = TrustConsultationSystem(initial_trust=initial_trust)
                self.memory.remember(
                    "[Guardian Trust] Trust Consultation System initialized",
                    category="trust",
                    priority=0.8
                )
            except Exception as e:
                self.consultation_system = None
                self.memory.remember(
                    f"[Guardian Trust] Failed to initialize Trust Consultation System: {e}",
                    category="trust",
                    priority=0.5
                )
            
            try:
                # Initialize Adversarial AI Self-Improvement
                self.adversarial_system = AdversarialAISelfImprovement(initial_trust=0.75)
                self.memory.remember(
                    "[Guardian Trust] Adversarial AI Self-Improvement System initialized",
                    category="trust",
                    priority=0.8
                )
            except Exception as e:
                self.adversarial_system = None
                self.memory.remember(
                    f"[Guardian Trust] Failed to initialize Adversarial AI System: {e}",
                    category="trust",
                    priority=0.5
                )
        else:
            self.consultation_system = None
            self.adversarial_system = None
        
    def update_trust(self, name: str, delta: float, reason: str = "unspecified") -> float:
        """
        Update trust level for a component.
        
        Args:
            name: Component name
            delta: Trust change (-1.0 to 1.0)
            reason: Reason for the change
            
        Returns:
            New trust level
        """
        if name not in self.trust:
            self.trust[name] = 0.5  # Default trust level
            
        old_trust = self.trust[name]
        self.trust[name] = max(0.0, min(1.0, self.trust[name] + delta))
        new_trust = self.trust[name]
        
        # Log trust change
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "component": name,
            "old_trust": old_trust,
            "new_trust": new_trust,
            "delta": delta,
            "reason": reason
        }
        self.trust_history.append(entry)
        
        # Remember in memory
        self.memory.remember(
            f"[Guardian Trust] {name}: {old_trust:.3f} -> {new_trust:.3f} ({delta:+.3f}) - {reason}",
            category="trust",
            priority=0.7
        )
        
        return new_trust
        
    def get_trust(self, name: str) -> float:
        """
        Get current trust level for a component.
        
        Args:
            name: Component name
            
        Returns:
            Trust level (0.0 to 1.0)
        """
        return self.trust.get(name, 0.5)
        
    def get_trust_level_description(self, trust_level: float) -> str:
        """
        Get human-readable description of trust level.
        
        Args:
            trust_level: Trust level (0.0 to 1.0)
            
        Returns:
            Trust level description
        """
        if trust_level >= 0.9:
            return "Very High Trust"
        elif trust_level >= 0.7:
            return "High Trust"
        elif trust_level >= 0.5:
            return "Moderate Trust"
        elif trust_level >= 0.3:
            return "Low Trust"
        else:
            return "Very Low Trust"
            
    def decay_all(self, amount: Optional[float] = None) -> None:
        """
        Apply trust decay to all components.
        
        Args:
            amount: Decay amount (uses default if None)
        """
        if amount is None:
            amount = self.decay_rate
            
        for component in self.trust:
            old_trust = self.trust[component]
            self.trust[component] = max(0.0, self.trust[component] - amount)
            new_trust = self.trust[component]
            
            if old_trust != new_trust:
                self.memory.remember(
                    f"[Guardian Trust Decay] {component}: {old_trust:.3f} -> {new_trust:.3f}",
                    category="trust",
                    priority=0.5
                )
                
    def get_high_trust_components(self, threshold: float = 0.7) -> List[str]:
        """
        Get components with high trust levels.
        
        Args:
            threshold: Minimum trust level
            
        Returns:
            List of high-trust components
        """
        return [comp for comp, trust in self.trust.items() if trust >= threshold]
        
    def get_low_trust_components(self, threshold: float = 0.3) -> List[str]:
        """
        Get components with low trust levels.
        
        Args:
            threshold: Maximum trust level
            
        Returns:
            List of low-trust components
        """
        return [comp for comp, trust in self.trust.items() if trust <= threshold]
        
    def get_trust_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive trust report.
        
        Returns:
            Trust statistics and component status
        """
        high_trust = self.get_high_trust_components()
        low_trust = self.get_low_trust_components()
        
        return {
            "total_components": len(self.trust),
            "high_trust_components": high_trust,
            "low_trust_components": low_trust,
            "average_trust": sum(self.trust.values()) / len(self.trust) if self.trust else 0.5,
            "trust_history_count": len(self.trust_history),
            "recent_changes": self.trust_history[-10:] if self.trust_history else []
        }
        
    def validate_trust_for_action(self, component: str, action: str, context: Optional[Dict[str, Any]] = None) -> TrustDecision:
        """
        Validate if a component has sufficient trust for an action.
        
        Args:
            component: Component name
            action: Action to perform
            context: Optional context dict with target, method, caller_identity, task_id, etc.
            
        Returns:
            TrustDecision object with decision, reason_code, message, risk_score
        """
        trust_level = self.get_trust(component)
        
        # Define trust requirements for different actions
        # Use action constants for consistency
        # Legacy strings are supported for backward compatibility but should be migrated to constants
        trust_requirements = {
            # Action constants (preferred)
            NETWORK_ACCESS: 0.7,
            FILE_WRITE: 0.5,
            SUBPROCESS_EXECUTION: 0.9,  # High trust required for subprocess execution
            GOVERNANCE_MUTATION: 0.9,  # Same as subprocess for governance overrides
            
            # Legacy action strings (deprecated - use constants above)
            "mutation": 0.8,  # Legacy - prefer GOVERNANCE_MUTATION
            "data_access": 0.6,  # Legacy - no constant defined yet
            "system_change": 0.9,  # Legacy alias for SUBPROCESS_EXECUTION
            "file_operation": 0.5,  # Legacy alias for FILE_WRITE
            
            # Default fallback
            "default": 0.5
        }
        
        # Guardrail: Warn if unknown action string is used (not a constant and not in legacy list)
        # Check against both constants and legacy action strings
        known_actions = [NETWORK_ACCESS, FILE_WRITE, SUBPROCESS_EXECUTION, GOVERNANCE_MUTATION]
        known_actions.extend(LEGACY_ACTIONS.values())
        known_actions.extend(LEGACY_ACTIONS.keys())
        
        if action not in trust_requirements and action not in known_actions:
            self.memory.remember(
                f"[TrustMatrix] Unknown action string used: {action}. Consider using action constants from trust.py",
                category="governance",
                priority=0.6
            )
        
        required_trust = trust_requirements.get(action, trust_requirements["default"])
        
        # Calculate risk score (inverse of trust margin)
        trust_margin = trust_level - required_trust
        risk_score = max(0.0, min(1.0, 1.0 - trust_margin)) if trust_margin >= 0 else 1.0
        
        # Log context if provided (for audit trail, but no sensitive data)
        # Redact sensitive fields: sensitive, content, body, token, key, secret, password
        context_str = ""
        if context:
            sensitive_keys = ["sensitive", "content", "body", "token", "key", "secret", "password", "api_key", "auth_token"]
            safe_context = {k: v for k, v in context.items() if not any(sensitive in k.lower() for sensitive in sensitive_keys)}
            context_str = f" | Context: {safe_context}"
        
        if trust_level < required_trust:
            reason_code = f"INSUFFICIENT_TRUST_{action.upper()}"
            message = f"Insufficient trust for {action} by {component} (trust: {trust_level:.3f}, required: {required_trust:.3f})"
            
            self.memory.remember(
                f"[Guardian Trust] {message}{context_str}",
                category="trust",
                priority=0.8
            )
            
            return TrustDecision(
                allowed=False,
                decision="deny",
                reason_code=reason_code,
                message=message,
                risk_score=risk_score
            )
        
        # Check if trust is borderline (within 0.1 of requirement) - may need review
        # NOTE: decision="review" means action is NOT allowed until human approval.
        # allowed=False reflects that gateways must enqueue and raise TrustReviewRequiredError.
        if trust_level < required_trust + 0.1:
            reason_code = f"BORDERLINE_TRUST_{action.upper()}"
            message = f"Borderline trust for {action} by {component} (trust: {trust_level:.3f}, required: {required_trust:.3f}) - may require review"
            
            self.memory.remember(
                f"[Guardian Trust] {message}{context_str}",
                category="trust",
                priority=0.7
            )
            
            return TrustDecision(
                allowed=False,  # Review decisions are NOT allowed until approved
                decision="review",
                reason_code=reason_code,
                message=message,
                risk_score=risk_score
            )
        
        # Trust is sufficient
        reason_code = f"ALLOWED_{action.upper()}"
        message = f"Approved {action} by {component} (trust: {trust_level:.3f})"
        
        if context:
            # Redact sensitive fields (same as above)
            sensitive_keys = ["sensitive", "content", "body", "token", "key", "secret", "password", "api_key", "auth_token"]
            safe_context = {k: v for k, v in context.items() if not any(sensitive in k.lower() for sensitive in sensitive_keys)}
            self.memory.remember(
                f"[Guardian Trust] {message} | Context: {safe_context}",
                category="trust",
                priority=0.6
            )
        else:
            self.memory.remember(
                f"[Guardian Trust] {message}",
                category="trust",
                priority=0.6
            )
        
        return TrustDecision(
            allowed=True,
            decision="allow",
            reason_code=reason_code,
            message=message,
            risk_score=risk_score
        )
        
    def get_trust_summary(self) -> str:
        """
        Get a human-readable trust summary.
        
        Returns:
            Trust summary string
        """
        if not self.trust:
            return "[Guardian Trust] No trust data available."
            
        high_trust = self.get_high_trust_components()
        low_trust = self.get_low_trust_components()
        avg_trust = sum(self.trust.values()) / len(self.trust)
        
        summary = f"[Guardian Trust] Summary: {len(self.trust)} components, "
        summary += f"avg trust: {avg_trust:.3f}, "
        summary += f"high trust: {len(high_trust)}, low trust: {len(low_trust)}"
        
        return summary
    
    def make_consultation_decision(
        self,
        confidence: float,
        context: Dict[str, Any],
        mediator_input: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Make a consultation decision using the Trust Consultation System.
        
        Args:
            confidence: Confidence level (0.0 to 1.0)
            context: Context information
            mediator_input: Optional mediator input
            
        Returns:
            Consultation decision or None if system not available
        """
        if self.consultation_system:
            try:
                decision = self.consultation_system.make_consultation_decision(
                    confidence=confidence,
                    context=context,
                    mediator_input=mediator_input
                )
                # Update trust based on decision
                if decision.mediator_alignment:
                    self.update_trust("mediator", 0.01, "mediator_aligned_decision")
                return {
                    "action": decision.action,
                    "confidence": decision.confidence,
                    "trust_level": decision.trust_level,
                    "mediator_alignment": decision.mediator_alignment,
                    "reasoning": decision.reasoning
                }
            except Exception as e:
                self.memory.remember(
                    f"[Guardian Trust] Consultation decision error: {e}",
                    category="trust",
                    priority=0.6
                )
        return None
    
    def run_adversarial_improvement_cycle(
        self,
        num_debates: int = 100,
        perfect_ratio: float = 0.5
    ) -> Optional[Dict[str, Any]]:
        """
        Run an adversarial self-improvement cycle.
        
        Args:
            num_debates: Number of debates to run
            perfect_ratio: Ratio of perfect to flawed mediators
            
        Returns:
            Improvement results or None if system not available
        """
        if self.adversarial_system:
            try:
                results = self.adversarial_system.run_self_improvement_cycle(
                    num_debates=num_debates,
                    perfect_ratio=perfect_ratio
                )
                # Update trust based on results
                final_trust = results.get('final_trust', 0.75)
                initial_trust = results.get('initial_trust', 0.75)
                trust_delta = final_trust - initial_trust
                self.update_trust("adversarial_system", trust_delta, "adversarial_improvement_cycle")
                return results
            except Exception as e:
                self.memory.remember(
                    f"[Guardian Trust] Adversarial improvement error: {e}",
                    category="trust",
                    priority=0.6
                )
        return None