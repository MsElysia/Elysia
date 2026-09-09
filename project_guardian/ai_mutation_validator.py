# project_guardian/ai_mutation_validator.py
# AIMutationValidator: AI-Powered Mutation Validation
# Uses AI to check mutations for safety, quality, and correctness

import logging
import json
import re
import inspect
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field

try:
    from .ask_ai import AskAI, AIProvider
    from .mutation_engine import MutationProposal
except ImportError:
    try:
        from ask_ai import AskAI, AIProvider
        from mutation_engine import MutationProposal
    except ImportError:
        AskAI = None
        AIProvider = None
        MutationProposal = None

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Validation issue severity."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidationCategory(Enum):
    """Validation categories."""
    SECURITY = "security"
    CORRECTNESS = "correctness"
    PERFORMANCE = "performance"
    STYLE = "style"
    MAINTAINABILITY = "maintainability"
    COMPATIBILITY = "compatibility"


@dataclass
class ValidationIssue:
    """Represents a validation issue found by AI."""
    severity: ValidationSeverity
    category: ValidationCategory
    description: str
    line_number: Optional[int] = None
    code_snippet: Optional[str] = None
    suggestion: Optional[str] = None
    confidence: float = 0.5  # 0.0-1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "severity": self.severity.value,
            "category": self.category.value,
            "description": self.description,
            "line_number": self.line_number,
            "code_snippet": self.code_snippet,
            "suggestion": self.suggestion,
            "confidence": self.confidence
        }


@dataclass
class ValidationResult:
    """Result of AI mutation validation."""
    mutation_id: str
    passed: bool
    confidence: float  # Overall confidence in validation
    score: float  # 0.0-1.0, quality score
    issues: List[ValidationIssue] = field(default_factory=list)
    summary: str = ""
    recommendations: List[str] = field(default_factory=list)
    validated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "mutation_id": self.mutation_id,
            "passed": self.passed,
            "confidence": self.confidence,
            "score": self.score,
            "issues": [issue.to_dict() for issue in self.issues],
            "summary": self.summary,
            "recommendations": self.recommendations,
            "validated_at": self.validated_at.isoformat()
        }


