"""
No Side-Effects Tests: Mutation Operations
===========================================
Tests that deny/review decisions for mutation operations create no side-effects.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

try:
    from project_guardian.mutation import MutationEngine, MutationDeniedError, MutationReviewRequiredError
    from project_guardian.trust import TrustMatrix, TrustDecision, GOVERNANCE_MUTATION
    from project_guardian.review_queue import ReviewQueue
    from project_guardian.approval_store import ApprovalStore
    from project_guardian.memory import MemoryCore
    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False
    pytestmark = pytest.mark.skip("Required modules not available")


class TestNoSideEffectsMutation:
    """Test that mutation deny/review decisions create no side-effects"""
    
    @pytest.fixture
    def memory(self):
        """Create MemoryCore instance"""
        return MemoryCore()
    
    @pytest.fixture
    def review_queue(self):
        """Create ReviewQueue"""
        return ReviewQueue()
    
    @pytest.fixture
    def approval_store(self):
        """Create ApprovalStore"""
        return ApprovalStore()
    
    def test_mutation_invalid_path_no_writes_no_backups(self, memory, review_queue, approval_store, tmp_path):
        """Verify invalid path mutation does not write or create backups"""
        # Create TrustMatrix that would allow (to ensure denial comes from path validation)
        trust_matrix = Mock(spec=TrustMatrix)
        trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=True,
            decision="allow",
            reason_code="ALLOWED",
            message="Test allow",
            risk_score=0.1
        ))
        
        mutation_engine = MutationEngine(
            memory,
            trust_matrix=trust_matrix,
            review_queue=review_queue,
            approval_store=approval_store,
            repo_root=tmp_path
        )
        
        # Create a safe file
        safe_file = tmp_path / "safe.txt"
        safe_file.write_text("A")
        original_content = safe_file.read_text()
        
        # Create backup directory (should remain empty)
        backup_dir = tmp_path / "guardian_backups"
        
        # Try to apply mutation with invalid path (traversal)
        with pytest.raises(MutationDeniedError) as exc_info:
            mutation_engine.apply(
                filename="../evil.txt",  # Invalid path (traversal)
                new_code="malicious content",
                caller_identity="TestCaller",
                task_id="TASK-001"
            )
        
        # Verify denial reason
        assert exc_info.value.reason == "PATH_TRAVERSAL_BLOCKED"
        
        # Verify safe file unchanged
        assert safe_file.read_text() == original_content
        
        # Verify no backup files created
        if backup_dir.exists():
            backups = list(backup_dir.rglob("*.bak.*"))
            assert len(backups) == 0
        else:
            assert True  # Backup directory not created (also acceptable)
    
    def test_mutation_review_no_writes_no_backups(self, memory, review_queue, approval_store, tmp_path):
        """Verify mutation review does not write or create backups"""
        # Create TrustMatrix that returns review
        trust_matrix = Mock(spec=TrustMatrix)
        trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="review",
            reason_code="REVIEW_REQUIRED",
            message="Test review",
            risk_score=0.6
        ))
        
        mutation_engine = MutationEngine(
            memory,
            trust_matrix=trust_matrix,
            review_queue=review_queue,
            approval_store=approval_store,
            repo_root=tmp_path
        )
        
        # Create a protected file (CONTROL.md)
        protected_file = tmp_path / "CONTROL.md"
        protected_file.write_text("CURRENT_TASK: TASK-0001\n")
        original_content = protected_file.read_text()
        
        # Create backup directory (should remain empty)
        backup_dir = tmp_path / "guardian_backups"
        
        # Try to apply mutation to protected file with override (should require review)
        with pytest.raises(MutationReviewRequiredError) as exc_info:
            mutation_engine.apply(
                filename="CONTROL.md",
                new_code="CURRENT_TASK: NONE\n",
                allow_governance_mutation=True,  # Override flag
                caller_identity="TestCaller",
                task_id="TASK-001"
            )
        
        # Verify review required
        assert exc_info.value.request_id is not None
        
        # Verify ReviewQueue has 1 pending request
        pending = review_queue.get_pending()
        assert len(pending) == 1
        assert pending[0].request_id == exc_info.value.request_id
        
        # Verify protected file unchanged
        assert protected_file.read_text() == original_content
        
        # Verify no backup files created
        if backup_dir.exists():
            backups = list(backup_dir.rglob("*.bak.*"))
            assert len(backups) == 0
        else:
            assert True  # Backup directory not created (also acceptable)
    
    def test_mutation_deny_no_writes_no_backups(self, memory, review_queue, approval_store, tmp_path):
        """Verify mutation deny does not write or create backups"""
        # Create TrustMatrix that returns deny
        trust_matrix = Mock(spec=TrustMatrix)
        trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="deny",
            reason_code="DENIED",
            message="Test deny",
            risk_score=0.9
        ))
        
        mutation_engine = MutationEngine(
            memory,
            trust_matrix=trust_matrix,
            review_queue=review_queue,
            approval_store=approval_store,
            repo_root=tmp_path
        )
        
        # Create a protected file (CONTROL.md)
        protected_file = tmp_path / "CONTROL.md"
        protected_file.write_text("CURRENT_TASK: TASK-0001\n")
        original_content = protected_file.read_text()
        
        # Create backup directory (should remain empty)
        backup_dir = tmp_path / "guardian_backups"
        
        # Try to apply mutation to protected file with override (should be denied)
        with pytest.raises(MutationDeniedError) as exc_info:
            mutation_engine.apply(
                filename="CONTROL.md",
                new_code="CURRENT_TASK: NONE\n",
                allow_governance_mutation=True,  # Override flag
                caller_identity="TestCaller",
                task_id="TASK-001"
            )
        
        # Verify denial
        assert exc_info.value.reason == "DENIED"
        
        # Verify protected file unchanged
        assert protected_file.read_text() == original_content
        
        # Verify no backup files created
        if backup_dir.exists():
            backups = list(backup_dir.rglob("*.bak.*"))
            assert len(backups) == 0
        else:
            assert True  # Backup directory not created (also acceptable)
    
    def test_mutation_protected_without_override_no_writes(self, memory, review_queue, approval_store, tmp_path):
        """Verify protected path without override does not write"""
        # Create TrustMatrix (should not be called for protected path without override)
        trust_matrix = Mock(spec=TrustMatrix)
        trust_matrix.validate_trust_for_action = Mock()
        
        mutation_engine = MutationEngine(
            memory,
            trust_matrix=trust_matrix,
            review_queue=review_queue,
            approval_store=approval_store,
            repo_root=tmp_path
        )
        
        # Create a protected file (CONTROL.md)
        protected_file = tmp_path / "CONTROL.md"
        protected_file.write_text("CURRENT_TASK: TASK-0001\n")
        original_content = protected_file.read_text()
        
        # Try to apply mutation without override (should be denied immediately)
        with pytest.raises(MutationDeniedError) as exc_info:
            mutation_engine.apply(
                filename="CONTROL.md",
                new_code="CURRENT_TASK: NONE\n",
                allow_governance_mutation=False,  # No override
                caller_identity="TestCaller",
                task_id="TASK-001"
            )
        
        # Verify denial reason
        assert exc_info.value.reason == "PROTECTED_PATH_WITHOUT_OVERRIDE"
        
        # Verify TrustMatrix was NOT called (denial happened before trust check)
        trust_matrix.validate_trust_for_action.assert_not_called()
        
        # Verify protected file unchanged
        assert protected_file.read_text() == original_content
