"""
TrustEvalContent - Content filtering and sanitization for trust system
Integrated from old modules.
"""

from typing import Dict, List, Optional, Any


class TrustEvalContent:
    """
    Evaluates content for trust and safety violations.
    Filters content based on policy rules.
    """
    
    def __init__(self, audit_logger=None, policy_manager=None):
        """
        Initialize TrustEvalContent.
        
        Args:
            audit_logger: Optional audit logger instance
            policy_manager: Optional policy manager instance
        """
        self.audit = audit_logger
        self.policy = policy_manager
        self.default_policies = {
            "banned_words": [],
            "min_content_length": 0,
            "max_content_length": 100000
        }
    
    def _get_policy_rules(self) -> Dict[str, Any]:
        """Get current policy rules from policy manager or use defaults"""
        if self.policy and hasattr(self.policy, 'policies'):
            return {**self.default_policies, **self.policy.policies}
        return self.default_policies
    
    def _log_event(self, verdict: str, details: Dict[str, Any]):
        """Log audit event if audit logger is available"""
        if self.audit:
            if hasattr(self.audit, 'log_event'):
                self.audit.log_event(verdict, details)
            elif hasattr(self.audit, 'remember'):
                self.audit.remember(f"[TrustEvalContent] {verdict}: {details}")
    
    def evaluate(self, content: str, user_id: str = "system", context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Evaluate content for trust and safety violations.
        
        Args:
            content: Content string to evaluate
            user_id: User identifier
            context: Optional context dictionary
        
        Returns:
            Dictionary with verdict, reason, and flags
        """
        if not content or not content.strip():
            self._log_event("ALLOW", {
                "user_id": user_id,
                "module": "TrustEvalContent",
                "reason": "empty"
            })
            return {
                "verdict": "ALLOW",
                "reason": "empty",
                "flags": [],
                "score": 1.0
            }
        
        rules = self._get_policy_rules()
        flags = []
        lowered = content.lower()
        
        # Check content length
        content_length = len(content)
        if content_length < rules.get("min_content_length", 0):
            flags.append("content_too_short")
        if content_length > rules.get("max_content_length", 100000):
            flags.append("content_too_long")
        
        # Check banned words
        if "banned_words" in rules:
            for word in rules["banned_words"]:
                if word.lower() in lowered:
                    flags.append(f"banned_word: {word}")
        
        # Check for suspicious patterns
        suspicious_patterns = [
            "exec(",
            "eval(",
            "__import__",
            "compile(",
            "open(",
            "file(",
            "input(",
            "raw_input("
        ]
        for pattern in suspicious_patterns:
            if pattern in content:
                flags.append(f"suspicious_pattern: {pattern}")
        
        # Calculate trust score (0.0 to 1.0)
        base_score = 1.0
        score_penalty = len(flags) * 0.2
        final_score = max(0.0, base_score - score_penalty)
        
        if flags:
            self._log_event("DENY", {
                "user_id": user_id,
                "module": "TrustEvalContent",
                "reason": "policy_violation",
                "flags": flags,
                "score": final_score
            })
            return {
                "verdict": "DENY",
                "reason": "policy_violation",
                "flags": flags,
                "score": final_score
            }
        
        self._log_event("ALLOW", {
            "user_id": user_id,
            "module": "TrustEvalContent",
            "reason": "clean",
            "score": final_score
        })
        return {
            "verdict": "ALLOW",
            "reason": "clean",
            "flags": [],
            "score": final_score
        }
    
    def sanitize_content(self, content: str, user_id: str = "system") -> Dict[str, Any]:
        """
        Sanitize content by removing or replacing flagged elements.
        
        Args:
            content: Content to sanitize
            user_id: User identifier
        
        Returns:
            Dictionary with sanitized content and changes made
        """
        evaluation = self.evaluate(content, user_id)
        
        if evaluation["verdict"] == "ALLOW":
            return {
                "sanitized": content,
                "changes": [],
                "original": content
            }
        
        sanitized = content
        changes = []
        
        # Remove banned words
        rules = self._get_policy_rules()
        if "banned_words" in rules:
            for word in rules["banned_words"]:
                if word.lower() in sanitized.lower():
                    sanitized = sanitized.replace(word, "[REDACTED]")
                    changes.append(f"removed_banned_word: {word}")
        
        return {
            "sanitized": sanitized,
            "changes": changes,
            "original": content,
            "flags": evaluation["flags"]
        }


# Example usage
if __name__ == "__main__":
    # Test with default policies
    evaluator = TrustEvalContent()
    
    # Test clean content
    result = evaluator.evaluate("This is a clean message.", "user1")
    print("Clean content:", result)
    
    # Test with suspicious pattern
    result = evaluator.evaluate("This has exec() in it.", "user2")
    print("Suspicious content:", result)
    
    # Test sanitization
    sanitized = evaluator.sanitize_content("This has exec() in it.", "user3")
    print("Sanitized:", sanitized)

