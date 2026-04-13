# project_guardian/tests/test_resource_limits.py
# Test Resource Limits and Monitoring

import pytest
import sys
import time
from pathlib import Path
import tempfile

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from project_guardian.resource_limits import ResourceMonitor, ResourceType


@pytest.fixture
def temp_dir(tmp_path):
    """Create temporary directory."""
    yield tmp_path
    import shutil
    shutil.rmtree(tmp_path, ignore_errors=True)


class TestResourceLimits:
    """Test resource limits and monitoring."""
    
    def test_resource_monitor_initialization(self, temp_dir):
        """Test 1: ResourceMonitor initializes correctly."""
        monitor = ResourceMonitor(disk_path=str(temp_dir))
        
        assert monitor is not None
        assert hasattr(monitor, 'limits')
        assert hasattr(monitor, 'check_resources')
        assert ResourceType.MEMORY in monitor.limits
        assert ResourceType.CPU in monitor.limits
        assert ResourceType.DISK in monitor.limits
    
    def test_resource_monitor_configurable_limits(self, temp_dir):
        """Test 2: Resource limits are configurable."""
        monitor = ResourceMonitor(
            memory_limit_percent=0.5,
            cpu_limit_percent=0.7,
            disk_limit_percent=0.8,
            disk_path=str(temp_dir)
        )
        
        assert monitor.limits[ResourceType.MEMORY].limit_percent == 0.5
        assert monitor.limits[ResourceType.CPU].limit_percent == 0.7
        assert monitor.limits[ResourceType.DISK].limit_percent == 0.8
    
    def test_check_resources_returns_stats(self, temp_dir):
        """Test 3: check_resources returns statistics."""
        monitor = ResourceMonitor(disk_path=str(temp_dir))
        
        stats = monitor.check_resources()
        
        # Should return stats (may be empty if psutil not available)
        assert isinstance(stats, dict)
        
        # If psutil available, should have resource data
        if monitor.psutil_available:
            assert "memory" in stats or "cpu" in stats or "disk" in stats
    
    def test_get_resource_stats(self, temp_dir):
        """Test 4: get_resource_stats returns current stats."""
        monitor = ResourceMonitor(disk_path=str(temp_dir))
        
        stats = monitor.get_resource_stats()
        
        assert isinstance(stats, dict)
    
    def test_get_status(self, temp_dir):
        """Test 5: get_status returns monitoring status."""
        monitor = ResourceMonitor(disk_path=str(temp_dir))
        
        status = monitor.get_status()
        
        assert isinstance(status, dict)
        assert "monitoring_active" in status
        assert "psutil_available" in status
        assert "limits" in status
        assert "resource_stats" in status
    
    def test_set_limit(self, temp_dir):
        """Test 6: set_limit updates resource limits."""
        monitor = ResourceMonitor(disk_path=str(temp_dir))
        
        monitor.set_limit(ResourceType.MEMORY, 0.75, warning_threshold=0.6, critical_threshold=0.8)
        
        limit = monitor.limits[ResourceType.MEMORY]
        assert limit.limit_percent == 0.75
        assert limit.warning_threshold == 0.6
        assert limit.critical_threshold == 0.8
    
    def test_get_violations(self, temp_dir):
        """Test 7: get_violations returns violation list."""
        monitor = ResourceMonitor(disk_path=str(temp_dir))
        
        violations = monitor.get_violations()
        
        assert isinstance(violations, list)
        
        # Test with limit
        violations_limited = monitor.get_violations(limit=5)
        assert isinstance(violations_limited, list)
        assert len(violations_limited) <= 5
    
    def test_monitoring_start_stop(self, temp_dir):
        """Test 8: Monitoring can be started and stopped."""
        monitor = ResourceMonitor(disk_path=str(temp_dir))
        
        # Start monitoring
        monitor.start_monitoring(interval=1)
        
        # Give it a moment
        time.sleep(0.1)
        
        # Verify it started
        assert monitor.monitoring_active == monitor.psutil_available
        
        # Stop monitoring
        monitor.stop_monitoring()
        
        # Should be stopped
        assert monitor.monitoring_active == False
    
    def test_is_resource_available(self, temp_dir):
        """Test 9: is_resource_available checks resource usage."""
        monitor = ResourceMonitor(disk_path=str(temp_dir))
        
        # Check each resource type
        memory_available = monitor.is_resource_available(ResourceType.MEMORY)
        cpu_available = monitor.is_resource_available(ResourceType.CPU)
        disk_available = monitor.is_resource_available(ResourceType.DISK)
        
        # Should return boolean
        assert isinstance(memory_available, bool)
        assert isinstance(cpu_available, bool)
        assert isinstance(disk_available, bool)
    
    def test_register_callback(self, temp_dir):
        """Test 10: Callbacks can be registered."""
        monitor = ResourceMonitor(disk_path=str(temp_dir))
        
        callback_called = []
        
        def test_callback(violation):
            callback_called.append(violation)
        
        monitor.register_callback(ResourceType.MEMORY, test_callback)
        
        # Callback should be registered
        assert len(monitor.callbacks[ResourceType.MEMORY]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

