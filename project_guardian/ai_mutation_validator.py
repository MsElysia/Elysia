# project_guardian/ai_mutation_validator.py
# AIMutationValidator: AI-Powered Mutation Validation
# Uses AI to check mutations for safety, quality, and correctness

import logging
import json
import re
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
        if not self.ask_ai:
            logger.warning("AskAI not available, returning default pass")
            return ValidationResult(
                mutation_id=proposal.mutation_id,
                passed=True,
                confidence=0.5,
                score=0.5,
                summary="AI validation not available"
            )
        
        self.stats["total_validations"] += 1
        
        # Build validation prompt
        prompt = self._build_validation_prompt(proposal, original_code)
        
        try:
            # Call AI for validation
            response = await self.ask_ai.ask(
                prompt=prompt,
                provider=self.provider,
                temperature=0.3,  # Lower temperature for more consistent analysis
                max_tokens=2000
            )
            
            if not response.success:
                logger.error(f"AI validation failed: {response.error}")
                return ValidationResult(
                    mutation_id=proposal.mutation_id,
                    passed=False,
                    confidence=0.0,
                    score=0.0,
                    summary=f"AI validation error: {response.error}"
                )
            
            # Parse AI response
            validation_result = self._parse_ai_response(
                proposal.mutation_id,
                response.content,
                proposal.proposed_code
            )
            
            # Update statistics
            if validation_result.passed:
                self.stats["passed"] += 1
            else:
                self.stats["failed"] += 1
            
            # Update average score
            total_score = self.stats["average_score"] * (self.stats["total_validations"] - 1)
            total_score += validation_result.score
            self.stats["average_score"] = total_score / self.stats["total_validations"]
            
            # Count critical issues
            critical_count = sum(
                1 for issue in validation_result.issues
                if issue.severity == ValidationSeverity.CRITICAL
            )
            self.stats["critical_issues_found"] += critical_count
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Error in AI validation: {e}", exc_info=True)
            return ValidationResult(
                mutation_id=proposal.mutation_id,
                passed=False,
                confidence=0.0,
                score=0.0,
                summary=f"Validation error: {str(e)}"
            )
    
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
    from mutation_review_manager import ReviewDecision
    
    original_review = review_manager.review_mutation
    
    async def enhanced_review_mutation(*args, **kwargs):
        """Enhanced review that includes AI validation."""
        mutation_id = args[0] if args else kwargs.get("mutation_id")
        
        # Get proposal
        if not review_manager.mutation_engine:
            return original_review(*args, **kwargs)
        
        proposal = review_manager.mutation_engine.get_proposal(mutation_id)
        if not proposal:
            return original_review(*args, **kwargs)
        
        # Run AI validation
        try:
            import asyncio
            ai_result = await ai_validator.validate_mutation(
                proposal,
                original_code=proposal.original_code
            )
            
            # Enhance review with AI results
            review = original_review(*args, **kwargs)
            
            # Add AI validation to review metadata
            review.metadata["ai_validation"] = ai_result.to_dict()
            
            # Adjust review based on AI results
            if not ai_result.passed:
                # AI found issues - enhance review concerns
                review.concerns.extend([
                    f"AI Validation: {issue.description}"
                    for issue in ai_result.issues
                    if issue.severity in [ValidationSeverity.CRITICAL, ValidationSeverity.ERROR]
                ])
                
                # If critical AI issues, consider deferring
                critical_ai_issues = [
                    issue for issue in ai_result.issues
                    if issue.severity == ValidationSeverity.CRITICAL
                ]
                if critical_ai_issues:
                    review.decision = ReviewDecision.DEFER
                    review.reasoning += f" AI found {len(critical_ai_issues)} critical issues."
            
            # Add AI recommendations
            if ai_result.recommendations:
                review.conditions.extend(ai_result.recommendations)
            
            return review
            
        except Exception as e:
            logger.error(f"AI validation integration error: {e}")
            # Fall back to original review
            return original_review(*args, **kwargs)
    
    # Replace review method
    review_manager.review_mutation = enhanced_review_mutation
    logger.info("AI mutation validator integrated with MutationReviewManager")


# Example usage
if __name__ == "__main__":
    # Initialize components
    ask_ai = None  # Would be provided
    mutation_engine = None  # Would be provided
    
    validator = AIMutationValidator(
        ask_ai=ask_ai,
        provider=AIProvider.OPENAI if AIProvider else None,
        min_confidence_threshold=0.7
    )
    
    # Validate a mutation
    # proposal = mutation_engine.get_proposal("mut_123")
    # result = await validator.validate_mutation(proposal)
    # print(validator.get_validation_summary(result))

