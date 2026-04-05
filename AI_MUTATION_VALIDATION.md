# AI Mutation Validation

**File**: `project_guardian/ai_mutation_validator.py`  
**Status**: ✅ IMPLEMENTED

---

## Overview

AIMutationValidator uses AI (via AskAI) to analyze mutations before they're applied, providing an additional layer of safety and quality assurance beyond syntax validation.

---

## Features

### Validation Categories

1. **Security** - Detects vulnerabilities, injection risks, file access issues
2. **Correctness** - Logic errors, potential bugs, edge cases
3. **Performance** - Bottlenecks, inefficient code, resource usage
4. **Style** - Code style, best practices, PEP compliance
5. **Maintainability** - Code clarity, documentation, complexity
6. **Compatibility** - Breaking changes, API compatibility

### Issue Severity Levels

- **CRITICAL** - Security vulnerabilities, critical bugs (blocks approval)
- **ERROR** - Serious issues that should be fixed
- **WARNING** - Issues to consider fixing
- **INFO** - Suggestions for improvement

### Validation Results

- **Pass/Fail** - Overall validation result
- **Confidence** - AI confidence in analysis (0.0-1.0)
- **Score** - Quality score (0.0-1.0)
- **Issues** - Detailed list of issues found
- **Recommendations** - Suggestions for improvement
- **Summary** - Human-readable summary

---

## Integration

### With MutationReviewManager

```python
from project_guardian.ai_mutation_validator import AIMutationValidator, integrate_ai_validator
from project_guardian.mutation_review_manager import MutationReviewManager
from project_guardian.ask_ai import AskAI, AIProvider

# Initialize
ask_ai = AskAI(openai_api_key="...")
validator = AIMutationValidator(
    ask_ai=ask_ai,
    provider=AIProvider.OPENAI,
    min_confidence_threshold=0.7,
    fail_on_critical=True
)

review_manager = MutationReviewManager(...)

# Integrate
integrate_ai_validator(review_manager, validator)

# Now all reviews include AI validation
review = review_manager.review_mutation("mut_123")
```

### Direct Usage

```python
# Validate a mutation directly
result = await validator.validate_mutation(proposal, original_code)

if result.passed:
    print(f"Validation passed with score: {result.score:.2%}")
else:
    print(f"Validation failed:")
    print(validator.get_validation_summary(result))
```

---

## AI Validation Process

1. **Build Prompt** - Creates detailed prompt with:
   - Mutation details (type, description, confidence)
   - Original code
   - Proposed code
   - Validation requirements

2. **AI Analysis** - Calls AskAI with:
   - Low temperature (0.3) for consistent analysis
   - Structured JSON response format
   - Security, correctness, performance checks

3. **Parse Response** - Extracts:
   - Validation result (pass/fail)
   - Issues with severity and category
   - Recommendations
   - Confidence and score

4. **Enhance Review** - Integrates with MutationReviewManager:
   - Adds AI issues to concerns
   - Defers review if critical issues found
   - Includes recommendations in conditions
   - Adjusts confidence based on AI score

---

## Example Validation Output

```
AI Validation: FAILED
Confidence: 85.00%
Quality Score: 45.00%

Summary: Mutation introduces potential security vulnerability and performance issue

CRITICAL ISSUES:
  - [security] Direct file write without validation could allow path traversal
    → Add path validation before file operations
  - [security] User input not sanitized before use in eval-like operation
    → Use safe string operations instead

ERRORS:
  - [correctness] Missing null check could cause AttributeError
  - [performance] Nested loop with O(n²) complexity

RECOMMENDATIONS:
  - Add input validation
  - Use pathlib for path operations
  - Add error handling for edge cases
  - Consider caching for repeated operations
```

---

## Configuration

### Thresholds

```python
validator = AIMutationValidator(
    ask_ai=ask_ai,
    min_confidence_threshold=0.7,  # Minimum AI confidence
    fail_on_critical=True  # Block on critical issues
)
```

### Customization

- **Confidence Threshold**: Require minimum AI confidence (default: 0.7)
- **Score Threshold**: Minimum quality score (default: 0.6)
- **Fail on Critical**: Automatically fail if critical issues found
- **Provider Selection**: Choose AI provider (OpenAI, Claude, etc.)

---

## Benefits

### Safety Enhancement
- **Security Scanning**: Detects vulnerabilities before deployment
- **Bug Detection**: Finds logic errors and edge cases
- **Quality Assurance**: Ensures code quality standards

### Integration Benefits
- **Automatic**: Works with existing MutationReviewManager
- **Non-Blocking**: Falls back gracefully if AI unavailable
- **Comprehensive**: Multi-category analysis (security, correctness, performance, etc.)

---

## Statistics

The validator tracks:
- Total validations
- Pass/fail rates
- Average quality scores
- Critical issues found

Access via `validator.get_statistics()`

---

## Future Enhancements

- [ ] Multiple AI provider comparison
- [ ] Custom validation rules
- [ ] Learning from past mutations
- [ ] Integration with mutation test suite
- [ ] Real-time validation during code editing
- [ ] Batch validation for multiple mutations

