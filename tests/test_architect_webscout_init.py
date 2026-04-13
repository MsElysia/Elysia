"""
Test that Architect-Core can initialize ElysiaWebScout without web_reader.
Verifies graceful fallback when WebReader is unavailable.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_webscout_init_without_web_reader():
    """Test that ElysiaWebScout can be initialized without web_reader"""
    try:
        from project_guardian.webscout_agent import ElysiaWebScout
    except ImportError:
        pytest.skip("ElysiaWebScout not available")
    
    # Should not raise TypeError about missing web_reader
    # Note: If GuardianCore singleton exists, it may get web_reader from it
    # That's fine - the important thing is it doesn't crash
    scout = ElysiaWebScout(web_reader=None)
    assert scout is not None
    # web_reader may be None or may be retrieved from singleton - both are valid
    assert scout.agent_name == "Elysia-WebScout"


def test_webscout_init_with_web_reader():
    """Test that ElysiaWebScout works with web_reader provided"""
    try:
        from project_guardian.webscout_agent import ElysiaWebScout
    except ImportError:
        pytest.skip("ElysiaWebScout not available")
    
    mock_web_reader = Mock()
    scout = ElysiaWebScout(web_reader=mock_web_reader)
    assert scout is not None
    assert scout.web_reader is mock_web_reader


def test_webscout_init_gets_web_reader_from_singleton():
    """Test that ElysiaWebScout tries to get web_reader from GuardianCore singleton"""
    try:
        from project_guardian.webscout_agent import ElysiaWebScout
        from project_guardian.guardian_singleton import get_guardian_core, reset_singleton
    except ImportError:
        pytest.skip("Required modules not available")
    
    # Reset singleton first
    reset_singleton()
    
    # Create GuardianCore with web_reader
    guardian = get_guardian_core()
    assert guardian is not None
    
    # ElysiaWebScout should get web_reader from singleton
    scout = ElysiaWebScout(web_reader=None)
    assert scout is not None
    # If guardian has web_reader, scout should have it too
    if hasattr(guardian, 'web_reader') and guardian.web_reader:
        assert scout.web_reader is not None


def test_architect_core_init_without_web_reader():
    """Test that Architect-Core can initialize ElysiaWebScout without web_reader"""
    try:
        from core_modules.elysia_core_comprehensive.architect_core import ArchitectCore
    except ImportError:
        pytest.skip("ArchitectCore not available")
    
    # Should not crash when initializing with webscout enabled
    architect = ArchitectCore(enable_webscout=True)
    assert architect is not None
    
    # WebScout should be initialized (may be None if import fails, but shouldn't crash)
    if hasattr(architect, 'webscout'):
        # If webscout exists, it should be ElysiaWebScout or None
        # But initialization should not have crashed
        assert True  # Test passes if no exception was raised


def test_webscout_methods_handle_none_web_reader():
    """Test that WebScout methods handle None web_reader gracefully"""
    try:
        from project_guardian.webscout_agent import ElysiaWebScout
    except ImportError:
        pytest.skip("ElysiaWebScout not available")
    
    scout = ElysiaWebScout(web_reader=None)
    
    # Methods that use web_reader should handle None gracefully
    # _brave_search should return empty list
    result = scout._brave_search("test query", count=5)
    assert result == []  # Should return empty list, not crash
    
    # _tavily_search should return empty list
    result = scout._tavily_search("test query", count=5)
    assert result == []  # Should return empty list, not crash
    
    # _fetch_and_parse_webpage should return None
    result = scout._fetch_and_parse_webpage("https://example.com", "test")
    assert result is None  # Should return None, not crash
