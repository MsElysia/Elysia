"""
WebReader Target Validation Tests
=================================
Tests for SSRF safety floor (scheme validation + internal target blocking).
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
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    pytestmark = pytest.mark.skip("Required modules not available")


class TestWebReaderTargetValidation:
    """Test WebReader SSRF safety floor"""
    
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
    def web_reader(self, memory, trust_matrix, review_queue, approval_store):
        """Create WebReader instance"""
        return WebReader(memory, trust_matrix, review_queue, approval_store)
    
    def test_scheme_validation_file_denied(self, web_reader):
        """Verify file:// scheme is denied"""
        with pytest.raises(TrustDeniedError) as exc_info:
            web_reader.fetch("file:///etc/passwd")
        
        assert exc_info.value.reason == "UNSUPPORTED_URL_SCHEME"
        assert "file" in str(exc_info.value).lower()
    
    def test_scheme_validation_missing_scheme_denied(self, web_reader):
        """Verify missing scheme is denied"""
        with pytest.raises(TrustDeniedError) as exc_info:
            web_reader.fetch("example.com/path")
        
        assert exc_info.value.reason == "UNSUPPORTED_URL_SCHEME"
    
    def test_scheme_validation_http_allowed(self, web_reader):
        """Verify http:// scheme is allowed"""
        # Mock network call
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        
        with patch.object(web_reader.session, 'get', return_value=mock_response):
            result = web_reader.fetch("http://example.com/")
            assert result is not None
    
    def test_scheme_validation_https_allowed(self, web_reader):
        """Verify https:// scheme is allowed"""
        # Mock network call
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        
        with patch.object(web_reader.session, 'get', return_value=mock_response):
            result = web_reader.fetch("https://example.com/")
            assert result is not None
    
    def test_internal_ip_loopback_blocked(self, web_reader):
        """Verify 127.0.0.1 is blocked by default"""
        with pytest.raises(TrustDeniedError) as exc_info:
            web_reader.fetch("http://127.0.0.1/")
        
        assert exc_info.value.reason == "TARGET_BLOCKED_INTERNAL"
        assert "127.0.0.1" in str(exc_info.value)
    
    def test_internal_ip_link_local_blocked(self, web_reader):
        """Verify 169.254.169.254 (cloud metadata) is blocked"""
        with pytest.raises(TrustDeniedError) as exc_info:
            web_reader.fetch("http://169.254.169.254/latest/meta-data/")
        
        assert exc_info.value.reason == "TARGET_BLOCKED_INTERNAL"
    
    def test_internal_ip_private_blocked(self, web_reader):
        """Verify 192.168.1.10 (private IP) is blocked"""
        with pytest.raises(TrustDeniedError) as exc_info:
            web_reader.fetch("http://192.168.1.10/")
        
        assert exc_info.value.reason == "TARGET_BLOCKED_INTERNAL"
    
    def test_internal_ip_10_blocked(self, web_reader):
        """Verify 10.0.0.1 (private IP) is blocked"""
        with pytest.raises(TrustDeniedError) as exc_info:
            web_reader.fetch("http://10.0.0.1/")
        
        assert exc_info.value.reason == "TARGET_BLOCKED_INTERNAL"
    
    def test_internal_ip_172_blocked(self, web_reader):
        """Verify 172.16.0.1 (private IP) is blocked"""
        with pytest.raises(TrustDeniedError) as exc_info:
            web_reader.fetch("http://172.16.0.1/")
        
        assert exc_info.value.reason == "TARGET_BLOCKED_INTERNAL"
    
    def test_internal_hostname_localhost_blocked(self, web_reader):
        """Verify localhost hostname is blocked"""
        with pytest.raises(TrustDeniedError) as exc_info:
            web_reader.fetch("http://localhost/")
        
        assert exc_info.value.reason == "TARGET_BLOCKED_INTERNAL"
    
    def test_internal_hostname_local_blocked(self, web_reader):
        """Verify .local hostname is blocked"""
        with pytest.raises(TrustDeniedError) as exc_info:
            web_reader.fetch("http://printer.local/")
        
        assert exc_info.value.reason == "TARGET_BLOCKED_INTERNAL"
    
    def test_external_host_allowed_with_trustmatrix_allow(self, web_reader):
        """Verify external host is allowed when TrustMatrix allows"""
        # Mock network call
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        
        with patch.object(web_reader.session, 'get', return_value=mock_response):
            result = web_reader.fetch("https://example.com/")
            assert result is not None
    
    def test_external_host_denied_with_trustmatrix_deny(self, web_reader):
        """Verify external host is denied when TrustMatrix denies"""
        # Mock TrustMatrix to return deny
        web_reader.trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="deny",
            reason_code="DENIED",
            message="Test deny",
            risk_score=0.9
        ))
        
        with pytest.raises(TrustDeniedError) as exc_info:
            web_reader.fetch("https://example.com/")
        
        assert exc_info.value.reason == "DENIED"
        assert NETWORK_ACCESS in str(exc_info.value)
    
    def test_allow_internal_with_trustmatrix_deny_still_denied(self, web_reader):
        """Verify allow_internal=True with TrustMatrix deny still denies"""
        # Mock TrustMatrix to return deny
        web_reader.trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="deny",
            reason_code="DENIED",
            message="Test deny",
            risk_score=0.9
        ))
        
        with pytest.raises(TrustDeniedError) as exc_info:
            web_reader.fetch("http://127.0.0.1/", allow_internal=True)
        
        assert exc_info.value.reason == "DENIED"
    
    def test_allow_internal_with_trustmatrix_review_enqueues(self, web_reader, review_queue):
        """Verify allow_internal=True with TrustMatrix review enqueues request"""
        # Mock TrustMatrix to return review
        web_reader.trust_matrix.validate_trust_for_action = Mock(return_value=TrustDecision(
            allowed=False,
            decision="review",
            reason_code="REVIEW_REQUIRED",
            message="Test review",
            risk_score=0.6
        ))
        
        with pytest.raises(TrustReviewRequiredError) as exc_info:
            web_reader.fetch("http://127.0.0.1/", allow_internal=True)
        
        assert exc_info.value.request_id is not None
        # Verify request was enqueued
        pending = review_queue.list_pending()
        assert len(pending) > 0
        assert any(r.request_id == exc_info.value.request_id for r in pending)
    
    def test_allow_internal_with_trustmatrix_allow_proceeds(self, web_reader):
        """Verify allow_internal=True with TrustMatrix allow proceeds"""
        # Mock network call
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        
        with patch.object(web_reader.session, 'get', return_value=mock_response):
            result = web_reader.fetch("http://127.0.0.1/", allow_internal=True)
            assert result is not None
    
    def test_request_json_scheme_validation(self, web_reader):
        """Verify request_json also validates scheme"""
        with pytest.raises(TrustDeniedError) as exc_info:
            web_reader.request_json(method="POST", url="file:///etc/passwd", json_body={"test": "data"})
        
        assert exc_info.value.reason == "UNSUPPORTED_URL_SCHEME"
    
    def test_request_json_internal_ip_blocked(self, web_reader):
        """Verify request_json blocks internal IPs"""
        with pytest.raises(TrustDeniedError) as exc_info:
            web_reader.request_json(method="POST", url="http://192.168.1.10/api", json_body={"test": "data"})
        
        assert exc_info.value.reason == "TARGET_BLOCKED_INTERNAL"
    
    def test_request_json_allow_internal_with_review(self, web_reader, review_queue):
        """Verify request_json allow_internal requires review"""
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
                url="http://localhost/api",
                json_body={"test": "data"},
                allow_internal=True
            )
        
        assert exc_info.value.request_id is not None
    
    def test_request_json_allow_internal_with_allow_proceeds(self, web_reader):
        """Verify request_json allow_internal with allow proceeds"""
        # Mock urllib
        mock_response = MagicMock()
        mock_response.getcode.return_value = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.read.return_value = b'{"success": true}'
        
        with patch('urllib.request.urlopen', return_value=mock_response):
            result = web_reader.request_json(
                method="POST",
                url="http://127.0.0.1/api",
                json_body={"test": "data"},
                allow_internal=True
            )
        
        assert result["status_code"] == 200
        assert result["json"] == {"success": True}
    
    def test_context_includes_scheme_and_allow_internal(self, web_reader):
        """Verify context passed to TrustMatrix includes scheme and allow_internal"""
        captured_context = {}
        
        def capture_context(component, action, context):
            captured_context.update(context)
            return TrustDecision(allowed=True, decision="allow", reason_code="ALLOWED", message="Test", risk_score=0.1)
        
        web_reader.trust_matrix.validate_trust_for_action = Mock(side_effect=capture_context)
        
        # Mock network call
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        
        with patch.object(web_reader.session, 'get', return_value=mock_response):
            web_reader.fetch("https://example.com/", allow_internal=False)
        
        # Verify context
        assert captured_context["scheme"] == "https"
        assert captured_context["allow_internal"] == False
        assert captured_context["target"] == "example.com"
        assert captured_context["method"] == "GET"
    
    def test_context_includes_blocked_reason_for_internal(self, web_reader):
        """Verify context includes blocked_reason for internal targets with allow_internal"""
        captured_context = {}
        
        def capture_context(component, action, context):
            captured_context.update(context)
            return TrustDecision(allowed=True, decision="allow", reason_code="ALLOWED", message="Test", risk_score=0.1)
        
        web_reader.trust_matrix.validate_trust_for_action = Mock(side_effect=capture_context)
        
        # Mock network call
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        
        with patch.object(web_reader.session, 'get', return_value=mock_response):
            web_reader.fetch("http://127.0.0.1/", allow_internal=True)
        
        # Verify context includes blocked_reason
        assert captured_context["blocked_reason"] == "TARGET_BLOCKED_INTERNAL"
        assert captured_context["allow_internal"] == True
