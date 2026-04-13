# project_guardian/tests/test_introspection_ui.py
# Tests for Introspection UI Integration
# Validates API endpoints, data formatting, and UI integration

import pytest
import json
import os
import tempfile
from unittest.mock import Mock, patch
from ..core import GuardianCore
from ..introspection import SelfReflector, IntrospectionLens


class TestIntrospectionAPIIntegration:
    """Test introspection API endpoints through UI Control Panel."""
    
    def test_introspection_reflector_available(self, guardian_core):
        """Test that SelfReflector is available on GuardianCore."""
        assert hasattr(guardian_core, 'reflector')
        assert isinstance(guardian_core.reflector, SelfReflector)
        
    def test_comprehensive_report_endpoint(self, guardian_core):
        """Test comprehensive introspection report API."""
        # Skip if Flask not available
        try:
            from ..ui_control_panel import UIControlPanel
        except ImportError:
            pytest.skip("Flask not available for UI testing")
            
        # Create some test memories
        guardian_core.memory.remember(
            "Test introspection memory",
            category="test",
            priority=0.8
        )
        
        panel = UIControlPanel(guardian_core)
        
        # Test the endpoint handler directly
        with panel.app.test_client() as client:
            response = client.get('/api/introspection/comprehensive')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'report' in data
            assert isinstance(data['report'], str)
            assert len(data['report']) > 0
            
    def test_identity_summary_endpoint(self, guardian_core):
        """Test identity summary API endpoint."""
        try:
            from ..ui_control_panel import UIControlPanel
        except ImportError:
            pytest.skip("Flask not available for UI testing")
            
        panel = UIControlPanel(guardian_core)
        
        with panel.app.test_client() as client:
            response = client.get('/api/introspection/identity')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'identity' in data
            ident = data['identity']
            if isinstance(ident, dict):
                assert ident.get('system_name') == 'Project Guardian' or 'Project Guardian' in (
                    ident.get('summary_text') or ''
                )
            else:
                assert 'Project Guardian' in ident
            
    def test_behavior_report_endpoint(self, guardian_core):
        """Test behavior report API endpoint."""
        try:
            from ..ui_control_panel import UIControlPanel
        except ImportError:
            pytest.skip("Flask not available for UI testing")
            
        # Add some memories for behavior analysis
        for i in range(5):
            guardian_core.memory.remember(
                f"Test behavior memory {i}",
                category="test",
                priority=0.7
            )
            
        panel = UIControlPanel(guardian_core)
        
        with panel.app.test_client() as client:
            response = client.get('/api/introspection/behavior')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'behavior' in data
            beh = data['behavior']
            assert isinstance(beh, (str, dict))
            if isinstance(beh, str):
                assert len(beh) > 0
            else:
                assert beh
            
    def test_memory_health_endpoint(self, guardian_core):
        """Test memory health analysis API endpoint."""
        try:
            from ..ui_control_panel import UIControlPanel
        except ImportError:
            pytest.skip("Flask not available for UI testing")
            
        # Add test memories
        guardian_core.memory.remember(
            "Test memory for health check",
            category="test",
            priority=0.8
        )
        
        panel = UIControlPanel(guardian_core)
        
        with panel.app.test_client() as client:
            response = client.get('/api/introspection/health')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'health' in data
            
            health = data['health']
            assert 'status' in health
            assert 'health_score' in health
            assert 'total_memories' in health
            assert 'warnings' in health
            assert isinstance(health['health_score'], (int, float))
            assert 0 <= health['health_score'] <= 1.0
            
    def test_focus_analysis_endpoint(self, guardian_core):
        """Test focus analysis API endpoint."""
        try:
            from ..ui_control_panel import UIControlPanel
        except ImportError:
            pytest.skip("Flask not available for UI testing")
            
        # Add memories for focus analysis
        guardian_core.memory.remember(
            "Focus test memory",
            category="analysis",
            priority=0.9
        )
        
        panel = UIControlPanel(guardian_core)
        
        with panel.app.test_client() as client:
            # Test with default hours (24)
            response = client.get('/api/introspection/focus')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'focus' in data
            
            focus = data['focus']
            assert 'time_window_hours' in focus
            assert 'activity_count' in focus
            assert 'primary_focus' in focus
            assert 'priority_trend' in focus
            assert 'most_active_period' in focus
            
            # Test with custom hours
            response = client.get('/api/introspection/focus?hours=48')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            focus = data['focus']
            assert focus['time_window_hours'] == 48
            
    def test_memory_correlations_endpoint(self, guardian_core):
        """Test memory correlations API endpoint."""
        try:
            from ..ui_control_panel import UIControlPanel
        except ImportError:
            pytest.skip("Flask not available for UI testing")
            
        # Add related memories for correlation testing
        guardian_core.memory.remember(
            "Python programming language is powerful",
            category="coding",
            priority=0.8
        )
        guardian_core.memory.remember(
            "Python development requires good practices",
            category="coding",
            priority=0.7
        )
        
        panel = UIControlPanel(guardian_core)
        
        with panel.app.test_client() as client:
            # Test with keyword
            response = client.get('/api/introspection/correlations?keyword=Python&threshold=0.3')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'correlations' in data
            corr = data['correlations']
            assert isinstance(corr, (list, dict))
            
            # Test missing keyword (should fail)
            response = client.get('/api/introspection/correlations')
            
            assert response.status_code == 400
            data = json.loads(response.data)
            assert data['success'] is False
            
    def test_memory_patterns_endpoint(self, guardian_core):
        """Test memory patterns API endpoint."""
        try:
            from ..ui_control_panel import UIControlPanel
        except ImportError:
            pytest.skip("Flask not available for UI testing")
            
        # Add memories with different categories
        guardian_core.memory.remember("Test 1", category="category1", priority=0.8)
        guardian_core.memory.remember("Test 2", category="category2", priority=0.7)
        
        panel = UIControlPanel(guardian_core)
        
        with panel.app.test_client() as client:
            response = client.get('/api/introspection/patterns')
            
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['success'] is True
            assert 'patterns' in data
            
            patterns = data['patterns']
            if isinstance(patterns, dict) and patterns.get("note"):
                assert "not" in patterns["note"].lower() or "implement" in patterns["note"].lower()
            else:
                assert 'total_memories' in patterns
                assert 'categories' in patterns
                assert 'average_priority' in patterns
                assert isinstance(patterns['total_memories'], int)
                assert patterns['total_memories'] >= 0
            
    def test_introspection_error_handling(self, guardian_core):
        """Test error handling when introspection is unavailable."""
        try:
            from ..ui_control_panel import UIControlPanel
        except ImportError:
            pytest.skip("Flask not available for UI testing")
            
        # Temporarily remove reflector to test error handling
        original_reflector = guardian_core.reflector
        del guardian_core.reflector
        
        panel = UIControlPanel(guardian_core)
        
        with panel.app.test_client() as client:
            response = client.get('/api/introspection/comprehensive')

            # Panel degrades gracefully when reflector is absent (static fallback report).
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data.get('success') is True
            assert 'report' in data
            assert len(data.get('report') or '') > 0

        # Restore reflector
        guardian_core.reflector = original_reflector


