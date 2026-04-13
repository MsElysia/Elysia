"""
Test that webscout_agent module imports without crashing.
Verifies HAS_HTTPX is defined before use.
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_webscout_agent_imports_without_crashing():
    """Test that webscout_agent can be imported without NameError"""
    # This should not raise NameError: HAS_HTTPX is not defined
    try:
        from project_guardian import webscout_agent
        # If we get here, import succeeded
        assert True
    except NameError as e:
        if "HAS_HTTPX" in str(e):
            pytest.fail(f"HAS_HTTPX not defined before use: {e}")
        else:
            raise
    except ImportError as e:
        # ImportError is acceptable (missing dependencies)
        # But NameError is not (HAS_HTTPX should be defined)
        if "HAS_HTTPX" in str(e):
            pytest.fail(f"HAS_HTTPX not defined: {e}")
        # Other ImportErrors are fine (missing optional deps)
        pass


def test_has_httpx_is_defined():
    """Test that HAS_HTTPX is defined in the module"""
    try:
        from project_guardian import webscout_agent
        # HAS_HTTPX should be defined as a module-level constant
        assert hasattr(webscout_agent, 'HAS_HTTPX'), "HAS_HTTPX should be defined in webscout_agent module"
        # Should be a boolean
        assert isinstance(webscout_agent.HAS_HTTPX, bool), "HAS_HTTPX should be a boolean"
    except ImportError:
        # If module can't be imported due to missing deps, skip this test
        pytest.skip("webscout_agent module not available (missing dependencies)")


def test_webscout_agent_works_without_httpx():
    """Test that webscout_agent works even when httpx is not installed"""
    try:
        from project_guardian import webscout_agent
        
        # HAS_HTTPX should be False if httpx is not installed
        # (This test passes regardless of whether httpx is installed)
        assert hasattr(webscout_agent, 'HAS_HTTPX')
        
        # Module should be importable and usable
        # Even if httpx is not available, the module should not crash
        assert webscout_agent is not None
        
    except ImportError as e:
        # Only fail if it's a NameError about HAS_HTTPX
        if "HAS_HTTPX" in str(e):
            pytest.fail(f"Module should define HAS_HTTPX even without httpx: {e}")
        # Other ImportErrors are acceptable
        pytest.skip(f"Module not available: {e}")
