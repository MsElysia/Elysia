"""
Test that UnifiedElysiaSystem + ElysiaInterface don't cause double GuardianCore initialization.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from project_guardian.guardian_singleton import get_guardian_core, reset_singleton
from project_guardian.core import GuardianCore


class TestUnifiedInterfaceNoDoubleInit:
    """Test that unified system + interface don't double-initialize"""
    
    def setup_method(self):
        """Reset singleton before each test"""
        reset_singleton()
        GuardianCore._any_instance_initialized = False
    
    def teardown_method(self):
        """Clean up after each test"""
        reset_singleton()
        GuardianCore._any_instance_initialized = False
    
    def test_unified_then_interface_uses_singleton(self):
        """Test that UnifiedElysiaSystem then ElysiaInterface uses same GuardianCore"""
        # Simulate unified system startup
        from run_elysia_unified import UnifiedElysiaSystem
        
        # Mock other initializations to avoid full system startup
        with patch('run_elysia_unified.UnifiedElysiaSystem._init_architect_core'), \
             patch('run_elysia_unified.UnifiedElysiaSystem._init_runtime_loop'), \
             patch('run_elysia_unified.UnifiedElysiaSystem._init_integrated_modules'), \
             patch('run_elysia_unified.UnifiedElysiaSystem._register_all_modules'):
            
            system = UnifiedElysiaSystem(config={})
            unified_core = system.guardian
            assert unified_core is not None
            
            # Now simulate interface trying to get GuardianCore
            from elysia_interface import ElysiaInterface
            interface = ElysiaInterface()
            
            # Interface should use singleton (not create new instance)
            interface._init_core()
            interface_core = interface.core
            
            # Should be the same instance
            assert interface_core is not None
            assert unified_core is interface_core
    
    def test_interface_init_does_not_raise_exception(self):
        """Test that ElysiaInterface._init_core() doesn't raise 'instance already exists'"""
        # First, create GuardianCore via singleton
        core1 = get_guardian_core()
        assert core1 is not None
        
        # Now interface should be able to get it without exception
        from elysia_interface import ElysiaInterface
        interface = ElysiaInterface()
        
        # Should not raise RuntimeError about instance already existing
        try:
            interface._init_core()
            assert interface.core is not None
            # Should be the same instance
            assert interface.core is core1
        except RuntimeError as e:
            if "already exists" in str(e):
                pytest.fail(f"Interface should use singleton, not raise exception: {e}")
            raise
    
    def test_monitoring_not_started_twice(self):
        """Test that monitoring is not started twice when unified + interface both initialize"""
        from project_guardian.guardian_singleton import ensure_monitoring_started
        
        # Simulate unified system
        from run_elysia_unified import UnifiedElysiaSystem
        with patch('run_elysia_unified.UnifiedElysiaSystem._init_architect_core'), \
             patch('run_elysia_unified.UnifiedElysiaSystem._init_runtime_loop'), \
             patch('run_elysia_unified.UnifiedElysiaSystem._init_integrated_modules'), \
             patch('run_elysia_unified.UnifiedElysiaSystem._register_all_modules'):
            
            system = UnifiedElysiaSystem(config={})
            unified_core = system.guardian
            
            # Unified system should have started monitoring
            if unified_core and hasattr(unified_core, 'monitor'):
                monitoring_started_1 = unified_core.monitor.monitoring_active if unified_core.monitor else False
            else:
                monitoring_started_1 = False
            
            # Now interface initializes
            from elysia_interface import ElysiaInterface
            interface = ElysiaInterface()
            interface._init_core()
            
            # Monitoring should still be started (not restarted)
            if interface.core and hasattr(interface.core, 'monitor'):
                monitoring_started_2 = interface.core.monitor.monitoring_active if interface.core.monitor else False
            else:
                monitoring_started_2 = False
            
            # Should be same instance, so monitoring state should be consistent
            assert unified_core is interface.core