class TestIntrospectionDataFormatting:
    """Test data formatting for UI display."""
    
    def test_comprehensive_report_formatting(self, guardian_core):
        """Test comprehensive report is properly formatted."""
        guardian_core.memory.remember("Test", category="test", priority=0.8)
        
        report = guardian_core.reflector.get_comprehensive_report()
        
        assert isinstance(report, str)
        assert len(report) > 0
        # Should contain key sections
        assert '[Guardian Identity]' in report or 'Identity' in report
        assert 'Memory' in report or 'memory' in report.lower()
        
    def test_identity_summary_formatting(self, guardian_core):
        """Test identity summary formatting."""
        summary = guardian_core.reflector.get_identity_summary()
        
        assert isinstance(summary, str)
        assert 'Project Guardian' in summary
        assert len(summary) > 0
        
    def test_behavior_report_formatting(self, guardian_core):
        """Test behavior report formatting."""
        # Add some memories
        for i in range(3):
            guardian_core.memory.remember(
                f"Behavior test {i}",
                category="test",
                priority=0.6 + (i * 0.1)
            )
            
        behavior = guardian_core.reflector.get_behavior_report()
        
        assert isinstance(behavior, str)
        assert len(behavior) > 0
        
    def test_memory_health_data_structure(self, guardian_core):
        """Test memory health returns proper data structure."""
        guardian_core.memory.remember("Test", category="test", priority=0.8)
        
        health = guardian_core.reflector.introspection.analyze_memory_health()
        
        assert isinstance(health, dict)
        assert 'status' in health
        assert 'health_score' in health
        assert 'total_memories' in health
        assert 'warnings' in health
        assert health['status'] in ['healthy', 'degraded', 'poor', 'empty']
        assert 0 <= health['health_score'] <= 1.0
        
    def test_focus_analysis_data_structure(self, guardian_core):
        """Test focus analysis returns proper data structure."""
        guardian_core.memory.remember("Test", category="focus_test", priority=0.8)
        
        focus = guardian_core.reflector.introspection.get_focus_analysis(24)
        
        assert isinstance(focus, dict)
        assert 'time_window_hours' in focus
        assert 'activity_count' in focus
        assert 'primary_focus' in focus
        assert 'priority_trend' in focus
        assert 'most_active_period' in focus
        assert focus['priority_trend'] in ['increasing', 'decreasing', 'stable']
        assert focus['most_active_period'] in ['Morning', 'Afternoon', 'Evening', 'Night', 'No activity', 'Unknown']