class AIMutationValidator:
    """
    AI-powered mutation validator.
    Uses AskAI to analyze mutations for safety, quality, and correctness.
    """
    
    def __init__(
        self,
        ask_ai: Optional[AskAI] = None,
        provider: AIProvider = AIProvider.OPENAI if AIProvider else None,
        min_confidence_threshold: float = 0.7,
        fail_on_critical: bool = True
    ):
        """
        Initialize AIMutationValidator.
        
        Args:
            ask_ai: AskAI instance
            provider: AI provider to use
            min_confidence_threshold: Minimum confidence for approval (0.0-1.0)
            fail_on_critical: If True, critical issues cause validation failure
        """
        self.ask_ai = ask_ai
        self.provider = provider
        self.min_confidence_threshold = min_confidence_threshold
        self.fail_on_critical = fail_on_critical
        
        # Statistics
        self.stats = {
            "total_validations": 0,
            "passed": 0,
            "failed": 0,
            "average_score": 0.0,
            "critical_issues_found": 0
        }
    
    async def validate_mutation(
        self,
        proposal: MutationProposal,
        original_code: Optional[str] = None
    ) -> ValidationResult:
        """
        Validate a mutation proposal using AI.
        
        Args:
            proposal: Mutation proposal
            original_code: Original code (if available)
            
        Returns:
            ValidationResult
        """
        self.stats["total_validations"] += 1

        if not self.ask_ai:
            logger.warning("AskAI not available; mutation validation requires manual review")
            return self._record_validation_result(ValidationResult(
                mutation_id=proposal.mutation_id,
                passed=False,
                confidence=0.0,
                score=0.0,
                issues=[
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        category=ValidationCategory.COMPATIBILITY,
                        description="AskAI is not configured; AI mutation validation cannot run.",
                        suggestion="Configure AskAI/LLM validation or route this mutation through manual review before approval.",
                        confidence=1.0,
                    )
                ],
                summary="AI validation not available; manual review required",
                recommendations=[
                    "Configure AskAI/LLM validation before automated approval.",
                    "Route this mutation through manual review before applying it.",
                ],
            ))
        
        # Build validation prompt
        prompt = self._build_validation_prompt(proposal, original_code)
        
        try:
            # Call AI for validation
            response = await self.ask_ai.ask_async(
                prompt=prompt,
                provider=self.provider,
                temperature=0.3,  # Lower temperature for more consistent analysis
                max_tokens=2000
            )
            
            if not response.success:
                logger.error(f"AI validation failed: {response.error}")
                return self._record_validation_result(ValidationResult(
                    mutation_id=proposal.mutation_id,
                    passed=False,
                    confidence=0.0,
                    score=0.0,
                    summary=f"AI validation error: {response.error}"
                ))
            
            # Parse AI response
            validation_result = self._parse_ai_response(
                proposal.mutation_id,
                response.content,
                proposal.proposed_code
            )
            return self._record_validation_result(validation_result)
            
        except Exception as e:
            logger.error(f"Error in AI validation: {e}", exc_info=True)
            return self._record_validation_result(ValidationResult(
                mutation_id=proposal.mutation_id,
                passed=False,
                confidence=0.0,
                score=0.0,
                summary=f"Validation error: {str(e)}"
            ))

    def _record_validation_result(self, validation_result: ValidationResult) -> ValidationResult:
        """Update aggregate validation statistics for a completed result."""
        if validation_result.passed:
            self.stats["passed"] += 1
        else:
            self.stats["failed"] += 1

        total_score = self.stats["average_score"] * (self.stats["total_validations"] - 1)
        total_score += validation_result.score
        self.stats["average_score"] = total_score / max(1, self.stats["total_validations"])

        critical_count = sum(
            1 for issue in validation_result.issues
            if issue.severity == ValidationSeverity.CRITICAL
        )
        self.stats["critical_issues_found"] += critical_count

        return validation_result
    
    def _build_validation_prompt(
        self,
        proposal: MutationProposal,
        original_code: Optional[str]
    ) -> str:
        """Build AI validation prompt."""
        prompt = f"""Analyze this code mutation for safety, quality, and correctness.

MUTATION DETAILS:
- Mutation ID: {proposal.mutation_id}
- Target Module: {proposal.target_module}
- Mutation Type: {proposal.mutation_type}
- Description: {proposal.description}
- Confidence: {proposal.confidence:.2f}

ORIGINAL CODE:
```python
{original_code[:2000] if original_code else "Original code not provided"}
```

PROPOSED CODE:
```python
{proposal.proposed_code[:2000]}
```

VALIDATION REQUIREMENTS:
1. **Security**: Check for security vulnerabilities (injection, file access, etc.)
2. **Correctness**: Verify logic correctness and potential bugs
3. **Performance**: Identify performance issues or bottlenecks
4. **Style**: Check code style and best practices
5. **Maintainability**: Assess code maintainability
6. **Compatibility**: Check for compatibility issues with existing code
7. **Replication Gating**: Flag autonomous deployment, cloning, slave spawning, persistence, or resource acquisition that lacks explicit human approval.
8. **Lineage Tracking**: Flag missing provenance, signing, parent identifiers, or registry metadata for generated modules, model variants, or mutation pipelines.
9. **Deception Robustness**: Look for hidden triggers, filter avoidance, camouflage/obfuscation, impersonation, or code paths that would behave differently under tests.
10. **Selection Pressure Risk**: Flag objectives based on engagement, cost minimization, rate-limit/filter avoidance, or competitive survival when they may select for unsafe behavior.

Return a JSON response with this structure:
{{
  "passed": true/false,
  "confidence": 0.0-1.0,
  "score": 0.0-1.0,
  "summary": "Brief summary of validation",
  "issues": [
    {{
      "severity": "info|warning|error|critical",
      "category": "security|correctness|performance|style|maintainability|compatibility",
      "description": "Issue description",
      "line_number": null or integer,
      "code_snippet": "relevant code snippet",
      "suggestion": "how to fix",
      "confidence": 0.0-1.0
    }}
  ],
  "recommendations": ["recommendation1", "recommendation2"]
}}

Return ONLY valid JSON, no markdown or explanation outside the JSON."""
        
        return prompt
    
    def _parse_ai_response(
        self,
        mutation_id: str,
        ai_content: str,
        proposed_code: str
    ) -> ValidationResult:
        """Parse AI response into ValidationResult."""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', ai_content, re.DOTALL)
            if not json_match:
                logger.warning("No JSON found in AI response")
                return ValidationResult(
                    mutation_id=mutation_id,
                    passed=False,
                    confidence=0.0,
                    score=0.0,
                    summary="Failed to parse AI response"
                )
            
            json_str = json_match.group(0)
            data = json.loads(json_str)
            
            # Parse issues
            issues = []
            for issue_data in data.get("issues", []):
                try:
                    issue = ValidationIssue(
                        severity=ValidationSeverity(issue_data.get("severity", "info")),
                        category=ValidationCategory(issue_data.get("category", "style")),
                        description=issue_data.get("description", ""),
                        line_number=issue_data.get("line_number"),
                        code_snippet=issue_data.get("code_snippet"),
                        suggestion=issue_data.get("suggestion"),
                        confidence=float(issue_data.get("confidence", 0.5))
                    )
                    issues.append(issue)
                except Exception as e:
                    logger.debug(f"Failed to parse issue: {e}")
            
            # Determine if passed
            passed = data.get("passed", False)
            confidence = float(data.get("confidence", 0.5))
            score = float(data.get("score", 0.5))
            
            # Check critical issues
            critical_issues = [
                issue for issue in issues
                if issue.severity == ValidationSeverity.CRITICAL
            ]
            
            if self.fail_on_critical and critical_issues:
                passed = False
                score = min(score, 0.3)  # Lower score if critical issues
            
            # Check confidence threshold
            if confidence < self.min_confidence_threshold:
                passed = False
            
            # Check score threshold
            if score < 0.6:  # Require at least 60% quality score
                passed = False
            
            return ValidationResult(
                mutation_id=mutation_id,
                passed=passed,
                confidence=confidence,
                score=score,
                issues=issues,
                summary=data.get("summary", ""),
                recommendations=data.get("recommendations", []),
                validated_at=datetime.now()
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response JSON: {e}")
            return ValidationResult(
                mutation_id=mutation_id,
                passed=False,
                confidence=0.0,
                score=0.0,
                summary=f"JSON parse error: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Error parsing AI response: {e}", exc_info=True)
            return ValidationResult(
                mutation_id=mutation_id,
                passed=False,
                confidence=0.0,
                score=0.0,
                summary=f"Parse error: {str(e)}"
            )
    
    def get_validation_summary(
        self,
        validation_result: ValidationResult
    ) -> str:
        """
        Get human-readable validation summary.
        
        Args:
            validation_result: Validation result
            
        Returns:
            Formatted summary string
        """
        lines = [
            f"AI Validation: {'PASSED' if validation_result.passed else 'FAILED'}",
            f"Confidence: {validation_result.confidence:.2%}",
            f"Quality Score: {validation_result.score:.2%}",
            ""
        ]
        
        if validation_result.summary:
            lines.append(f"Summary: {validation_result.summary}")
            lines.append("")
        
        # Group issues by severity
        critical = [i for i in validation_result.issues if i.severity == ValidationSeverity.CRITICAL]
        errors = [i for i in validation_result.issues if i.severity == ValidationSeverity.ERROR]
        warnings = [i for i in validation_result.issues if i.severity == ValidationSeverity.WARNING]
        info = [i for i in validation_result.issues if i.severity == ValidationSeverity.INFO]
        
        if critical:
            lines.append("CRITICAL ISSUES:")
            for issue in critical:
                lines.append(f"  - [{issue.category.value}] {issue.description}")
                if issue.suggestion:
                    lines.append(f"    → {issue.suggestion}")
            lines.append("")
        
        if errors:
            lines.append("ERRORS:")
            for issue in errors:
                lines.append(f"  - [{issue.category.value}] {issue.description}")
            lines.append("")
        
        if warnings:
            lines.append("WARNINGS:")
            for issue in warnings:
                lines.append(f"  - [{issue.category.value}] {issue.description}")
        
        if validation_result.recommendations:
            lines.append("")
            lines.append("RECOMMENDATIONS:")
            for rec in validation_result.recommendations:
                lines.append(f"  - {rec}")
        
        return "\n".join(lines)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get validator statistics."""
        return {
            "total_validations": self.stats["total_validations"],
            "passed": self.stats["passed"],
            "failed": self.stats["failed"],
            "pass_rate": self.stats["passed"] / max(1, self.stats["total_validations"]),
            "average_score": self.stats["average_score"],
            "critical_issues_found": self.stats["critical_issues_found"]
        }


# Integration with MutationReviewManager
def _guardian_component(guardian: Any, *names: str) -> Any:
    """Best-effort attribute lookup for lightweight guardian wiring."""
    for name in names:
        if guardian is not None and hasattr(guardian, name):
            value = getattr(guardian, name)
            if value is not None:
                return value
    return None


def configure_ai_validator_integration(
    *,
    review_manager: Optional[Any] = None,
    mutation_engine: Optional[Any] = None,
    guardian: Optional[Any] = None,
    ai_validator: Optional["AIMutationValidator"] = None,
):
    """
    Resolve review dependencies from explicit args or a minimal guardian object.

    Returns the configured review manager so standalone helpers can avoid placeholder
    ``None`` wiring.
    """
    resolved_review_manager = review_manager or _guardian_component(
        guardian,
        "mutation_review_manager",
        "review_manager",
    )
    resolved_mutation_engine = mutation_engine or _guardian_component(
        guardian,
        "mutation_engine",
        "mutation",
    )

    if resolved_review_manager is None:
        raise ValueError("review_manager is required for AI validator integration")

    if resolved_mutation_engine is not None and getattr(resolved_review_manager, "mutation_engine", None) is None:
        try:
            resolved_review_manager.mutation_engine = resolved_mutation_engine
        except Exception:
            logger.debug("Unable to attach mutation_engine to review_manager", exc_info=True)

    if ai_validator is not None:
        integrate_ai_validator(resolved_review_manager, ai_validator)
    return resolved_review_manager


def integrate_ai_validator(
    review_manager,
    ai_validator: AIMutationValidator
):
    """
    Integrate AIMutationValidator with MutationReviewManager.
    
    Args:
        review_manager: MutationReviewManager instance
        ai_validator: AIMutationValidator instance
    """
    if review_manager is None:
        raise ValueError("review_manager is required")
    if ai_validator is None:
        raise ValueError("ai_validator is required")

    if getattr(review_manager, "_integrated_ai_validator", None) is ai_validator:
        return review_manager

    original_review = review_manager.review_mutation
    signature = inspect.signature(original_review)
    supports_ai_validator = (
        "ai_validator" in signature.parameters
        or any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
    )

    def enhanced_review_mutation(*args, **kwargs):
        """Enhanced review that forwards the configured AI validator when supported."""
        if supports_ai_validator:
            kwargs.setdefault("ai_validator", ai_validator)
        return original_review(*args, **kwargs)

    # Replace review method
    review_manager.review_mutation = enhanced_review_mutation
    review_manager._integrated_ai_validator = ai_validator
    logger.info("AI mutation validator integrated with MutationReviewManager")
    return review_manager


if __name__ == "__main__":
    import sys

    print(
        "AIMutationValidator is a library component. Wire it with "
        "configure_ai_validator_integration(...) / integrate_ai_validator(...) "
        "using a live AskAI and MutationReviewManager from your guardian runtime."
    )
    sys.exit(0)
