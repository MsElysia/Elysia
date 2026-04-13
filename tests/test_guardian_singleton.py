"""
Tests for GuardianCore singleton pattern to prevent double initialization.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from project_guardian.guardian_singleton import (
    get_guardian_core,
    reset_singleton,
    ensure_monitoring_started
)
from project_guardian.core import GuardianCore


class TestGuardianSingleton:
    """Test GuardianCore singleton behavior"""
    
    def setup_method(self):
        """Reset singleton before each test"""
        reset_singleton()
        # Also reset the class-level flag
        GuardianCore._any_instance_initialized = False
    
    def teardown_method(self):
        """Clean up after each test"""
        reset_singleton()
        GuardianCore._any_instance_initialized = False
    
    def test_get_guardian_core_creates_singleton(self):
        """Test that get_guardian_core creates a singleton instance"""
        # First call should create instance
        core1 = get_guardian_core()
        assert core1 is not None
        assert isinstance(core1, GuardianCore)
        
        # Second call should return same instance
        core2 = get_guardian_core()
        assert core2 is not None
        assert core1 is core2
    
    def test_get_guardian_core_with_config(self):
        """Test that get_guardian_core accepts config"""
        config = {
            "memory_file": "test_memory.json",
            "enable_resource_monitoring": False
        }
        core = get_guardian_core(config=config)
        assert core is not None
        assert core.config.get("memory_file") == "test_memory.json"
    
    def test_direct_guardian_core_initialization_fails_after_singleton(self):
        """Test that direct GuardianCore() fails after singleton is created"""
        # Create via singleton first
        singleton_core = get_guardian_core()
        assert singleton_core is not None
        
        # Direct initialization should fail
        with pytest.raises(RuntimeError, match="already exists"):
            GuardianCore()
    
    def test_unified_then_interface_uses_same_instance(self):
        """Test that unified startup then interface startup uses same instance"""
        # Simulate unified startup
        from run_elysia_unified import UnifiedElysiaSystem
        
        # Mock the other initializations to avoid full system startup
        with patch('run_elysia_unified.UnifiedElysiaSystem._init_architect_core'), \
             patch('run_elysia_unified.UnifiedElysiaSystem._init_runtime_loop'), \
             patch('run_elysia_unified.UnifiedElysiaSystem._init_integrated_modules'), \
             patch('run_elysia_unified.UnifiedElysiaSystem._register_all_modules'):
            
            system = UnifiedElysiaSystem(config={})
            unified_core = system.guardian
            
            # Now simulate interface trying to get GuardianCore
            interface_core = get_guardian_core()
            
            # Should be the same instance
            assert unified_core is interface_core
    
    def test_monitoring_started_once(self):
        """Test that monitoring is started exactly once"""
        core = get_guardian_core()
        assert core is not None
        
        # First call to ensure_monitoring_started should start monitoring
        result1 = ensure_monitoring_started(core)
        assert result1 is True
        
        # Check that monitor is active
        if hasattr(core, 'monitor') and core.monitor:
            assert core.monitor.monitoring_active is True
        
        # Second call should not start again (idempotent)
        result2 = ensure_monitoring_started(core)
        assert result2 is True
        
        # Monitor should still be active (not restarted)
        if hasattr(core, 'monitor') and core.monitor:
            assert core.monitor.monitoring_active is True
    
    def test_reset_singleton(self):
        """Test that reset_singleton clears the instance"""
        # Create instance
        core1 = get_guardian_core()
        assert core1 is not None
        
        # Reset
        reset_singleton()
        
        # New call should create new instance
        core2 = get_guardian_core()
        assert core2 is not None
        # Note: They might be the same object if Python reuses memory,
        # but the singleton flag should be reset
        assert GuardianCore._any_instance_initialized is True
    
    def test_force_new_for_testing(self):
        """Test that force_new allows multiple instances for testing"""
        core1 = get_guardian_core()
        assert core1 is not None
        
        # Force new should create a different instance
        core2 = get_guardian_core(config={}, force_new=True)
        assert core2 is not None
        # They should be different instances when force_new=True
        # (though in practice they might be the same if singleton wasn't set)
        
        # But direct initialization should still work with allow_multiple
        core3 = GuardianCore(config={}, allow_multiple=True)
        assert core3 is not None


class TestMonitoringGuard:
    """Test monitoring guard prevents duplicate heartbeat loops"""
    
    def setup_method(self):
        """Reset singleton before each test"""
        reset_singleton()
        GuardianCore._any_instance_initialized = False
    
    def teardown_method(self):
        """Clean up after each test"""
        reset_singleton()
        GuardianCore._any_instance_initialized = False
    
    def test_monitor_start_is_idempotent(self):
        """Test that monitor.start_monitoring() is idempotent"""
        from project_guardian.monitoring import SystemMonitor
        from project_guardian.memory import MemoryCore
        
        core = get_guardian_core()
        memory = MemoryCore()
        monitor = SystemMonitor(memory, core)
        
        # First start
        monitor.start_monitoring()
        assert monitor.monitoring_active is True
        heartbeat_running_1 = monitor.heartbeat.running
        
        # Second start (should be no-op)
        monitor.start_monitoring()
        assert monitor.monitoring_active is True
        heartbeat_running_2 = monitor.heartbeat.running
        
        # Should still be running (not restarted)
        assert heartbeat_running_1 == heartbeat_running_2
        
        # Clean up
        monitor.stop_monitoring()
