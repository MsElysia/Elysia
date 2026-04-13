"""
WebReader POST/JSON Tests
========================
Tests for WebReader.request_json() method (POST/PUT/JSON support).
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

try:
    from project_guardian.external import WebReader, TrustDeniedError, TrustReviewRequiredError
    from project_guardian.trust import TrustMatrix, TrustDecision, NETWORK_ACCESS
    from project_guardian.review_queue import ReviewQueue
    from project_guardian.approval_store import ApprovalStore
    from project_guardian.memory import MemoryCore
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    pytestmark = pytest.mark.skip("Required modules not available")


class TestWebReaderRequestJson:
    """Test WebReader.request_json() method"""
    
    @pytest.fixture
    def memory(self):
        """Create MemoryCore instance"""
        return MemoryCore()
    
    @pytest.fixture
    def trust_matrix(self):
        """Create TrustMatrix that allows all actions"""
        trust = TrustMatrix()
        # Mock to allow all actions by default
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
    def web_reader(self, memory, trust_matrix, review_queue, approval_store):
        """Create WebReader instance"""
        return WebReader(memory, trust_matrix, review_queue, approval_store)
    
    def test_request_json_deny_raises_exception(self, web_reader):
        """Verify deny decision raises TrustDeniedError"""
        # Mock TrustMatrix to return deny
        web_reader.trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="deny",
            reason_code="DENIED",
            message="Test deny",
            risk_score=0.9
        ))
        
        with pytest.raises(TrustDeniedError) as exc_info:
            web_reader.request_json(
                method="POST",
                url="https://api.example.com/test",
                json_body={"test": "data"},
                caller_identity="Test",
                task_id=None
            )
        
        assert exc_info.value.reason == "DENIED"
        assert NETWORK_ACCESS in str(exc_info.value)
    
    def test_request_json_review_enqueues_and_raises(self, web_reader, review_queue):
        """Verify review decision enqueues request and raises TrustReviewRequiredError"""
        # Mock TrustMatrix to return review
        web_reader.trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="review",
            reason_code="REVIEW_REQUIRED",
            message="Test review",
            risk_score=0.6
        ))
        
        with pytest.raises(TrustReviewRequiredError) as exc_info:
            web_reader.request_json(
                method="POST",
                url="https://api.example.com/test",
                json_body={"test": "data"},
                caller_identity="Test",
                task_id=None
            )
        
        assert exc_info.value.request_id is not None
        # Verify request was enqueued
        pending = review_queue.list_pending()
        assert len(pending) > 0
        assert any(r.request_id == exc_info.value.request_id for r in pending)
    
    def test_request_json_replay_approval_bypasses_review(self, web_reader, approval_store):
        """Verify approved request_id bypasses review and proceeds"""
        request_id = "test-request-123"
        context = {
            "component": "WebReader",
            "action": NETWORK_ACCESS,
            "target": "api.example.com",
            "method": "POST",
            "has_body": True,
            "content_type": "json",
            "caller_identity": "Test",
            "task_id": "none"
        }
        
        # Pre-approve the request
        approval_store.approve(request_id, context, approver="test", notes="Test approval")
        
        # Mock urllib.request.urlopen to avoid real network call
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.read.return_value = b'{"success": true}'
        
        with patch('urllib.request.urlopen', return_value=mock_response):
            result = web_reader.request_json(
                method="POST",
                url="https://api.example.com/test",
                json_body={"test": "data"},
                caller_identity="Test",
                task_id=None,
                request_id=request_id
            )
        
        # Should succeed without calling TrustMatrix (replay bypass)
        assert result["status_code"] == 200
        assert result["json"] == {"success": True}
        # Verify TrustMatrix was not called (replay bypass)
        assert not web_reader.trust_matrix.validate_trust_for_action.called
    
    def test_request_json_context_includes_method_and_target(self, web_reader):
        """Verify context passed to TrustMatrix includes method, target domain, has_body"""
        captured_context = {}
        
        def capture_context(component, action, context):
            captured_context.update(context)
            return TrustDecision(allowed=True, decision="allow", reason_code="ALLOWED", message="Test", risk_score=0.1)
        
        web_reader.trust_matrix.validate_trust_for_action = Mock(side_effect=capture_context)
        
        # Mock urllib to avoid real network call
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.headers = {}
        mock_response.read.return_value = b'OK'
        
        with patch('urllib.request.urlopen', return_value=mock_response):
            web_reader.request_json(
                method="POST",
                url="https://api.example.com/v1/data",
                json_body={"key": "value"},
                caller_identity="Test",
                task_id="TASK-001"
            )
        
        # Verify context
        assert captured_context["method"] == "POST"
        assert captured_context["target"] == "api.example.com"  # Domain only, not full URL
        assert captured_context["has_body"] == True
        assert captured_context["content_type"] == "json"
        assert captured_context["caller_identity"] == "Test"
        assert captured_context["task_id"] == "TASK-001"
    
    def test_request_json_parses_json_response(self, web_reader):
        """Verify JSON response is parsed correctly"""
        # Mock urllib
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.read.return_value = b'{"result": "success", "data": [1, 2, 3]}'
        
        with patch('urllib.request.urlopen', return_value=mock_response):
            result = web_reader.request_json(
                method="GET",
                url="https://api.example.com/data",
                caller_identity="Test",
                task_id=None
            )
        
        assert result["status_code"] == 200
        assert result["json"] == {"result": "success", "data": [1, 2, 3]}
        assert result["text"] is None  # JSON parsed, text is None
    
    def test_request_json_handles_http_errors(self, web_reader):
        """Verify HTTP errors (4xx, 5xx) are handled gracefully"""
        import urllib.error
        
        # Mock HTTPError
        mock_error = urllib.error.HTTPError(
            "https://api.example.com/test",
            404,
            "Not Found",
            {},
            None
        )
        mock_error.read = Mock(return_value=b'{"error": "not found"}')
        mock_error.headers = {}
        
        with patch('urllib.request.urlopen', side_effect=mock_error):
            result = web_reader.request_json(
                method="GET",
                url="https://api.example.com/test",
                caller_identity="Test",
                task_id=None
            )
        
        assert result["status_code"] == 404
        assert result["json"] == {"error": "not found"}
