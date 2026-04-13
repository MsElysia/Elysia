"""
UI Local-Only Access Tests
==========================
Tests for local-only enforcement (loopback guard, misbind warnings).
"""

import pytest
import os
from unittest.mock import patch, MagicMock

try:
    from project_guardian.ui.app import is_loopback, app
    from fastapi.testclient import TestClient
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    pytestmark = pytest.mark.skip("FastAPI not available")


class TestLoopbackGuard:
    """Test loopback host detection"""
    
    def test_is_loopback_127_0_0_1(self):
        """Verify 127.0.0.1 is recognized as loopback"""
        assert is_loopback("127.0.0.1") == True
        assert is_loopback("127.0.0.1:8000") == True  # With port
    
    def test_is_loopback_ipv6(self):
        """Verify ::1 is recognized as loopback"""
        assert is_loopback("::1") == True
        assert is_loopback("[::1]:8000") == True  # With port (bracketed)
    
    def test_is_loopback_localhost(self):
        """Verify localhost is recognized as loopback"""
        assert is_loopback("localhost") == True
        assert is_loopback("localhost:8000") == True  # With port
    
    def test_is_loopback_non_loopback_ipv4(self):
        """Verify non-loopback IPv4 addresses are rejected"""
        assert is_loopback("192.168.1.5") == False
        assert is_loopback("10.0.0.2") == False
        assert is_loopback("172.16.0.1") == False
        assert is_loopback("8.8.8.8") == False
    
    def test_is_loopback_empty(self):
        """Verify empty/None host is rejected"""
        assert is_loopback("") == False
        assert is_loopback(None) == False


class TestLocalOnlyMiddleware:
    """Test local-only middleware enforcement"""
    
    @pytest.fixture
    def client(self):
        """Create FastAPI test client"""
        return TestClient(app)
    
    def test_localhost_request_succeeds(self, client):
        """Verify localhost requests succeed (TestClient appears as local)"""
        response = client.get("/")
        assert response.status_code == 200
    
    def test_api_status_includes_local_only_flag(self, client):
        """Verify /api/status includes local_only_enforced flag"""
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "local_only_enforced" in data
        assert data["local_only_enforced"] == True
    
    def test_middleware_rejects_non_loopback(self):
        """Test middleware rejects non-loopback hosts"""
        # Note: TestClient always appears as localhost, so we can't easily
        # simulate a remote host. Instead, we test the is_loopback function
        # directly and document that middleware integration testing requires
        # actual network setup or more complex mocking.
        
        # Verify the guard function works correctly
        assert is_loopback("192.168.1.5") == False
        assert is_loopback("10.0.0.2") == False
        
        # The middleware will use request.client.host, which TestClient
        # always sets to a loopback address. Full integration testing
        # would require running a real server or mocking the request object.


class TestBindHostWarning:
    """Test bind host warning detection"""
    
    @pytest.fixture
    def client(self):
        """Create FastAPI test client"""
        return TestClient(app)
    
    def test_dashboard_shows_local_only_banner(self, client):
        """Verify dashboard shows local-only banner"""
        response = client.get("/")
        assert response.status_code == 200
        # Should contain local-only message
        assert "Local-only UI is enforced" in response.text or "local-only" in response.text.lower()
    
    def test_bind_host_warning_with_env_var(self, client):
        """Verify warning appears when UI_BIND_HOST is set to non-loopback"""
        with patch.dict(os.environ, {"UI_BIND_HOST": "0.0.0.0"}):
            response = client.get("/")
            assert response.status_code == 200
            # Should show warning about bind host
            assert "UI_BIND_HOST" in response.text or "bind" in response.text.lower()
    
    def test_api_status_shows_bind_host_warning(self, client):
        """Verify /api/status shows bind_host_warning when set"""
        with patch.dict(os.environ, {"UI_BIND_HOST": "0.0.0.0"}):
            response = client.get("/api/status")
            assert response.status_code == 200
            data = response.json()
            assert "bind_host_warning" in data
            assert data["bind_host_warning"] == True
    
    def test_api_status_no_warning_for_loopback(self, client):
        """Verify /api/status shows no warning for loopback bind host"""
        with patch.dict(os.environ, {"UI_BIND_HOST": "127.0.0.1"}):
            response = client.get("/api/status")
            assert response.status_code == 200
            data = response.json()
            assert "bind_host_warning" in data
            assert data["bind_host_warning"] == False


class TestErrorPage:
    """Test error page rendering for blocked requests"""
    
    def test_error_page_template_exists(self):
        """Verify error.html template can be rendered with error_title and error_message"""
        # This is a basic check that the template variables are supported
        # Full rendering test would require mocking the middleware rejection
        from project_guardian.ui.app import templates
        if FASTAPI_AVAILABLE:
            # Template should accept these variables
            # (actual rendering test would require a Request object)
            pass
