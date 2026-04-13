"""
No Side-Effects Tests: Network Operations
==========================================
Tests that deny/review decisions for network operations create no side-effects.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

try:
    from project_guardian.external import WebReader, TrustDeniedError, TrustReviewRequiredError
    from project_guardian.trust import TrustMatrix, TrustDecision, NETWORK_ACCESS
    from project_guardian.review_queue import ReviewQueue
    from project_guardian.approval_store import ApprovalStore
    from project_guardian.memory import MemoryCore
    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False
    pytestmark = pytest.mark.skip("Required modules not available")


class TestNoSideEffectsNetwork:
    """Test that network deny/review decisions create no side-effects"""
    
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
    
    def test_internal_target_denied_no_network_call(self, memory, review_queue, approval_store):
        """Verify SSRF denial (internal target) does not call network"""
        # Create TrustMatrix that would allow (to ensure denial comes from SSRF floor)
        trust_matrix = Mock(spec=TrustMatrix)
        trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=True,
            decision="allow",
            reason_code="ALLOWED",
            message="Test allow",
            risk_score=0.1
        ))
        
        web_reader = WebReader(
            memory,
            trust_matrix,
            review_queue,
            approval_store
        )
        
        # Mock urllib.request.urlopen to track if it's called
        with patch('urllib.request.urlopen') as mock_urlopen:
            # Try to access internal target (should be blocked by SSRF floor)
            with pytest.raises(TrustDeniedError) as exc_info:
                web_reader.request_json(
                    method="GET",
                    url="http://127.0.0.1/test",
                    allow_internal=False,
                    caller_identity="TestCaller",
                    task_id="TASK-001"
                )
            
            # Verify denial reason
            assert exc_info.value.reason == "TARGET_BLOCKED_INTERNAL"
            
            # Verify network was NOT called
            mock_urlopen.assert_not_called()
    
    def test_internal_target_review_override_enqueues_only(self, memory, review_queue, approval_store):
        """Verify internal target with review override enqueues but does not call network"""
        # Create TrustMatrix that returns review
        trust_matrix = Mock(spec=TrustMatrix)
        trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="review",
            reason_code="REVIEW_REQUIRED",
            message="Test review",
            risk_score=0.6
        ))
        
        web_reader = WebReader(
            memory,
            trust_matrix,
            review_queue,
            approval_store
        )
        
        # Mock urllib.request.urlopen to track if it's called
        with patch('urllib.request.urlopen') as mock_urlopen:
            # Try to access internal target with allow_internal=True (should require review)
            with pytest.raises(TrustReviewRequiredError) as exc_info:
                web_reader.request_json(
                    method="GET",
                    url="http://127.0.0.1/test",
                    allow_internal=True,  # Override flag
                    caller_identity="TestCaller",
                    task_id="TASK-001"
                )
            
            # Verify review required
            assert exc_info.value.request_id is not None
            
            # Verify ReviewQueue has 1 pending request
            pending = review_queue.get_pending()
            assert len(pending) == 1
            assert pending[0].request_id == exc_info.value.request_id
            
            # Verify network was NOT called
            mock_urlopen.assert_not_called()
    
    def test_external_target_denied_no_network_call(self, memory, review_queue, approval_store):
        """Verify external target denial does not call network"""
        # Create TrustMatrix that returns deny
        trust_matrix = Mock(spec=TrustMatrix)
        trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="deny",
            reason_code="DENIED",
            message="Test deny",
            risk_score=0.9
        ))
        
        web_reader = WebReader(
            memory,
            trust_matrix,
            review_queue,
            approval_store
        )
        
        # Mock urllib.request.urlopen to track if it's called
        with patch('urllib.request.urlopen') as mock_urlopen:
            # Try to access external target (should be denied by TrustMatrix)
            with pytest.raises(TrustDeniedError) as exc_info:
                web_reader.request_json(
                    method="GET",
                    url="http://example.com/test",
                    caller_identity="TestCaller",
                    task_id="TASK-001"
                )
            
            # Verify denial
            assert exc_info.value.reason == "DENIED"
            
            # Verify network was NOT called
            mock_urlopen.assert_not_called()
    
    def test_external_target_review_enqueues_only(self, memory, review_queue, approval_store):
        """Verify external target review enqueues but does not call network"""
        # Create TrustMatrix that returns review
        trust_matrix = Mock(spec=TrustMatrix)
        trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="review",
            reason_code="REVIEW_REQUIRED",
            message="Test review",
            risk_score=0.6
        ))
        
        web_reader = WebReader(
            memory,
            trust_matrix,
            review_queue,
            approval_store
        )
        
        # Mock urllib.request.urlopen to track if it's called
        with patch('urllib.request.urlopen') as mock_urlopen:
            # Try to access external target (should require review)
            with pytest.raises(TrustReviewRequiredError) as exc_info:
                web_reader.request_json(
                    method="GET",
                    url="http://example.com/test",
                    caller_identity="TestCaller",
                    task_id="TASK-001"
                )
            
            # Verify review required
            assert exc_info.value.request_id is not None
            
            # Verify ReviewQueue has 1 pending request
            pending = review_queue.get_pending()
            assert len(pending) == 1
            assert pending[0].request_id == exc_info.value.request_id
            
            # Verify network was NOT called
            mock_urlopen.assert_not_called()
