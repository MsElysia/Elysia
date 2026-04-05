# Proposal System Tests

Pytest test suite for the Elysia proposal system.

## Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_proposal_validation.py

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=project_guardian --cov-report=html
```

## Test Structure

- `test_proposal_validation.py` - ProposalValidator tests
- `test_lifecycle_transitions.py` - ProposalLifecycleManager tests
- `test_duplicate_detection.py` - Duplicate detection tests
- `test_history_tracking.py` - History/audit trail tests

## Fixtures

- `base_metadata` - Base valid proposal metadata
- `temp_proposals_dir` - Temporary directory for test proposals
- `sample_proposal_path` - Sample proposal directory with metadata
- `validator` - ProposalValidator instance
- `lifecycle_manager` - ProposalLifecycleManager instance

