# project_guardian/safety.py
# Safety and Critical Thinking Module for Project Guardian

import random
from typing import List, Dict, Any, Optional
from .memory import MemoryCore

class DevilsAdvocate:
    """
    Critical thinking and safety validation system for Project Guardian.
    Provides built-in skepticism and safety checks.
    """
    
    def __init__(self, memory: MemoryCore):
        self.memory = memory
        self.challenge_history: List[Dict[str, Any]] = []
        
    def challenge(self, claim: str, context: str = "unspecified") -> str:
        """
        Challenge a claim with critical analysis.
        
        Args:
            claim: The claim to challenge
            context: Context for the challenge
            
        Returns:
            Challenge response
        """
        flaws = [
            "relies on unfounded assumptions",
            "ignores potential side effects",
            "creates unnecessary complexity",
            "has unclear benefits",
            "could introduce regressions",
            "is ethically questionable",
            "conflicts with prior behavior",
            "invites unintended consequences",
            "lacks proper validation",
            "may violate safety protocols",
            "doesn't consider edge cases",
            "could impact system stability"
        ]
        
        flaw = random.choice(flaws)
        rebuttal = (
            f"[Guardian Safety] '{claim}' may be flawed — it {flaw}. "
            f"Context: {context}."
        )
        
        self.memory.remember(rebuttal, category="safety", priority=0.8)
        self.challenge_history.append({
            "claim": claim,
            "context": context,
            "flaw": flaw,
            "rebuttal": rebuttal
        })
        print(rebuttal)
        return rebuttal
        
    def review_mutation(self, mutation_diff: List[str]) -> str:
        """
        Review code mutation for safety issues.
        
        Args:
            mutation_diff: List of code changes
            
        Returns:
            Safety assessment
        """
        if not mutation_diff:
            return "[Guardian Safety] No mutation diff provided."
            
        red_flags = [
            "import os", "import subprocess", "import sys",
            "exec(", "eval(", "compile(",
            "open(", "file(", "os.system(",
            "subprocess.call(", "subprocess.run(",
            "memory.forget", "memory.clear",
            "password", "secret", "token", "key",
            "rm -rf", "del /s", "format c:",
            "shutdown", "reboot", "kill",
            "network", "socket", "http",
            "delete", "remove", "unlink"
        ]
        
        flagged_lines = [
            line for line in mutation_diff 
            if any(flag in line.lower() for flag in red_flags)
        ]
        
        if flagged_lines:
            warning = f"[Guardian Safety] ⚠️ Mutation contains suspicious patterns: {flagged_lines}"
            self.memory.remember(warning, category="safety", priority=0.9)
            return warning
            
        self.memory.remember("[Guardian Safety] Mutation passed basic scrutiny.", 
                           category="safety", priority=0.6)
        return "[Guardian Safety] No immediate safety concerns."
        
    def review_action(self, action: str, parameters: Dict[str, Any]) -> str:
        """
        Review a proposed action for safety.
        
        Args:
            action: Action to review
            parameters: Action parameters
            
        Returns:
            Safety assessment
        """
        dangerous_actions = [
            "delete", "remove", "format", "shutdown",
            "restart", "kill", "terminate", "clear",
            "reset", "wipe", "destroy"
        ]
        
        if any(dangerous in action.lower() for dangerous in dangerous_actions):
            warning = f"[Guardian Safety] ⚠️ Potentially dangerous action detected: {action}"
            self.memory.remember(warning, category="safety", priority=0.9)
            return warning
            
        # Check for dangerous parameters
        dangerous_params = ["password", "secret", "token", "key", "credential"]
        for param, value in parameters.items():
            if any(dangerous in param.lower() for dangerous in dangerous_params):
                warning = f"[Guardian Safety] ⚠️ Action contains sensitive parameter: {param}"
                self.memory.remember(warning, category="safety", priority=0.8)
                return warning
                
        return "[Guardian Safety] Action appears safe."
        
    def validate_trust_level(self, component: str, trust_level: float) -> str:
        """
        Validate if a trust level is appropriate.
        
        Args:
            component: Component name
            trust_level: Proposed trust level (0.0 to 1.0)
            
        Returns:
            Validation result
        """
        if trust_level > 0.9:
            warning = f"[Guardian Safety] ⚠️ Very high trust level ({trust_level}) for {component}"
            self.memory.remember(warning, category="safety", priority=0.8)
            return warning
            
        if trust_level < 0.1:
            warning = f"[Guardian Safety] ⚠️ Very low trust level ({trust_level}) for {component}"
            self.memory.remember(warning, category="safety", priority=0.7)
            return warning
            
        return "[Guardian Safety] Trust level appears reasonable."
        
    def check_system_health(self, health_metrics: Dict[str, Any]) -> str:
        """
        Check system health metrics for concerning patterns.
        
        Args:
            health_metrics: System health data
            
        Returns:
            Health assessment
        """
        concerns = []
        
        # Check memory usage
        if health_metrics.get("memory_usage", 0) > 0.9:
            concerns.append("High memory usage")
            
        # Check CPU usage
        if health_metrics.get("cpu_usage", 0) > 0.95:
            concerns.append("High CPU usage")
            
        # Check error rate
        if health_metrics.get("error_rate", 0) > 0.1:
            concerns.append("High error rate")
            
        # Check mutation frequency
        if health_metrics.get("mutations_per_hour", 0) > 10:
            concerns.append("High mutation frequency")
            
        if concerns:
            warning = f"[Guardian Safety] ⚠️ System health concerns: {', '.join(concerns)}"
            self.memory.remember(warning, category="safety", priority=0.8)
            return warning
            
        return "[Guardian Safety] System health appears normal."
        
    def get_safety_report(self) -> Dict[str, Any]:
        """
        Generate a safety report.
        
        Returns:
            Safety statistics and recent concerns
        """
        recent_challenges = self.challenge_history[-10:] if self.challenge_history else []
        
        return {
            "total_challenges": len(self.challenge_history),
            "recent_challenges": recent_challenges,
            "safety_level": "high" if len(recent_challenges) < 5 else "medium"
        } 