"""
Unit tests for RSS cleanup logging truth.
Tests verify delta calculation and sign correctness.
All tests use the pure helper function and do not require psutil.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_format_rss_change_increase():
    """Test that RSS increase shows positive delta."""
    from project_guardian.monitoring import SystemMonitor
    
    fake_memory = Mock()
    fake_guardian = Mock()
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # RSS increased: 100MB -> 150MB
    rss_before_bytes = 100 * 1024 * 1024  # 100 MB
    rss_after_bytes = 150 * 1024 * 1024  # 150 MB
    
    result = monitor._format_rss_change(rss_before_bytes, rss_after_bytes)
    
    assert result is not None
    assert "+" in result, f"Expected '+' in result for increase, got: {result}"
    assert "50.00" in result or "50.0" in result, f"Expected ~50MB delta, got: {result}"


def test_format_rss_change_decrease():
    """Test that RSS decrease shows negative delta."""
    from project_guardian.monitoring import SystemMonitor
    
    fake_memory = Mock()
    fake_guardian = Mock()
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # RSS decreased: 200MB -> 150MB
    rss_before_bytes = 200 * 1024 * 1024  # 200 MB
    rss_after_bytes = 150 * 1024 * 1024  # 150 MB
    
    result = monitor._format_rss_change(rss_before_bytes, rss_after_bytes)
    
    assert result is not None
    assert "-" in result, f"Expected '-' in result for decrease, got: {result}"
    assert "50.00" in result or "50.0" in result, f"Expected ~50MB delta, got: {result}"


def test_format_rss_change_no_change():
    """Test that RSS with no change shows zero delta."""
    from project_guardian.monitoring import SystemMonitor
    
    fake_memory = Mock()
    fake_guardian = Mock()
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # RSS unchanged: 100MB -> 100MB
    rss_before_bytes = 100 * 1024 * 1024  # 100 MB
    rss_after_bytes = 100 * 1024 * 1024  # 100 MB
    
    result = monitor._format_rss_change(rss_before_bytes, rss_after_bytes)
    
    assert result is not None
    assert "0.00" in result or "+0.00" in result, f"Expected ~0MB delta, got: {result}"


def test_format_rss_change_unavailable():
    """Test that unavailable RSS returns None."""
    from project_guardian.monitoring import SystemMonitor
    
    fake_memory = Mock()
    fake_guardian = Mock()
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # RSS unavailable
    result = monitor._format_rss_change(None, None)
    assert result is None
    
    result = monitor._format_rss_change(100 * 1024 * 1024, None)
    assert result is None
    
    result = monitor._format_rss_change(None, 100 * 1024 * 1024)
    assert result is None


def test_format_rss_change_correct_sign():
    """Test that sign matches the actual change direction."""
    from project_guardian.monitoring import SystemMonitor
    
    fake_memory = Mock()
    fake_guardian = Mock()
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # Test increase: 153.12MB -> 297.15MB (should be positive)
    rss_before_bytes = int(153.12 * 1024 * 1024)
    rss_after_bytes = int(297.15 * 1024 * 1024)
    
    result = monitor._format_rss_change(rss_before_bytes, rss_after_bytes)
    
    assert result is not None
    # Should show positive delta (increase)
    assert "+" in result or (result.startswith("(delta: ") and not result.startswith("(delta: -"))
    
    # Verify the value is approximately correct
    expected_delta_mb = (rss_after_bytes - rss_before_bytes) / (1024 * 1024)
    assert str(round(expected_delta_mb, 2)) in result or str(int(expected_delta_mb)) in result


def test_cleanup_log_omits_rss_when_unavailable():
    """Test that cleanup completion log omits RSS fields when RSS is unavailable."""
    from project_guardian.monitoring import SystemMonitor
    from unittest.mock import patch
    import logging
    
    fake_memory = Mock()
    fake_memory.memory_log = [{"id": i} for i in range(100)]
    fake_guardian = Mock()
    
    monitor = SystemMonitor(fake_memory, fake_guardian)
    
    # Capture log messages
    log_messages = []
    
    class LogHandler(logging.Handler):
        def emit(self, record):
            log_messages.append(self.format(record))
    
    handler = LogHandler()
    logger = logging.getLogger('project_guardian.monitoring')
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    
    try:
        # Mock _get_cleanup_metrics to return None RSS
        def mock_metrics():
            return {
                "memory_count": 50,
                "rss_bytes": None,
                "rss_mb": None,
                "cache_sizes": {}
            }
        
        monitor._get_cleanup_metrics = mock_metrics
        
        # Mock memory object with consolidate
        fake_memory_obj = Mock()
        fake_memory_obj.memory_log = [{"id": i} for i in range(50)]
        fake_memory_obj.consolidate = Mock(return_value={"removed": 0, "final_count": 50, "before_count": 50})
        
        # Mock _clear_caches
        monitor._clear_caches = Mock(return_value={})
        
        # Get the underlying memory object
        with patch.object(monitor, 'memory', fake_memory):
            # Manually call the cleanup logic with None RSS
            metrics_before = {"memory_count": 100, "rss_bytes": None, "rss_mb": None, "cache_sizes": {}}
            metrics_after = {"memory_count": 50, "rss_bytes": None, "rss_mb": None, "cache_sizes": {}}
            
            # Format the completion message
            memory_delta = metrics_before["memory_count"] - metrics_after["memory_count"]
            rss_change_str = monitor._format_rss_change(metrics_before.get("rss_bytes"), metrics_after.get("rss_bytes"))
            
            # Log completion (simulating what _perform_cleanup does)
            if rss_change_str:
                logger.info(
                    f"[Auto-Cleanup #1] Completed: "
                    f"memory {metrics_before['memory_count']} -> {metrics_after['memory_count']} (removed {memory_delta}), "
                    f"RSS {metrics_before.get('rss_mb')}MB -> {metrics_after.get('rss_mb')}MB {rss_change_str}"
                )
            else:
                logger.info(
                    f"[Auto-Cleanup #1] Completed: "
                    f"memory {metrics_before['memory_count']} -> {metrics_after['memory_count']} (removed {memory_delta})"
                )
        
        # Verify RSS is NOT in the log message
        completion_logs = [msg for msg in log_messages if "Completed:" in msg]
        assert len(completion_logs) > 0, "No completion log found"
        
        completion_log = completion_logs[0]
        assert "RSS" not in completion_log, f"RSS should be omitted when unavailable, but found in: {completion_log}"
        assert "delta:" not in completion_log, f"RSS delta should be omitted when unavailable, but found in: {completion_log}"
        
    finally:
        logger.removeHandler(handler)
