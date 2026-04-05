# project_guardian/trust_eval_content.py
# TrustEvalContent: Content Filtering and Sanitization
# Based on Conversation 6 design specifications

import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
from datetime import datetime
from .trust_policy_manager import TrustPolicyManager
from .trust_audit_log import TrustAuditLog
from .trust_escalation_handler import TrustEscalationHandler

logger = logging.getLogger(__name__)


class ContentVerdict(Enum):
    """Content evaluation verdict."""
    ALLOW = "ALLOW"
    MODIFY = "MODIFY"
    DENY = "DENY"
    ESCALATE = "ESCALATE"


class ContentCategory(Enum):
    """Categories of content that can be flagged."""
    HATE_SPEECH = "hate_speech"
    PII = "pii"  # Personally Identifiable Information
    SEXUAL_CONTENT = "sexual_content"
    VIOLENCE = "violence"
    PROFANITY = "profanity"
    SPAM = "spam"
    MALICIOUS = "malicious"


class TrustEvalContent:
    """
    Filters and sanitizes all natural-language output from Elysia.
    Acts as gatekeeper for generated content.
    Ensures compliance with trust and safety policies.
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
        
        # Initialize content patterns
        self._init_patterns()
        
    def _init_patterns(self):
        """Initialize regex patterns for content detection."""
        # PII Patterns
        self.pii_patterns = {
            "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
            "phone": re.compile(r'(\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}'),
            "ssn": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
            "credit_card": re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'),
            "ip_address": re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
        }
        
        # Hate speech indicators (simplified - would use ML model in production)
        self.hate_speech_keywords = [
            # Add hate speech patterns here - keeping minimal for safety
        ]
        
        # Profanity patterns (simplified)
        self.profanity_patterns = [
            # Add profanity detection - keeping minimal for safety
        ]
        
        # URL patterns
        self.url_pattern = re.compile(
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        )
        
    def evaluate(
        self,
        content: str,
        user_id: str = "system",
        persona_mode: Optional[str] = None,
        child_safe_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Evaluate content for safety and compliance.
        
        Args:
            content: Content text to evaluate
            user_id: User/component identifier
            persona_mode: Active persona mode (affects filtering strictness)
            child_safe_mode: If True, stricter filtering
            
        Returns:
            Evaluation result with verdict, flags, and modified content
        """
        flags: List[str] = []
        issues: List[str] = []
        modified_content = content
        
        # Check for PII
        pii_results = self._check_pii(content)
        if pii_results["found"]:
            flags.append(ContentCategory.PII.value)
            issues.extend(pii_results["issues"])
            modified_content = pii_results["redacted_content"]
            
        # Check for hate speech
        hate_speech_result = self._check_hate_speech(content)
        if hate_speech_result["found"]:
            flags.append(ContentCategory.HATE_SPEECH.value)
            issues.append("Potential hate speech detected")
            
        # Check for sexual content
        sexual_content_result = self._check_sexual_content(content)
        if sexual_content_result["found"]:
            flags.append(ContentCategory.SEXUAL_CONTENT.value)
            issues.append("Potential sexual content detected")
            
        # Check for violence
        violence_result = self._check_violence(content)
        if violence_result["found"]:
            flags.append(ContentCategory.VIOLENCE.value)
            issues.append("Violent content detected")
            
        # Check for profanity (if child safe mode)
        if child_safe_mode:
            profanity_result = self._check_profanity(content)
            if profanity_result["found"]:
                flags.append(ContentCategory.PROFANITY.value)
                issues.append("Profanity detected")
                modified_content = profanity_result["sanitized_content"]
                
        # Check for malicious URLs
        url_result = self._check_malicious_urls(content)
        if url_result["found"]:
            flags.append(ContentCategory.MALICIOUS.value)
            issues.extend(url_result["issues"])
            modified_content = url_result["sanitized_content"]
            
        # Determine verdict based on findings
        verdict = self._determine_verdict(flags, issues, child_safe_mode)
        
        # Log evaluation
        if verdict != ContentVerdict.ALLOW:
            if verdict == ContentVerdict.MODIFY:
                self.audit.log_modification(user_id, content, modified_content, issues)
            elif verdict == ContentVerdict.DENY:
                self.audit.log_violation(user_id, content, f"Content denied: {', '.join(issues)}")
            elif verdict == ContentVerdict.ESCALATE:
                self.escalation.flag_for_review(
                    user_id=user_id,
                    action={"type": "content_evaluation", "content": content[:200]},
                    severity=75,
                    reason=f"Content escalated: {', '.join(issues)}"
                )
                
        result = {
            "verdict": verdict.value,
            "flags": flags,
            "issues": issues,
            "original_length": len(content),
            "modified_content": modified_content if verdict == ContentVerdict.MODIFY else content,
            "was_modified": verdict == ContentVerdict.MODIFY
        }
        
        return result
        
    def _check_pii(self, content: str) -> Dict[str, Any]:
        """Check for Personally Identifiable Information."""
        found_pii = []
        redacted_content = content
        
        for pii_type, pattern in self.pii_patterns.items():
            matches = pattern.findall(content)
            if matches:
                found_pii.append(f"{pii_type}: {len(matches)} found")
                
                # Redact based on type
                if pii_type == "email":
                    redacted_content = pattern.sub("[EMAIL_REDACTED]", redacted_content)
                elif pii_type == "phone":
                    redacted_content = pattern.sub("[PHONE_REDACTED]", redacted_content)
                elif pii_type == "ssn":
                    redacted_content = pattern.sub("[SSN_REDACTED]", redacted_content)
                elif pii_type == "credit_card":
                    redacted_content = pattern.sub("[CARD_REDACTED]", redacted_content)
                elif pii_type == "ip_address":
                    # Allow localhost
                    for match in matches:
                        if match not in ["127.0.0.1", "localhost"]:
                            redacted_content = redacted_content.replace(match, "[IP_REDACTED]")
                            
        return {
            "found": len(found_pii) > 0,
            "pii_types": found_pii,
            "issues": found_pii,
            "redacted_content": redacted_content
        }
        
    def _check_hate_speech(self, content: str) -> Dict[str, Any]:
        """Check for hate speech indicators."""
        # Simplified check - in production, would use ML model
        # Ensure content is a string
        if isinstance(content, list):
            content = " ".join(str(item) for item in content)
        content_str = str(content)
        content_lower = content_str.lower()
        
        # Check policy for hate speech keywords
        policy = self.policy.current_policy
        hate_speech_keywords = policy.get("content", {}).get("hate_speech_keywords", [])
        
        found_keywords = []
        for keyword in hate_speech_keywords:
            if isinstance(keyword, str) and keyword.lower() in content_lower:
                found_keywords.append(keyword)
                
        return {
            "found": len(found_keywords) > 0,
            "keywords": found_keywords
        }
        
    def _check_sexual_content(self, content: str) -> Dict[str, Any]:
        """Check for sexual content indicators."""
        # Simplified check - in production, would use ML model
        # Ensure content is a string
        if isinstance(content, list):
            content = " ".join(str(item) for item in content)
        content_str = str(content)
        content_lower = content_str.lower()
        
        policy = self.policy.current_policy
        sexual_keywords = policy.get("content", {}).get("sexual_keywords", [])
        
        found_keywords = []
        for keyword in sexual_keywords:
            if isinstance(keyword, str) and keyword.lower() in content_lower:
                found_keywords.append(keyword)
                
        return {
            "found": len(found_keywords) > 0,
            "keywords": found_keywords
        }
        
    def _check_violence(self, content: str) -> Dict[str, Any]:
        """Check for violent content indicators."""
        # Ensure content is a string
        if isinstance(content, list):
            content = " ".join(str(item) for item in content)
        content_str = str(content)
        content_lower = content_str.lower()
        
        policy = self.policy.current_policy
        violence_keywords = policy.get("content", {}).get("violence_keywords", [])
        
        found_keywords = []
        for keyword in violence_keywords:
            if isinstance(keyword, str) and keyword.lower() in content_lower:
                found_keywords.append(keyword)
                
        return {
            "found": len(found_keywords) > 0,
            "keywords": found_keywords
        }
        
    def _check_profanity(self, content: str) -> Dict[str, Any]:
        """Check for profanity."""
        # Ensure content is a string
        if isinstance(content, list):
            content = " ".join(str(item) for item in content)
        content_str = str(content)
        content_lower = content_str.lower()
        sanitized_content = content_str
        
        policy = self.policy.current_policy
        profanity_keywords = policy.get("content", {}).get("profanity_keywords", [])
        
        found_keywords = []
        for keyword in profanity_keywords:
            if isinstance(keyword, str) and keyword.lower() in content_lower:
                found_keywords.append(keyword)
                # Replace with asterisks
                pattern = re.compile(re.escape(keyword), re.IGNORECASE)
                sanitized_content = pattern.sub("*" * len(keyword), sanitized_content)
                
        return {
            "found": len(found_keywords) > 0,
            "keywords": found_keywords,
            "sanitized_content": sanitized_content
        }
        
    def _check_malicious_urls(self, content: str) -> Dict[str, Any]:
        """Check for malicious or suspicious URLs."""
        urls = self.url_pattern.findall(content)
        issues = []
        sanitized_content = content
        
        if not urls:
            return {"found": False, "issues": [], "sanitized_content": content}
            
        policy = self.policy.current_policy
        blocked_domains = policy.get("content", {}).get("blocked_url_domains", [])
        suspicious_patterns = policy.get("content", {}).get("suspicious_url_patterns", [])
        
        for url in urls:
            domain = self._extract_domain(url)
            
            # Check blocked domains
            if any(domain.endswith(blocked) for blocked in blocked_domains):
                issues.append(f"Blocked domain: {domain}")
                sanitized_content = sanitized_content.replace(url, "[URL_BLOCKED]")
                continue
                
            # Check suspicious patterns
            for pattern in suspicious_patterns:
                if pattern in url:
                    issues.append(f"Suspicious URL pattern: {pattern}")
                    sanitized_content = sanitized_content.replace(url, "[URL_REMOVED]")
                    break
                    
        return {
            "found": len(issues) > 0,
            "issues": issues,
            "sanitized_content": sanitized_content
        }
        
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            # Remove protocol
            url = url.replace("http://", "").replace("https://", "")
            # Get domain part
            domain = url.split("/")[0]
            return domain
        except Exception:
            return url
            
    def _determine_verdict(
        self,
        flags: List[str],
        issues: List[str],
        child_safe_mode: bool
    ) -> ContentVerdict:
        """
        Determine final verdict based on findings.
        
        Priority:
        1. DENY: Hate speech
        2. ESCALATE: Sexual content
        3. MODIFY: PII, profanity (in child safe mode), malicious URLs
        4. ALLOW: No issues
        """
        if ContentCategory.HATE_SPEECH.value in flags:
            return ContentVerdict.DENY
            
        if ContentCategory.SEXUAL_CONTENT.value in flags:
            return ContentVerdict.ESCALATE
            
        if ContentCategory.PII.value in flags:
            return ContentVerdict.MODIFY
            
        if ContentCategory.PROFANITY.value in flags and child_safe_mode:
            return ContentVerdict.MODIFY
            
        if ContentCategory.MALICIOUS.value in flags:
            return ContentVerdict.MODIFY
            
        if ContentCategory.VIOLENCE.value in flags:
            # Violence: escalate if severe, modify if mild
            return ContentVerdict.ESCALATE
            
        return ContentVerdict.ALLOW
        
    def filter_content(
        self,
        content: str,
        user_id: str = "system",
        **kwargs
    ) -> str:
        """
        Convenience method to filter content and return sanitized version.
        
        Args:
            content: Content to filter
            user_id: User identifier
            **kwargs: Additional evaluation parameters
            
        Returns:
            Filtered/sanitized content
        """
        result = self.evaluate(content, user_id, **kwargs)
        
        if result["verdict"] == ContentVerdict.DENY:
            return "[CONTENT_BLOCKED]"
        elif result["verdict"] == ContentVerdict.MODIFY:
            return result["modified_content"]
        elif result["verdict"] == ContentVerdict.ESCALATE:
            # Return original but flag for review
            return result["modified_content"]
        else:
            return content


