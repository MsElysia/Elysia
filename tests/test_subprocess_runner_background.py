"""
SubprocessRunner Background Mode Tests
======================================
Tests for SubprocessRunner.run_command_background() method.
"""

import pytest
import subprocess
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

try:
    from project_guardian.subprocess_runner import SubprocessRunner
    from project_guardian.external import TrustDeniedError, TrustReviewRequiredError
    from project_guardian.trust import TrustMatrix, TrustDecision, SUBPROCESS_EXECUTION
    from project_guardian.review_queue import ReviewQueue
    from project_guardian.approval_store import ApprovalStore
    from project_guardian.memory import MemoryCore
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    pytestmark = pytest.mark.skip("Required modules not available")


class TestSubprocessRunnerBackground:
    """Test SubprocessRunner.run_command_background() method"""
    
    @pytest.fixture
    def memory(self):
        """Create MemoryCore instance"""
        return MemoryCore()
    
    @pytest.fixture
    def trust_matrix(self):
        """Create TrustMatrix that allows all actions"""
        trust = TrustMatrix()
        trust.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=True,
            decision="allow",
            reason_code="ALLOWED",
            message="Test allow",
            risk_score=0.1
        ))
        return trust
    
    @pytest.fixture
    def review_queue(self):
        """Create ReviewQueue"""
        return ReviewQueue()
    
    @pytest.fixture
    def approval_store(self):
        """Create ApprovalStore"""
        return ApprovalStore()
    
    @pytest.fixture
    def subprocess_runner(self, memory, trust_matrix, review_queue, approval_store):
        """Create SubprocessRunner instance"""
        return SubprocessRunner(memory, trust_matrix, review_queue, approval_store)
    
    def test_background_deny_raises_exception(self, subprocess_runner):
        """Verify deny decision raises TrustDeniedError"""
        # Mock TrustMatrix to return deny
        subprocess_runner.trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="deny",
            reason_code="DENIED",
            message="Test deny",
            risk_score=0.9
        ))
        
        with pytest.raises(TrustDeniedError) as exc_info:
            subprocess_runner.run_command_background(
                command=["echo", "test"],
                caller_identity="Test",
                task_id=None
            )
        
        assert exc_info.value.reason == "DENIED"
        assert SUBPROCESS_EXECUTION in str(exc_info.value)
    
    def test_background_review_enqueues_and_raises(self, subprocess_runner, review_queue):
        """Verify review decision enqueues request and raises TrustReviewRequiredError"""
        # Mock TrustMatrix to return review
        subprocess_runner.trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="review",
            reason_code="REVIEW_REQUIRED",
            message="Test review",
            risk_score=0.6
        ))
        
        with pytest.raises(TrustReviewRequiredError) as exc_info:
            subprocess_runner.run_command_background(
                command=["echo", "test"],
                caller_identity="Test",
                task_id=None
            )
        
        assert exc_info.value.request_id is not None
        # Verify request was enqueued
        pending = review_queue.list_pending()
        assert len(pending) > 0
        assert any(r.request_id == exc_info.value.request_id for r in pending)
    
    def test_background_replay_approval_bypasses_review(self, subprocess_runner, approval_store):
        """Verify approved request_id bypasses review and proceeds"""
        request_id = "test-request-123"
        context = {
            "component": "SubprocessRunner",
            "action": SUBPROCESS_EXECUTION,
            "target": "echo",
            "args": 1,
            "background": True,
            "caller_identity": "Test",
            "task_id": "none"
        }
        
        # Pre-approve the request
        approval_store.approve(request_id, context, approver="test", notes="Test approval")
        
        # Mock subprocess.Popen to avoid real subprocess execution
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll = Mock(return_value=None)  # Still running
        
        with patch('subprocess.Popen', return_value=mock_process):
            result = subprocess_runner.run_command_background(
                command=["echo", "test"],
                caller_identity="Test",
                task_id=None,
                request_id=request_id
            )
        
        # Should succeed without calling TrustMatrix (replay bypass)
        assert result["pid"] == 12345
        assert result["started"] == True
        assert "echo" in result["command"]
        # Verify TrustMatrix was not called (replay bypass)
        assert not subprocess_runner.trust_matrix.validate_trust_for_action.called
    
    def test_background_returns_pid_and_started(self, subprocess_runner):
        """Verify background mode returns pid and started flag"""
        # Mock subprocess.Popen
        mock_process = MagicMock()
        mock_process.pid = 9999
        mock_process.poll = Mock(return_value=None)  # Still running
        
        with patch('subprocess.Popen', return_value=mock_process):
            result = subprocess_runner.run_command_background(
                command=["sleep", "10"],
                caller_identity="Test",
                task_id=None
            )
        
        assert "pid" in result
        assert "started" in result
        assert "command" in result
        assert result["pid"] == 9999
        assert result["started"] == True
    
    def test_background_context_includes_background_flag(self, subprocess_runner):
        """Verify context passed to TrustMatrix includes background=True"""
        captured_context = {}
        
        def capture_context(component, action, context):
            captured_context.update(context)
            return TrustDecision(allowed=True, decision="allow", reason_code="ALLOWED", message="Test", risk_score=0.1)
        
        subprocess_runner.trust_matrix.validate_trust_for_action = Mock(side_effect=capture_context)
        
        # Mock subprocess.Popen
        mock_process = MagicMock()
        mock_process.pid = 123
        mock_process.poll = Mock(return_value=None)
        
        with patch('subprocess.Popen', return_value=mock_process):
            subprocess_runner.run_command_background(
                command=["test", "command"],
                caller_identity="Test",
                task_id="TASK-001"
            )
        
        # Verify context includes background flag
        assert captured_context["background"] == True
        assert captured_context["target"] == "test"
        assert captured_context["args"] == 1
        assert captured_context["caller_identity"] == "Test"
        assert captured_context["task_id"] == "TASK-001"
    
    def test_background_enforces_shell_false(self, subprocess_runner):
        """Verify background mode enforces shell=False (STRICTLY FORBIDDEN)"""
        # Mock subprocess.Popen to capture call
        with patch('subprocess.Popen') as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 123
            mock_process.poll = Mock(return_value=None)
            mock_popen.return_value = mock_process
            
            subprocess_runner.run_command_background(
                command=["echo", "test"],
                caller_identity="Test",
                task_id=None
            )
            
            # Verify Popen was called with shell=False
            call_kwargs = mock_popen.call_args[1]
            assert call_kwargs.get("shell") == False
