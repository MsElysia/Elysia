# Mutation Sandbox

**File**: `project_guardian/mutation_sandbox.py`  
**Status**: ✅ IMPLEMENTED

---

## Overview

MutationSandbox provides isolated test execution for mutations before they're applied to the main codebase. This adds a critical safety layer by ensuring mutations pass tests in a controlled environment.

---

## Features

### Sandbox Creation

- **Isolated Environment** - Temporary directory for each mutation
- **Dependency Copying** - Automatically copies required dependencies
- **Test Files** - Copies test suite to sandbox
- **Code Application** - Applies mutation to sandbox copy

### Test Execution

- **Syntax Validation** - Validates code syntax before testing
- **Module Import Test** - Verifies module can be imported
- **Test Runner** - Runs tests (pytest compatible)
- **Timeout Protection** - Prevents hanging tests
- **Output Capture** - Captures stdout/stderr
- **Error Extraction** - Parses errors and warnings

### Safety Features

- **Isolation** - Each mutation tested in separate environment
- **Automatic Cleanup** - Removes sandbox after testing
- **Timeout Handling** - Prevents infinite test runs
- **Error Recovery** - Graceful handling of test failures

---

## Usage

### Basic Usage

```python
from project_guardian.mutation_sandbox import MutationSandbox
from project_guardian.mutation_engine import MutationEngine

# Initialize
sandbox = MutationSandbox(
    project_root=".",
    test_command="pytest",
    timeout=60,
    cleanup=True
)

# Get mutation proposal
mutation_engine = MutationEngine()
proposal = mutation_engine.get_proposal("mut_123")

# Test mutation
result = sandbox.test_mutation("mut_123", proposal)

if result.passed:
    print("All tests passed!")
else:
    print(f"Tests failed: {result.errors}")
```

### Integration with MutationPublisher

```python
from project_guardian.mutation_sandbox import integrate_with_mutation_publisher

# Integrate sandbox with publisher
integrate_with_mutation_publisher(mutation_publisher, sandbox)

# Now publish automatically runs sandbox tests
result = mutation_publisher.publish_mutation(
    "mut_123",
    run_sandbox_tests=True  # Runs sandbox tests before publishing
)
```

### Test Filtering

```python
# Test specific test file/module
result = sandbox.test_mutation(
    "mut_123",
    proposal,
    test_filter="tests/test_specific_module.py"
)
```

---

## Test Result Structure

```python
SandboxTestResult(
    test_id="uuid",
    mutation_id="mut_123",
    result=TestResult.PASSED,  # PASSED, FAILED, ERROR, TIMEOUT
    passed=True,
    execution_time=12.5,  # seconds
    output="Test output...",
    errors=[],  # List of error messages
    warnings=[],  # List of warnings
    module_imported=True,
    syntax_valid=True,
    metadata={...}
)
```

---

## Sandbox Process

1. **Create Sandbox**
   - Create temporary directory
   - Copy target module
   - Copy dependencies (if `include_dependencies=True`)
   - Copy test files
   - Apply mutation to sandbox copy

2. **Validate**
   - Syntax validation (MetaCoder or basic compile)
   - Module import test

3. **Run Tests**
   - Execute test command in sandbox
   - Capture output
   - Parse results

4. **Cleanup**
   - Remove sandbox directory (if `cleanup=True`)
   - Store results

---

## Configuration

```python
sandbox = MutationSandbox(
    project_root=".",           # Project root directory
    test_command="pytest",      # Test command (e.g., "pytest", "python -m pytest")
    timeout=60,                 # Test timeout in seconds
    cleanup=True,                # Auto-cleanup after tests
    metacoder=metacoder         # Optional MetaCoder for validation
)
```

---

## Statistics

```python
stats = sandbox.get_statistics()
# {
#     "total_tests": 100,
#     "passed": 85,
#     "failed": 10,
#     "errors": 3,
#     "timeouts": 2,
#     "pass_rate": 0.85,
#     "average_execution_time": 15.3,
#     "active_sandboxes": 0
# }
```

---

## Integration Points

### MutationPublisher

The sandbox can be integrated with `MutationPublisher` to automatically test mutations before publishing:

```python
integrate_with_mutation_publisher(mutation_publisher, sandbox)
```

When `publish_mutation()` is called with `run_sandbox_tests=True`, it will:
1. Run sandbox tests first
2. Only proceed with publish if tests pass
3. Return error if tests fail

### MutationReviewManager

Sandbox test results can be included in mutation reviews:

```python
# Test mutation in sandbox
sandbox_result = sandbox.test_mutation(mutation_id, proposal)

# Include in review
review = review_manager.review_mutation(
    mutation_id,
    ai_validator=ai_validator
)

# Sandbox result stored in metadata
review.metadata["sandbox_result"] = sandbox_result.to_dict()
```

---

## Safety Benefits

1. **Isolation** - Mutations tested in separate environment
2. **No Side Effects** - Main codebase unaffected by test failures
3. **Dependency Safety** - Dependencies copied, not modified
4. **Timeout Protection** - Prevents infinite test runs
5. **Cleanup** - Automatic cleanup prevents disk space issues

---

## Error Handling

- **Sandbox Creation Failure** - Returns error result
- **Syntax Errors** - Detected before test execution
- **Import Failures** - Detected and reported
- **Test Failures** - Captured and returned
- **Timeouts** - Handled gracefully with timeout result
- **Exceptions** - Caught and converted to error results

---

## Future Enhancements

- [ ] Code coverage analysis
- [ ] Performance benchmarking
- [ ] Multiple test runner support
- [ ] Parallel test execution
- [ ] Test result caching
- [ ] Integration with mutation scoring
- [ ] Custom test environments
- [ ] Mock/stub generation for dependencies

