"""
No Side-Effects Tests: Subprocess Operations
=============================================
Tests that deny/review decisions for subprocess operations create no side-effects.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

try:
    from project_guardian.subprocess_runner import SubprocessRunner
    from project_guardian.external import TrustDeniedError, TrustReviewRequiredError
    from project_guardian.trust import TrustMatrix, TrustDecision, SUBPROCESS_EXECUTION
    from project_guardian.review_queue import ReviewQueue
    from project_guardian.approval_store import ApprovalStore
    from project_guardian.memory import MemoryCore
    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False
    pytestmark = pytest.mark.skip("Required modules not available")


class TestNoSideEffectsSubprocess:
    """Test that subprocess deny/review decisions create no side-effects"""
    
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
    
    @pytest.fixture
    def tmp_reports_dir(self, tmp_path):
        """Create temporary REPORTS directory"""
        reports_dir = tmp_path / "REPORTS"
        reports_dir.mkdir()
        return reports_dir
    
    def test_subprocess_review_no_launch_no_audit(self, memory, review_queue, approval_store, tmp_reports_dir):
        """Verify subprocess review does not launch process or write audit"""
        # Create TrustMatrix that returns review
        trust_matrix = Mock(spec=TrustMatrix)
        trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="review",
            reason_code="REVIEW_REQUIRED",
            message="Test review",
            risk_score=0.6
        ))
        
        subprocess_runner = SubprocessRunner(
            memory,
            trust_matrix,
            review_queue,
            approval_store,
            reports_dir=str(tmp_reports_dir)
        )
        
        # Mock subprocess.Popen to track if it's called
        with patch('subprocess.Popen') as mock_popen:
            # Try to run background command (should require review)
            with pytest.raises(TrustReviewRequiredError) as exc_info:
                subprocess_runner.run_command_background(
                    command=["echo", "test"],
                    caller_identity="TestCaller",
                    task_id="TASK-001"
                )
            
            # Verify review required
            assert exc_info.value.request_id is not None
            
            # Verify ReviewQueue has 1 pending request
            pending = review_queue.get_pending()
            assert len(pending) == 1
            assert pending[0].request_id == exc_info.value.request_id
            
            # Verify subprocess.Popen was NOT called
            mock_popen.assert_not_called()
            
            # Verify audit log does not exist or is empty
            audit_path = tmp_reports_dir / "subprocess_background.jsonl"
            if audit_path.exists():
                content = audit_path.read_text(encoding='utf-8').strip()
                assert content == ""
            else:
                assert True  # File not created (also acceptable)
    
    def test_subprocess_deny_no_launch_no_audit(self, memory, review_queue, approval_store, tmp_reports_dir):
        """Verify subprocess deny does not launch process or write audit"""
        # Create TrustMatrix that returns deny
        trust_matrix = Mock(spec=TrustMatrix)
        trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="deny",
            reason_code="DENIED",
            message="Test deny",
            risk_score=0.9
        ))
        
        subprocess_runner = SubprocessRunner(
            memory,
            trust_matrix,
            review_queue,
            approval_store,
            reports_dir=str(tmp_reports_dir)
        )
        
        # Mock subprocess.Popen to track if it's called
        with patch('subprocess.Popen') as mock_popen:
            # Try to run background command (should be denied)
            with pytest.raises(TrustDeniedError) as exc_info:
                subprocess_runner.run_command_background(
                    command=["echo", "test"],
                    caller_identity="TestCaller",
                    task_id="TASK-001"
                )
            
            # Verify denial
            assert exc_info.value.reason == "DENIED"
            
            # Verify subprocess.Popen was NOT called
            mock_popen.assert_not_called()
            
            # Verify audit log does not exist or is empty
            audit_path = tmp_reports_dir / "subprocess_background.jsonl"
            if audit_path.exists():
                content = audit_path.read_text(encoding='utf-8').strip()
                assert content == ""
            else:
                assert True  # File not created (also acceptable)
    
    def test_subprocess_sync_review_no_execution(self, memory, review_queue, approval_store):
        """Verify sync subprocess review does not execute"""
        # Create TrustMatrix that returns review
        trust_matrix = Mock(spec=TrustMatrix)
        trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="review",
            reason_code="REVIEW_REQUIRED",
            message="Test review",
            risk_score=0.6
        ))
        
        subprocess_runner = SubprocessRunner(
            memory,
            trust_matrix,
            review_queue,
            approval_store
        )
        
        # Mock subprocess.run to track if it's called
        with patch('subprocess.run') as mock_run:
            # Try to run command (should require review)
            with pytest.raises(TrustReviewRequiredError) as exc_info:
                subprocess_runner.run_command(
                    command=["echo", "test"],
                    caller_identity="TestCaller",
                    task_id="TASK-001"
                )
            
            # Verify review required
            assert exc_info.value.request_id is not None
            
            # Verify subprocess.run was NOT called
            mock_run.assert_not_called()
    
    def test_subprocess_sync_deny_no_execution(self, memory, review_queue, approval_store):
        """Verify sync subprocess deny does not execute"""
        # Create TrustMatrix that returns deny
        trust_matrix = Mock(spec=TrustMatrix)
        trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="deny",
            reason_code="DENIED",
            message="Test deny",
            risk_score=0.9
        ))
        
        subprocess_runner = SubprocessRunner(
            memory,
            trust_matrix,
            review_queue,
            approval_store
        )
        
        # Mock subprocess.run to track if it's called
        with patch('subprocess.run') as mock_run:
            # Try to run command (should be denied)
            with pytest.raises(TrustDeniedError) as exc_info:
                subprocess_runner.run_command(
                    command=["echo", "test"],
                    caller_identity="TestCaller",
                    task_id="TASK-001"
                )
            
            # Verify denial
            assert exc_info.value.reason == "DENIED"
            
            # Verify subprocess.run was NOT called
            mock_run.assert_not_called()
