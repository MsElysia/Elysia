"""
Unit tests for capability detection and reporting.
Tests verify structure, stability, and ASCII-only output.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import importlib.util

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_get_capabilities_returns_required_keys():
    """Test that get_capabilities returns all required capability keys."""
    from project_guardian.capabilities import get_capabilities
    
    capabilities = get_capabilities()
    
    # Should return a dictionary
    assert isinstance(capabilities, dict)
    
    # Should have expected keys
    expected_keys = [
        "sentence_transformers",
        "faiss",
        "httpx",
        "playwright",
        "psutil",
        "anthropic",
        "openai"
    ]
    
    for key in expected_keys:
        assert key in capabilities, f"Missing capability key: {key}"


def test_capability_entry_structure():
    """Test that each capability entry contains required fields."""
    from project_guardian.capabilities import get_capabilities
    
    capabilities = get_capabilities()
    
    for name, info in capabilities.items():
        # Must have "available" field
        assert "available" in info, f"Capability {name} missing 'available' field"
        assert isinstance(info["available"], bool), f"Capability {name} 'available' must be bool"
        
        # Must have "version" field (can be None)
        assert "version" in info, f"Capability {name} missing 'version' field"
        assert info["version"] is None or isinstance(info["version"], str), \
            f"Capability {name} 'version' must be str or None"
        
        # Must have "notes" field (can be None)
        assert "notes" in info, f"Capability {name} missing 'notes' field"
        assert info["notes"] is None or isinstance(info["notes"], str), \
            f"Capability {name} 'notes' must be str or None"


def test_format_capabilities_text_ascii_only():
    """Test that format_capabilities_text returns ASCII-only output."""
    from project_guardian.capabilities import get_capabilities, format_capabilities_text
    
    capabilities = get_capabilities()
    formatted = format_capabilities_text(capabilities)
    
    # Should be a string
    assert isinstance(formatted, str)
    
    # Should be ASCII-encodable
    try:
        formatted.encode('ascii')
    except UnicodeEncodeError as e:
        pytest.fail(f"format_capabilities_text returned non-ASCII content: {e}")
    
    # Should contain expected sections
    assert "SYSTEM CAPABILITIES" in formatted
    assert "[OK]" in formatted or "[MISSING]" in formatted


def test_format_capabilities_text_structure():
    """Test that format_capabilities_text has expected structure."""
    from project_guardian.capabilities import get_capabilities, format_capabilities_text
    
    capabilities = get_capabilities()
    formatted = format_capabilities_text(capabilities)
    
    lines = formatted.split('\n')
    
    # Should have header
    assert any("SYSTEM CAPABILITIES" in line for line in lines)
    
    # Should have separator lines
    assert any("=" in line for line in lines)


def test_get_capabilities_with_checker_injection():
    """Test that get_capabilities accepts checker function for testing."""
    from project_guardian.capabilities import get_capabilities
    
    # Create a deterministic checker
    def test_checker(package_name: str) -> bool:
        # Make sentence_transformers available, others missing
        return package_name == "sentence_transformers"
    
    capabilities = get_capabilities(checker=test_checker)
    
    # Verify checker was used
    assert capabilities["sentence_transformers"]["available"] is True
    assert capabilities["faiss"]["available"] is False
    assert capabilities["httpx"]["available"] is False


def test_find_spec_checker_mechanism():
    """Test that _check_package_exists uses find_spec when no checker provided."""
    from project_guardian.capabilities import _check_package_exists
    
    # Test with a real package (if sys is available, it should exist)
    # We can't guarantee what packages exist, so we test the mechanism
    result = _check_package_exists("sys")
    # sys should always be available
    assert result is True
    
    # Test with a fake package
    result = _check_package_exists("_fake_package_that_does_not_exist_12345")
    assert result is False


def test_check_package_exists_with_custom_checker():
    """Test _check_package_exists with injected checker."""
    from project_guardian.capabilities import _check_package_exists
    
    def custom_checker(package_name: str) -> bool:
        return package_name == "test_pkg"
    
    assert _check_package_exists("test_pkg", checker=custom_checker) is True
    assert _check_package_exists("other_pkg", checker=custom_checker) is False


def test_get_package_version_handles_missing():
    """Test that _get_package_version handles missing packages gracefully."""
    from project_guardian.capabilities import _get_package_version
    
    # Should return None for non-existent package
    version = _get_package_version("_fake_package_that_does_not_exist_12345")
    assert version is None


def test_capabilities_no_import_time_crashes():
    """Test that importing capabilities module doesn't crash."""
    try:
        from project_guardian import capabilities
        # Should have module-level flags
        assert hasattr(capabilities, 'HAS_SENTENCE_TRANSFORMERS')
        assert hasattr(capabilities, 'HAS_FAISS')
        assert hasattr(capabilities, 'HAS_HTTPX')
        assert hasattr(capabilities, 'HAS_PLAYWRIGHT')
        assert hasattr(capabilities, 'HAS_PSUTIL')
        assert hasattr(capabilities, 'HAS_ANTHROPIC')
        assert hasattr(capabilities, 'HAS_OPENAI')
        
        # Flags should be boolean
        assert isinstance(capabilities.HAS_SENTENCE_TRANSFORMERS, bool)
        assert isinstance(capabilities.HAS_FAISS, bool)
    except Exception as e:
        pytest.fail(f"Importing capabilities module crashed: {e}")