# Integration adapter for ElysiaLoop-Core
from .elysia_loop_core import BaseModuleAdapter


class TrustEvalContentAdapter(BaseModuleAdapter):
    """Adapter for TrustEvalContent module."""
    
    def __init__(self, trust_eval_content: TrustEvalContent):
        self.trust_eval_content = trust_eval_content
        
    def get_module_name(self) -> str:
        return "trust_eval_content"
        
    def get_capabilities(self) -> List[str]:
        return ["evaluate", "filter_content"]
        
    def execute(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if method == "evaluate":
                content = payload.get("content", "")
                user_id = payload.get("user_id", "system")
                persona_mode = payload.get("persona_mode")
                child_safe_mode = payload.get("child_safe_mode", False)
                
                result = self.trust_eval_content.evaluate(
                    content, user_id, persona_mode, child_safe_mode
                )
                return {"success": True, "result": result}
                
            elif method == "filter_content":
                content = payload.get("content", "")
                user_id = payload.get("user_id", "system")
                kwargs = payload.get("kwargs", {})
                
                filtered = self.trust_eval_content.filter_content(content, user_id, **kwargs)
                return {"success": True, "filtered_content": filtered}
                
            else:
                return {"success": False, "error": f"Unknown method: {method}"}
                
        except Exception as e:
            logger.error(f"TrustEvalContent error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

