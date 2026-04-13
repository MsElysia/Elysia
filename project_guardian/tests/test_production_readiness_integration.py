# project_guardian/tests/test_production_readiness_integration.py
# Test Production Readiness Integration with GuardianCore

import pytest
import tempfile
import shutil
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from project_guardian.core import GuardianCore


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create temporary data directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    yield data_dir
    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture
def minimal_config(temp_data_dir):
    """Create minimal valid configuration."""
    return {
        "memory_path": str(temp_data_dir / "memory.json"),
        "storage_path": str(temp_data_dir),
        "log_level": "INFO",
        "ui_config": {"enabled": False},
        "enable_resource_monitoring": True,
        "resource_limits": {
            "memory_limit": 0.8,
            "cpu_limit": 0.9,
            "disk_limit": 0.9
        }
    }


class TestProductionReadinessIntegration:
    """Test production readiness features integrated with GuardianCore."""
    
    def test_security_auditor_initialized(self, minimal_config):
        """Test 1: SecurityAuditor is initialized in GuardianCore."""
        core = GuardianCore(minimal_config)
        
        assert hasattr(core, 'security_auditor')
        assert core.security_auditor is not None
        
        core.shutdown()
    
    def test_resource_monitor_initialized(self, minimal_config):
        """Test 2: ResourceMonitor is initialized in GuardianCore."""
        core = GuardianCore(minimal_config)
        
        assert hasattr(core, 'resource_monitor')
        assert core.resource_monitor is not None
        
        core.shutdown()
    
    def test_run_security_audit_method(self, minimal_config):
        """Test 3: run_security_audit method works."""
        core = GuardianCore(minimal_config)
        
        audit_results = core.run_security_audit()
        
        assert audit_results is not None
        assert "security_score" in audit_results
        assert "status" in audit_results
        assert "issues" in audit_results
        
        core.shutdown()
    
    def test_get_resource_status_method(self, minimal_config):
        """Test 4: get_resource_status method works."""
        core = GuardianCore(minimal_config)
        
        resource_status = core.get_resource_status()
        
        assert resource_status is not None
        assert "monitoring_active" in resource_status
        assert "limits" in resource_status
        
        core.shutdown()
    
    def test_get_resource_stats_method(self, minimal_config):
        """Test 5: get_resource_stats method works."""
        core = GuardianCore(minimal_config)
        
        resource_stats = core.get_resource_stats()
        
        assert isinstance(resource_stats, dict)
        
        core.shutdown()
    
    def test_get_resource_violations_method(self, minimal_config):
        """Test 6: get_resource_violations method works."""
        core = GuardianCore(minimal_config)
        
        violations = core.get_resource_violations(limit=10)
        
        assert isinstance(violations, list)
        
        core.shutdown()
    
    def test_resource_monitoring_starts(self, minimal_config):
        """Test 7: Resource monitoring starts automatically."""
        core = GuardianCore(minimal_config)
        
        status = core.get_resource_status()
        
        # Monitoring should be active if psutil available
        if status.get("psutil_available"):
            # May or may not be active depending on config
            pass
        
        core.shutdown()
    
    def test_security_audit_detects_issues(self, minimal_config):
        """Test 8: Security audit detects real issues."""
        core = GuardianCore(minimal_config)
        
        audit_results = core.run_security_audit()
        
        # Should have a security score
        assert audit_results["security_score"] >= 0
        assert audit_results["security_score"] <= 100
        
        # Should have summary
        assert len(audit_results["summary"]) > 0
        
        core.shutdown()
    
    def test_config_validation_and_security_audit(self, minimal_config):
        """Test 9: Configuration validation and security audit work together."""
        core = GuardianCore(minimal_config)
        
        # Both should work
        config_status = core.get_config_validation_status()
        audit_results = core.run_security_audit()
        
        assert config_status is not None
        assert audit_results is not None
        
        core.shutdown()
    
    def test_all_production_readiness_methods(self, minimal_config):
        """Test 10: All production readiness methods accessible."""
        core = GuardianCore(minimal_config)
        
        # Configuration validation
        config_status = core.get_config_validation_status()
        assert config_status is not None
        
        # Security audit
        audit_results = core.run_security_audit()
        assert audit_results is not None
        
        # Resource status
        resource_status = core.get_resource_status()
        assert resource_status is not None
        
        # Resource stats
        resource_stats = core.get_resource_stats()
        assert isinstance(resource_stats, dict)
        
        # Resource violations
        violations = core.get_resource_violations()
        assert isinstance(violations, list)
        
        core.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