class TestIntrospectionUIIntegration:
    """Test introspection integration with UI components."""
    
    def test_ui_panel_has_introspection_endpoints(self, guardian_core):
        """Test UI panel exposes introspection endpoints."""
        try:
            from ..ui_control_panel import UIControlPanel
        except ImportError:
            pytest.skip("Flask not available for UI testing")
            
        panel = UIControlPanel(guardian_core)
        
        # Check routes are registered
        routes = [str(rule) for rule in panel.app.url_map.iter_rules()]
        
        introspection_routes = [
            '/api/introspection/comprehensive',
            '/api/introspection/identity',
            '/api/introspection/behavior',
            '/api/introspection/health',
            '/api/introspection/focus',
            '/api/introspection/correlations',
            '/api/introspection/patterns'
        ]
        
        for route in introspection_routes:
            assert route in routes
            
    def test_introspection_tab_in_template(self, guardian_core):
        """Test introspection tab is included in UI template."""
        try:
            from ..ui_control_panel import UIControlPanel, CONTROL_PANEL_TEMPLATE
        except ImportError:
            pytest.skip("Flask not available for UI testing")
            
        # Check template contains introspection tab
        assert 'introspection' in CONTROL_PANEL_TEMPLATE.lower()
        assert 'Introspection' in CONTROL_PANEL_TEMPLATE
        assert 'introspection' in CONTROL_PANEL_TEMPLATE or 'Introspection' in CONTROL_PANEL_TEMPLATE
        
        # Check for introspection functions in JavaScript
        assert 'getComprehensiveReport' in CONTROL_PANEL_TEMPLATE
        assert 'checkMemoryHealth' in CONTROL_PANEL_TEMPLATE
        assert 'analyzeFocus' in CONTROL_PANEL_TEMPLATE
        assert 'findCorrelations' in CONTROL_PANEL_TEMPLATE
        
    def test_introspection_endpoints_return_json(self, guardian_core):
        """Test all introspection endpoints return valid JSON."""
        try:
            from ..ui_control_panel import UIControlPanel
        except ImportError:
            pytest.skip("Flask not available for UI testing")
            
        guardian_core.memory.remember("Test", category="test", priority=0.8)
        
        panel = UIControlPanel(guardian_core)
        
        endpoints = [
            '/api/introspection/comprehensive',
            '/api/introspection/identity',
            '/api/introspection/behavior',
            '/api/introspection/health',
            '/api/introspection/focus',
            '/api/introspection/patterns'
        ]
        
        with panel.app.test_client() as client:
            for endpoint in endpoints:
                response = client.get(endpoint)
                
                assert response.status_code == 200
                # Verify it's valid JSON
                data = json.loads(response.data)
                assert isinstance(data, dict)
                assert 'success' in data


class TestIntrospectionMethodsDirectly:
    """Test introspection methods work correctly without UI layer."""
    
    def test_get_comprehensive_report_method(self, guardian_core):
        """Test get_comprehensive_report method directly."""
        guardian_core.memory.remember("Test", category="test", priority=0.8)
        
        report = guardian_core.reflector.get_comprehensive_report()
        
        assert isinstance(report, str)
        assert len(report) > 0
        
    def test_get_memory_health_method(self, guardian_core):
        """Test analyze_memory_health method directly."""
        guardian_core.memory.remember("Test", category="test", priority=0.8)
        
        health = guardian_core.reflector.introspection.analyze_memory_health()
        
        assert isinstance(health, dict)
        assert health['status'] in ['healthy', 'degraded', 'poor', 'empty']
        
    def test_get_focus_analysis_method(self, guardian_core):
        """Test get_focus_analysis method directly."""
        guardian_core.memory.remember("Test", category="test", priority=0.8)
        
        focus = guardian_core.reflector.introspection.get_focus_analysis(24)
        
        assert isinstance(focus, dict)
        assert focus['time_window_hours'] == 24
        
    def test_get_memory_correlations_method(self, guardian_core):
        """Test get_memory_correlations method directly."""
        guardian_core.memory.remember(
            "Python is a programming language",
            category="coding",
            priority=0.8
        )
        guardian_core.memory.remember(
            "Python development workflow",
            category="coding",
            priority=0.7
        )
        
        correlations = guardian_core.reflector.introspection.get_memory_correlations(
            "Python", threshold=0.3
        )
        
        assert isinstance(correlations, list)
        # May or may not find correlations depending on similarity
        
    def test_get_memory_patterns_method(self, guardian_core):
        """Test get_memory_patterns method directly."""
        guardian_core.memory.remember("Test 1", category="cat1", priority=0.8)
        guardian_core.memory.remember("Test 2", category="cat2", priority=0.7)
        
        patterns = guardian_core.reflector.introspection.get_memory_patterns()
        
        assert isinstance(patterns, dict)
        assert 'total_memories' in patterns
        assert patterns['total_memories'] >= 0
        assert 'categories' in patterns
        assert isinstance(patterns['categories'], dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