def test_detect_capabilities_updates_flags():
    """Test that detect_capabilities updates module-level flags."""
    from project_guardian import capabilities
    from project_guardian.capabilities import detect_capabilities
    
    # Get current state
    old_sentence = capabilities.HAS_SENTENCE_TRANSFORMERS
    
    # Re-detect (should be idempotent)
    result = detect_capabilities()
    
    # Should return dict
    assert isinstance(result, dict)
    
    # Should have expected keys
    assert "sentence_transformers" in result
    assert "faiss" in result
    
    # Flags should match result
    assert capabilities.HAS_SENTENCE_TRANSFORMERS == result["sentence_transformers"]


def test_capabilities_in_system_status():
    """Test that capabilities are included in system status."""
    from project_guardian.guardian_singleton import reset_singleton, get_guardian_core
    from project_guardian.core import GuardianCore
    
    reset_singleton()
    GuardianCore._any_instance_initialized = False
    
    try:
        # Use force_new to create a test instance
        core = get_guardian_core(config={}, force_new=True)
        if core:
            status = core.get_system_status()
            
            # Should have capabilities key
            assert "capabilities" in status
            
            # Capabilities should be a dict
            capabilities = status["capabilities"]
            assert isinstance(capabilities, dict)
            
            # Should have at least one capability entry
            if capabilities:
                # Check structure of first entry
                first_key = next(iter(capabilities.keys()))
                first_entry = capabilities[first_key]
                assert "available" in first_entry
                assert "version" in first_entry
                assert "notes" in first_entry
    finally:
        # Cleanup
        try:
            reset_singleton()
            GuardianCore._any_instance_initialized = False
        except:
            pass


def test_format_capabilities_with_all_missing():
    """Test format_capabilities_text when all capabilities are missing."""
    from project_guardian.capabilities import format_capabilities_text
    
    # Create capabilities dict with all missing
    capabilities = {
        "sentence_transformers": {"available": False, "version": None, "notes": "Missing"},
        "faiss": {"available": False, "version": None, "notes": "Missing"},
    }
    
    formatted = format_capabilities_text(capabilities)
    
    # Should be ASCII
    formatted.encode('ascii')
    
    # Should contain MISSING section
    assert "[MISSING]" in formatted


def test_format_capabilities_with_all_available():
    """Test format_capabilities_text when all capabilities are available."""
    from project_guardian.capabilities import format_capabilities_text
    
    # Create capabilities dict with all available
    capabilities = {
        "sentence_transformers": {"available": True, "version": "2.2.0", "notes": "Available"},
        "faiss": {"available": True, "version": "1.7.4", "notes": "Available"},
    }
    
    formatted = format_capabilities_text(capabilities)
    
    # Should be ASCII
    formatted.encode('ascii')
    
    # Should contain OK section
    assert "[OK]" in formatted
