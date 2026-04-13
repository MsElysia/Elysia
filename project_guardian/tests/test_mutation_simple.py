# Simple mutation test to verify basic functionality
import pytest
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from project_guardian.mutation_engine import MutationEngine, MutationStatus


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

