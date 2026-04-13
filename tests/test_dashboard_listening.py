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

# Add project root to path
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "project_guardian"))


class TestDashboardListening:
    """Test dashboard server listening behavior."""
    
    def test_port_fallback_when_5000_occupied(self):
        """Test that port fallback works when port 5000 is occupied."""
        from project_guardian.ui_control_panel import UIControlPanel
        
        # Create a socket to occupy port 5000
        occupied_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            occupied_socket.bind(('127.0.0.1', 5000))
            occupied_socket.listen(1)
            
            # Create UI panel (mock orchestrator)
            mock_orchestrator = Mock()
            ui_panel = UIControlPanel(orchestrator=mock_orchestrator, host='127.0.0.1', port=5000)
            
            # Mock socketio.run to avoid actually starting server
            with patch.object(ui_panel, 'socketio') as mock_socketio:
                mock_socketio.run = Mock()
                
                # Mock _wait_for_server_ready to return True (simulate success)
                with patch.object(ui_panel, '_wait_for_server_ready', return_value=True):
                    # Start should find alternative port
                    ui_panel.start(debug=False, source="test")
                    
                    # Verify port was changed
                    assert ui_panel.port != 5000, "Port should have been changed from 5000"
                    assert ui_panel.port >= 5001, "Port should be >= 5001"
                    assert ui_panel._actual_port == ui_panel.port, "Actual port should match"
                    
        finally:
            occupied_socket.close()
    
    def test_server_ready_before_browser_open(self):
        """Test that server is listening before browser open is called."""
        from project_guardian.ui_control_panel import UIControlPanel
        
        mock_orchestrator = Mock()
        ui_panel = UIControlPanel(orchestrator=mock_orchestrator, host='127.0.0.1', port=5000)
        
        # Mock socketio.run
        with patch.object(ui_panel, 'socketio') as mock_socketio:
            mock_socketio.run = Mock()
            
            # Mock _wait_for_server_ready to simulate server becoming ready
            ready_called = []
            def mock_wait(timeout):
                ready_called.append(time.time())
                return True
            
            with patch.object(ui_panel, '_wait_for_server_ready', side_effect=mock_wait):
                # Mock _check_port_available to return True (port available)
                with patch.object(ui_panel, '_check_port_available', return_value=True):
                    ui_panel.start(debug=False, source="test")
                    
                    # Verify _wait_for_server_ready was called
                    assert len(ready_called) > 0, "_wait_for_server_ready should have been called"
                    
                    # Verify _server_ready event is set
                    assert ui_panel._server_ready.is_set(), "Server ready event should be set"
    
    def test_server_error_propagation(self):
        """Test that server errors are properly captured and propagated."""
        from project_guardian.ui_control_panel import UIControlPanel
        
        mock_orchestrator = Mock()
        ui_panel = UIControlPanel(orchestrator=mock_orchestrator, host='127.0.0.1', port=5000)
        
        # Mock socketio.run to raise an error
        error_msg = "Port already in use"
        def mock_run(*args, **kwargs):
            raise OSError(error_msg)
        
        with patch.object(ui_panel, 'socketio') as mock_socketio:
            mock_socketio.run = mock_run
            
            # Mock _check_port_available to return True
            with patch.object(ui_panel, '_check_port_available', return_value=True):
                # Mock _wait_for_server_ready to return False (server didn't start)
                with patch.object(ui_panel, '_wait_for_server_ready', return_value=False):
                    # Start should raise RuntimeError with server error
                    with pytest.raises(RuntimeError) as exc_info:
                        ui_panel.start(debug=False, source="test")
                    
                    # Give thread time to set error
                    time.sleep(0.5)
                    
                    # Verify error was captured
                    assert ui_panel._server_error is not None, "Server error should be set"
                    assert error_msg in ui_panel._server_error or "already in use" in ui_panel._server_error.lower()
    
    def test_actual_port_stored_correctly(self):
        """Test that _actual_port is stored correctly."""
        from project_guardian.ui_control_panel import UIControlPanel
        
        mock_orchestrator = Mock()
        ui_panel = UIControlPanel(orchestrator=mock_orchestrator, host='127.0.0.1', port=5000)
        
        # Mock socketio.run
        with patch.object(ui_panel, 'socketio') as mock_socketio:
            mock_socketio.run = Mock()
            
            # Mock _check_port_available to return True
            with patch.object(ui_panel, '_check_port_available', return_value=True):
                # Mock _wait_for_server_ready to return True
                with patch.object(ui_panel, '_wait_for_server_ready', return_value=True):
                    ui_panel.start(debug=False, source="test")
                    
                    # Verify _actual_port is set
                    assert ui_panel._actual_port is not None, "_actual_port should be set"
                    assert ui_panel._actual_port == ui_panel.port, "_actual_port should match port"
    
    def test_port_availability_check(self):
        """Test that _check_port_available works correctly."""
        from project_guardian.ui_control_panel import UIControlPanel
        
        mock_orchestrator = Mock()
        ui_panel = UIControlPanel(orchestrator=mock_orchestrator, host='127.0.0.1', port=5000)
        
        # Test with available port (should return True)
        # Use a high port that's unlikely to be in use
        available = ui_panel._check_port_available('127.0.0.1', 65530)
        assert available == True, "Available port should return True"
        
        # Test with occupied port
        occupied_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            occupied_socket.bind(('127.0.0.1', 5000))
            occupied_socket.listen(1)
            
            # Small delay to ensure socket is bound
            time.sleep(0.1)
            
            available = ui_panel._check_port_available('127.0.0.1', 5000)
            assert available == False, "Occupied port should return False"
        finally:
            occupied_socket.close()
    
    def test_find_available_port(self):
        """Test that _find_available_port finds an available port."""
        from project_guardian.ui_control_panel import UIControlPanel
        
        mock_orchestrator = Mock()
        ui_panel = UIControlPanel(orchestrator=mock_orchestrator, host='127.0.0.1', port=5000)
        
        # Occupy port 5000
        occupied_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            occupied_socket.bind(('127.0.0.1', 5000))
            occupied_socket.listen(1)
            time.sleep(0.1)
            
            # Find available port
            available_port = ui_panel._find_available_port(5000, max_attempts=10)
            
            # Verify it's different from 5000 and available
            assert available_port != 5000, "Should find different port"
            assert available_port >= 5001, "Should be >= 5001"
            assert ui_panel._check_port_available('127.0.0.1', available_port), "Found port should be available"
        finally:
            occupied_socket.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
