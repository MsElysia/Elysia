# Project Guardian Test Suite

## Test Structure

### test_basic_functionality.py
Tests individual components work independently:
- MemoryCore storage and recall
- TrustMatrix trust updates and decay
- Feedback evaluators (Accuracy, Creativity)
- Basic TrustEval functionality

### test_integration.py
Tests critical system integrations:
- Event loop with module execution
- Security systems (TrustEval-Action, TrustEvalContent)
- Memory system (vector search, snapshots)
- FeedbackLoop evaluation cycles
- End-to-end workflows
- System health reporting

### test_introspection_ui.py
Tests introspection UI integration:
- Introspection API endpoints (comprehensive, identity, behavior, health, focus, correlations, patterns)
- Data formatting for UI display
- Error handling when introspection unavailable
- UI template integration (introspection tab)
- Direct method testing (bypassing UI layer)

## Running Tests

```bash
# Run all tests
pytest project_guardian/tests/ -v

# Run specific test file
pytest project_guardian/tests/test_basic_functionality.py -v
pytest project_guardian/tests/test_introspection_ui.py -v

# Run specific test
pytest project_guardian/tests/test_integration.py::TestSecurityIntegration::test_trust_eval_action_blocks_dangerous_action -v
pytest project_guardian/tests/test_introspection_ui.py::TestIntrospectionAPIIntegration::test_comprehensive_report_endpoint -v

# Run with coverage
pytest project_guardian/tests/ --cov=project_guardian --cov-report=html
```

## Test Requirements

Tests may require:
- OpenAI API key (for vector memory tests) - set OPENAI_API_KEY env var
- FAISS library (for vector memory tests)
- All dependencies from requirements.txt

## Test Fixtures

- `temp_dir`: Temporary directory for test files
- `test_config`: Standard test configuration
- `guardian_core`: Pre-configured GuardianCore instance
- `event_loop`: Async event loop for async tests

