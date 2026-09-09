# Simple mutation test to verify basic functionality
import pytest
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from types import SimpleNamespace

from project_guardian.mutation_engine import MutationEngine, MutationStatus
from project_guardian.mutation_publisher import configure_mutation_publisher
from project_guardian.mutation_review_manager import configure_mutation_review_manager


def test_mutation_engine_basic():
    """Simple test: Can we create MutationEngine and propose a mutation?"""
    import tempfile
    import os
    
    # Create temp file for storage
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_path = f.name
    
    try:
        # Create engine
        engine = MutationEngine(storage_path=temp_path)
        assert engine is not None
        
        # Propose a simple mutation
        mutation_id = engine.propose_mutation(
            target_module="test_module.py",
            mutation_type="code_modification",
            description="Test mutation",
            proposed_code="def test(): return 42",
            original_code="def test(): return 0"
        )
        
        assert mutation_id is not None
        
        # Get proposal
        proposal = engine.get_proposal(mutation_id)
        assert proposal is not None
        assert proposal.status == MutationStatus.PENDING
        assert proposal.target_module == "test_module.py"
        
    finally:
        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def test_configure_mutation_publisher_requires_engine():
    with pytest.raises(ValueError, match="mutation_engine"):
        configure_mutation_publisher()


def test_configure_mutation_publisher_resolves_from_guardian(tmp_path):
    engine_path = str(tmp_path / "mut_store.json")
    engine = MutationEngine(storage_path=engine_path)
    guardian = SimpleNamespace(mutation_engine=engine)
    publisher = configure_mutation_publisher(guardian=guardian, codebase_path=str(tmp_path))
    assert publisher.mutation_engine is engine


def test_configure_mutation_review_manager_requires_engine():
    with pytest.raises(ValueError, match="mutation_engine"):
        configure_mutation_review_manager()


def test_configure_mutation_review_manager_resolves_from_guardian(tmp_path):
    engine_path = str(tmp_path / "mut_store2.json")
    engine = MutationEngine(storage_path=engine_path)
    guardian = SimpleNamespace(mutation_engine=engine)
    reviews_path = str(tmp_path / "mutation_reviews.json")
    mgr = configure_mutation_review_manager(guardian=guardian, storage_path=reviews_path)
    assert mgr.mutation_engine is engine


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

