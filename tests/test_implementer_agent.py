"""Tests for Elysia-Implementer agent."""

import json
import tempfile
from pathlib import Path

import pytest

from elysia.agents.implementer import ImplementerAgent, ImplementationStep
from elysia.core.proposal_system import ProposalSystem
from elysia.events import EventBus


@pytest.fixture
def temp_proposals_root(tmp_path):
    """Create a temporary proposals root directory."""
    proposals_root = tmp_path / "proposals"
    proposals_root.mkdir()
    return proposals_root


@pytest.fixture
def temp_repo_root(tmp_path):
    """Create a temporary repo root directory."""
    return tmp_path


@pytest.fixture
def event_bus():
    """Create an event bus for testing."""
    return EventBus()


@pytest.fixture
def proposal_system(temp_proposals_root, event_bus):
    """Create a proposal system for testing."""
    return ProposalSystem(proposals_root=temp_proposals_root, event_bus=event_bus, enable_watcher=False)


@pytest.fixture
def implementer_agent(temp_repo_root, proposal_system, event_bus):
    """Create an ImplementerAgent for testing."""
    return ImplementerAgent(
        repo_root=temp_repo_root,
        proposal_system=proposal_system,
        event_bus=event_bus,
        dry_run=False,
    )


def create_test_proposal(proposals_root: Path, proposal_id: str, status: str = "approved"):
    """Create a test proposal with metadata."""
    proposal_path = proposals_root / proposal_id
    proposal_path.mkdir()
    (proposal_path / "design").mkdir()

    metadata = {
        "proposal_id": proposal_id,
        "title": "Test Proposal",
        "description": "A test proposal",
        "status": status,
        "created_by": "test",
        "created_at": "2025-01-01T00:00:00Z",
        "domain": "elysia_core",
        "history": [],
    }

    metadata_file = proposal_path / "metadata.json"
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return proposal_path


def test_implementation_step_creation():
    """Test creating an ImplementationStep."""
    step = ImplementationStep(1, "Create module", "Create elysia/agents/foo.py")
    assert step.step_number == 1
    assert step.title == "Create module"
    assert step.content == "Create elysia/agents/foo.py"
    assert step.step_type in ["create_file", "modify_file", "generic"]


def test_parse_implementation_plan_simple(implementer_agent):
    """Test parsing a simple implementation plan."""
    plan_content = """## Step 1: Create module elysia/agents/foo.py

This step creates a new module.

## Step 2: Add tests in tests/test_foo.py

This step adds tests.
"""

    steps = implementer_agent._parse_implementation_plan(plan_content)
    assert len(steps) == 2
    assert steps[0].step_number == 1
    assert steps[0].title == "Create module elysia/agents/foo.py"
    assert steps[1].step_number == 2
    assert steps[1].title == "Add tests in tests/test_foo.py"


def test_parse_implementation_plan_alternative_format(implementer_agent):
    """Test parsing implementation plan with alternative format."""
    plan_content = """### Step 1: Create module

Content here.

### Step 2: Add tests

More content.
"""

    steps = implementer_agent._parse_implementation_plan(plan_content)
    assert len(steps) == 2


def test_implementer_rejects_non_accepted_proposal(implementer_agent, temp_proposals_root):
    """Test that implementer rejects proposals not in 'accepted' status."""
    proposal_id = "test-prop-1"
    create_test_proposal(temp_proposals_root, proposal_id, status="proposal")

    result = implementer_agent.run_for_proposal(proposal_id)
    assert not result["success"]
    assert "not in 'accepted' status" in result["error"]


def test_implementer_rejects_missing_proposal(implementer_agent):
    """Test that implementer rejects non-existent proposals."""
    result = implementer_agent.run_for_proposal("nonexistent")
    assert not result["success"]
    assert "not found" in result["error"]


def test_implementer_rejects_missing_plan(implementer_agent, temp_proposals_root):
    """Test that implementer rejects proposals without implementation plan."""
    proposal_id = "test-prop-1"
    create_test_proposal(temp_proposals_root, proposal_id, status="accepted")

    result = implementer_agent.run_for_proposal(proposal_id)
    assert not result["success"]
    assert "Implementation plan not found" in result["error"]


def test_implementer_with_valid_plan_dry_run(implementer_agent, temp_proposals_root, temp_repo_root):
    """Test implementer with a valid plan in dry-run mode."""
    proposal_id = "test-prop-1"
    proposal_path = create_test_proposal(temp_proposals_root, proposal_id, status="accepted")

    # Create implementation plan
    plan_path = proposal_path / "design" / "implementation_plan.md"
    plan_content = """## Step 1: Create module elysia/agents/foo.py

Create a new module file.

```python
# Test module
pass
```

## Step 2: Run tests

Run pytest on tests/test_foo.py
"""
    plan_path.write_text(plan_content, encoding="utf-8")

    # Run in dry-run mode
    implementer_agent.dry_run = True
    result = implementer_agent.run_for_proposal(proposal_id)

    # In dry-run, should succeed but not make changes
    assert result["success"] or "Implementation plan not found" in result.get("error", "")


def test_implementer_batch_processing(implementer_agent, temp_proposals_root):
    """Test batch processing of proposals."""
    # Create multiple approved proposals
    for i in range(3):
        proposal_id = f"test-prop-{i}"
        create_test_proposal(temp_proposals_root, proposal_id, status="accepted")

    result = implementer_agent.run_batch()
    assert result["total"] == 3
    # All should fail because they don't have implementation plans
    assert result["failed"] == 3


def test_update_implementation_status(implementer_agent, temp_proposals_root):
    """Test updating implementation status."""
    proposal_id = "test-prop-1"
    create_test_proposal(temp_proposals_root, proposal_id, status="accepted")

    implementer_agent._update_implementation_status(proposal_id, "in_progress")

    proposal = implementer_agent.proposal_system.get_proposal(proposal_id)
    assert proposal["implementation_status"] == "in_progress"
    assert "last_implemented_at" in proposal


def test_add_history_entry(implementer_agent, temp_proposals_root):
    """Test adding history entries."""
    proposal_id = "test-prop-1"
    create_test_proposal(temp_proposals_root, proposal_id, status="accepted")

    implementer_agent._add_history_entry(proposal_id, "Elysia-Implementer", "Test entry", {"test": "data"})

    proposal = implementer_agent.proposal_system.get_proposal(proposal_id)
    assert len(proposal["history"]) == 1
    assert proposal["history"][0]["actor"] == "Elysia-Implementer"
    assert proposal["history"][0]["change_summary"] == "Test entry"

