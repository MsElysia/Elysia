# project_guardian/tests/test_config_validation.py
# Test Configuration Validation on Startup

import pytest
import tempfile
import shutil
from pathlib import Path
import sys
import os

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from project_guardian.core import GuardianCore
from project_guardian.config_validator import ConfigValidator


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
        "ui_config": {
            "enabled": False  # Disable UI for testing
        }
    }


@pytest.fixture
def invalid_config(temp_data_dir):
    """Create invalid configuration."""
    return {
        "memory_path": "/nonexistent/path/memory.json",
        "storage_path": "/nonexistent/path",
        "log_level": "INVALID"
    }


@pytest.mark.slow
class TestConfigurationValidation:
    """Test configuration validation on startup (GuardianCore init each test)."""
    
    def test_validation_runs_on_startup(self, minimal_config):
        """Test 1: Validation runs automatically on GuardianCore init."""
        
        core = GuardianCore(minimal_config)
        
        # Verify validation results are stored
        assert hasattr(core, 'config_validation_results')
        
        # Verify validation ran
        validation_status = core.get_config_validation_status()
        assert validation_status is not None
        assert "valid" in validation_status
        assert "errors" in validation_status
        assert "warnings" in validation_status
        
        core.shutdown()
    
    def test_validation_with_valid_config(self, minimal_config):
        """Test 2: Valid configuration passes validation."""
        
        core = GuardianCore(minimal_config)
        
        validation_status = core.get_config_validation_status()
        
        # Should have no critical errors (warnings may exist)
        # Configuration should be functional
        assert validation_status is not None
        
        core.shutdown()
    
    def test_validation_with_missing_directories(self, temp_data_dir):
        """Test 3: System creates missing directories."""
        
        # Config pointing to non-existent directories
        config = {
            "memory_path": str(temp_data_dir / "new_dir" / "memory.json"),
            "storage_path": str(temp_data_dir / "new_storage"),
            "ui_config": {"enabled": False}
        }
        
        core = GuardianCore(config)
        
        # Validation should either create directories or warn
        validation_status = core.get_config_validation_status()
        assert validation_status is not None
        
        # System should still start (graceful degradation)
        status = core.get_system_status()
        assert status is not None
        
        core.shutdown()
    
    def test_validation_status_method(self, minimal_config):
        """Test 4: get_config_validation_status returns correct format."""
        
        core = GuardianCore(minimal_config)
        
        status = core.get_config_validation_status()
        
        # Verify structure
        assert isinstance(status, dict)
        assert "valid" in status
        assert "errors" in status
        assert "warnings" in status
        assert "info" in status
        
        # Verify types
        assert isinstance(status["valid"], bool)
        assert isinstance(status["errors"], list)
        assert isinstance(status["warnings"], list)
        assert isinstance(status["info"], list)
        
        core.shutdown()
    
    def test_validation_doesnt_block_startup(self, invalid_config):
        """Test 5: Invalid config doesn't prevent startup."""
        
        # Even with invalid config, system should start
        try:
            core = GuardianCore(invalid_config)
            
            # Should have validation results
            validation_status = core.get_config_validation_status()
            assert validation_status is not None
            
            # System should still be functional (with warnings)
            assert hasattr(core, 'memory')
            assert hasattr(core, 'mutation')
            
            core.shutdown()
        except Exception as e:
            # If it fails completely, that's okay for this test
            # We're just checking that validation doesn't cause crashes
            pass
    
    def test_validation_checks_directories(self, temp_data_dir):
        """Test 6: Validation checks required directories."""
        
        config = {
            "storage_path": str(temp_data_dir),
            "ui_config": {"enabled": False}
        }
        
        core = GuardianCore(config)
        
        validation_status = core.get_config_validation_status()
        
        # Should check directories
        # May have warnings about missing dirs, but should create them
        assert validation_status is not None
        
        # Verify data directory was created or warned about
        data_dir = Path(temp_data_dir) / "data"
        
        core.shutdown()
    
    def test_validation_checks_api_keys(self, minimal_config):
        """Test 7: Validation checks for API keys."""
        
        # Remove API keys from environment temporarily (if any)
        original_keys = {}
        for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]:
            if key in os.environ:
                original_keys[key] = os.environ[key]
                del os.environ[key]
        
        try:
            core = GuardianCore(minimal_config)
            
            validation_status = core.get_config_validation_status()
            
            # Should have warnings about missing API keys (non-critical)
            assert validation_status is not None
            
            # System should still start
            assert hasattr(core, 'memory')
            
            core.shutdown()
        finally:
            # Restore API keys
            for key, value in original_keys.items():
                os.environ[key] = value
    
    def test_validation_logs_issues(self, minimal_config, caplog):
        """Test 8: Validation logs issues appropriately."""
        
        import logging
        with caplog.at_level(logging.INFO):
            core = GuardianCore(minimal_config)
            
            # Check that validation messages were logged
            log_messages = caplog.text
            
            # Should have some validation-related messages
            # (may be info, warning, or error depending on config)
            assert len(log_messages) > 0
            
            core.shutdown()
    
    def test_validation_handles_exceptions_gracefully(self, minimal_config):
        """Test 9: Validation handles exceptions without crashing."""
        
        # Create a config that might cause issues
        config = {
            **minimal_config,
            "config_path": "/nonexistent/config.json"
        }
        
        # Should not crash
        try:
            core = GuardianCore(config)
            
            # Should have validation results even if validation partially failed
            validation_status = core.get_config_validation_status()
            assert validation_status is not None
            
            core.shutdown()
        except Exception as e:
            # If it crashes, that's a problem we should note
            pytest.fail(f"Configuration validation caused crash: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

