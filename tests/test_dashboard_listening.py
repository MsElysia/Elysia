"""
Tests for dashboard server listening and port fallback.

Tests:
1. Server starts and port is listening before browser open
2. Port fallback works when 5000 is occupied
3. Server error propagation works
"""

import pytest
import socket
import threading
import time
from unittest.mock import Mock, patch, MagicMock
from contextlib import contextmanager

import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "project_guardian"))


@pytest.fixture(autouse=True)
def reset_guard_between_tests():
    from tests._ui_isolated_loader import reset_dashboard_guard
    reset_dashboard_guard()
    yield
    reset_dashboard_guard()


@contextmanager
def mock_running_server(panel):
    """A successful server start must stay active until test cleanup."""
    release = threading.Event()
    with patch.object(panel, "socketio") as mock_socketio:
        mock_socketio.run.side_effect = lambda *a, **kw: release.wait(timeout=8)
        try:
            yield mock_socketio
        finally:
            release.set()
            deadline = time.monotonic() + 1
            while panel.running and time.monotonic() < deadline:
                time.sleep(0.01)


class TestDashboardListening:
    """Test dashboard server listening behavior."""
    
    def test_port_fallback_when_5000_occupied(self):
        """Test that port fallback works when port 5000 is occupied."""
        from tests._ui_isolated_loader import UIControlPanel
        
        occupied_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            occupied_socket.bind(('127.0.0.1', 5000))
            occupied_socket.listen(1)
            
            mock_orchestrator = Mock()
            ui_panel = UIControlPanel(orchestrator=mock_orchestrator, host='127.0.0.1', port=5000)
            
            with mock_running_server(ui_panel):
                with patch.object(ui_panel, '_wait_for_server_ready', return_value=True):
                    ui_panel.start(debug=False, source="test")
                    
                    assert ui_panel.port != 5000, "Port should have been changed from 5000"
                    assert ui_panel.port >= 5001, "Port should be >= 5001"
                    assert ui_panel._actual_port == ui_panel.port, "Actual port should match"
                    
        finally:
            occupied_socket.close()
    
    def test_rejected_port_is_not_rechecked_during_fallback(self):
        """A port rejected as occupied must not be chosen again on retry."""
        from tests._ui_isolated_loader import UIControlPanel

        panel = UIControlPanel(orchestrator=Mock(), host="127.0.0.1", port=5000)
        with mock_running_server(panel), \
             patch.object(panel, "_check_port_available", return_value=False), \
             patch.object(panel, "_find_available_port", return_value=5001) as find, \
             patch.object(panel, "_wait_for_server_ready", return_value=True):
            assert panel.start(source="occupied-port-race") is True
            find.assert_called_once_with(5001)
            assert panel.port == 5001

    def test_server_ready_before_browser_open(self):
        """Test that server is listening before browser open is called."""
        from tests._ui_isolated_loader import UIControlPanel
        
        mock_orchestrator = Mock()
        ui_panel = UIControlPanel(orchestrator=mock_orchestrator, host='127.0.0.1', port=5000)
        
        with mock_running_server(ui_panel):
            ready_called = []
            def mock_wait(timeout):
                ready_called.append(time.time())
                return True
            
            with patch.object(ui_panel, '_wait_for_server_ready', side_effect=mock_wait):
                with patch.object(ui_panel, '_check_port_available', return_value=True):
                    ui_panel.start(debug=False, source="test")
                    
                    assert len(ready_called) > 0, "_wait_for_server_ready should have been called"
                    assert ui_panel._server_ready.is_set(), "Server ready event should be set"
    
    def test_server_error_propagation(self):
        """Test that server errors are properly captured and propagated."""
        from tests._ui_isolated_loader import UIControlPanel
        
        mock_orchestrator = Mock()
        ui_panel = UIControlPanel(orchestrator=mock_orchestrator, host='127.0.0.1', port=5000)
        
        error_msg = "Port already in use"
        def mock_run(*args, **kwargs):
            raise OSError(error_msg)
        
        with patch.object(ui_panel, 'socketio') as mock_socketio:
            mock_socketio.run = mock_run
            
            with patch.object(ui_panel, '_check_port_available', return_value=True):
                with patch.object(ui_panel, '_wait_for_server_ready', return_value=False):
                    with pytest.raises(RuntimeError):
                        ui_panel.start(debug=False, source="test")
                    
                    time.sleep(0.5)
                    assert ui_panel._server_error is not None, "Server error should be set"
                    assert error_msg in ui_panel._server_error or "already in use" in ui_panel._server_error.lower()
    
    def test_actual_port_stored_correctly(self):
        """Test that _actual_port is stored correctly."""
        from tests._ui_isolated_loader import UIControlPanel
        
        mock_orchestrator = Mock()
        ui_panel = UIControlPanel(orchestrator=mock_orchestrator, host='127.0.0.1', port=5000)
        
        with mock_running_server(ui_panel):
            with patch.object(ui_panel, '_check_port_available', return_value=True):
                with patch.object(ui_panel, '_wait_for_server_ready', return_value=True):
                    ui_panel.start(debug=False, source="test")
                    
                    assert ui_panel._actual_port is not None, "_actual_port should be set"
                    assert ui_panel._actual_port == ui_panel.port, "_actual_port should match port"
    
    def test_port_availability_check(self):
        """Test that _check_port_available works correctly."""
        from tests._ui_isolated_loader import UIControlPanel
        
        mock_orchestrator = Mock()
        ui_panel = UIControlPanel(orchestrator=mock_orchestrator, host='127.0.0.1', port=5000)
        
        available = ui_panel._check_port_available('127.0.0.1', 65530)
        assert available == True, "Available port should return True"
        
        occupied_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            occupied_socket.bind(('127.0.0.1', 5000))
            occupied_socket.listen(1)
            time.sleep(0.1)
            
            available = ui_panel._check_port_available('127.0.0.1', 5000)
            assert available == False, "Occupied port should return False"
        finally:
            occupied_socket.close()
    
    def test_find_available_port(self):
        """Test that _find_available_port finds an available port."""
        from tests._ui_isolated_loader import UIControlPanel
        
        mock_orchestrator = Mock()
        ui_panel = UIControlPanel(orchestrator=mock_orchestrator, host='127.0.0.1', port=5000)
        
        occupied_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            occupied_socket.bind(('127.0.0.1', 5000))
            occupied_socket.listen(1)
            time.sleep(0.1)
            
            available_port = ui_panel._find_available_port(5000, max_attempts=10)
            
            assert available_port != 5000, "Should find different port"
            assert available_port >= 5001, "Should be >= 5001"
            assert ui_panel._check_port_available('127.0.0.1', available_port), "Found port should be available"
        finally:
            occupied_socket.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
