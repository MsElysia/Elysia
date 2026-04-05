#!/usr/bin/env python3
"""
Capability Detection and Reporting
==================================
Detects available optional dependencies and reports system capabilities.
Uses importlib for safe dependency-free checks.
"""

import logging
import importlib.util
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger(__name__)

# Capability flags (initialized by detect_capabilities)
HAS_SENTENCE_TRANSFORMERS = False
HAS_FAISS = False
HAS_HTTPX = False
HAS_PLAYWRIGHT = False
HAS_PSUTIL = False
HAS_ANTHROPIC = False
HAS_OPENAI = False


def _check_package_exists(package_name: str, checker: Optional[Callable] = None) -> bool:
    """
    Check if a package exists using importlib.util.find_spec.
    
    Args:
        package_name: Name of the package to check
        checker: Optional function to override the check (for testing)
    
    Returns:
        True if package exists, False otherwise
    """
    if checker is not None:
        return checker(package_name)
    
    try:
        spec = importlib.util.find_spec(package_name)
        return spec is not None
    except (ImportError, ValueError, AttributeError):
        return False


def _get_package_version(package_name: str) -> Optional[str]:
    """
    Get package version using importlib.metadata.
    
    Args:
        package_name: Name of the package
    
    Returns:
        Version string or None if not available
    """
    try:
        from importlib.metadata import version
        return version(package_name)
    except Exception:
        # Fallback for older Python versions
        try:
            import importlib_metadata
            return importlib_metadata.version(package_name)
        except Exception:
            return None


def get_capabilities(checker: Optional[Callable[[str], bool]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Get capability report for all optional dependencies.
    
    Args:
        checker: Optional function to override package existence checks (for testing)
                 Should accept package_name: str and return bool
    
    Returns:
        Dictionary mapping capability names to capability info dicts.
        Each capability dict contains:
            - "available": bool
            - "version": str | None
            - "notes": str | None
    """
    capabilities = {}
    
    # sentence-transformers
    pkg_name = "sentence_transformers"
    available = _check_package_exists(pkg_name, checker)
    capabilities["sentence_transformers"] = {
        "available": available,
        "version": _get_package_version("sentence-transformers") if available else None,
        "notes": "High-quality local embeddings for semantic search" if available else "Missing: pip install sentence-transformers"
    }
    
    # faiss
    pkg_name = "faiss"
    available = _check_package_exists(pkg_name, checker)
    capabilities["faiss"] = {
        "available": available,
        "version": _get_package_version("faiss-cpu") or _get_package_version("faiss-gpu") if available else None,
        "notes": "Fast vector similarity search" if available else "Missing: pip install faiss-cpu (or faiss-gpu)"
    }
    
    # httpx
    pkg_name = "httpx"
    available = _check_package_exists(pkg_name, checker)
    capabilities["httpx"] = {
        "available": available,
        "version": _get_package_version("httpx") if available else None,
        "notes": "Modern HTTP client for web requests" if available else "Missing: pip install httpx"
    }
    
    # playwright
    pkg_name = "playwright"
    available = _check_package_exists(pkg_name, checker)
    capabilities["playwright"] = {
        "available": available,
        "version": _get_package_version("playwright") if available else None,
        "notes": "Browser automation for JavaScript-heavy sites" if available else "Missing: pip install playwright && playwright install"
    }
    
    # psutil
    pkg_name = "psutil"
    available = _check_package_exists(pkg_name, checker)
    capabilities["psutil"] = {
        "available": available,
        "version": _get_package_version("psutil") if available else None,
        "notes": "System and process utilities" if available else "Missing: pip install psutil"
    }
    
    # anthropic
    pkg_name = "anthropic"
    available = _check_package_exists(pkg_name, checker)
    capabilities["anthropic"] = {
        "available": available,
        "version": _get_package_version("anthropic") if available else None,
        "notes": "Claude API client" if available else "Missing: pip install anthropic"
    }
    
    # openai
    pkg_name = "openai"
    available = _check_package_exists(pkg_name, checker)
    capabilities["openai"] = {
        "available": available,
        "version": _get_package_version("openai") if available else None,
        "notes": "OpenAI API client" if available else "Missing: pip install openai"
    }
    
    return capabilities


def format_capabilities_text(capabilities: Dict[str, Dict[str, Any]]) -> str:
    """
    Format capabilities as a readable ASCII table-like string.
    
    Args:
        capabilities: Dictionary from get_capabilities()
    
    Returns:
        ASCII-only formatted string with [OK]/[MISSING] status
    """
    lines = []
    lines.append("=" * 70)
    lines.append("SYSTEM CAPABILITIES")
    lines.append("=" * 70)
    
    # Available capabilities
    available = [(name, info) for name, info in capabilities.items() if info.get("available", False)]
    if available:
        lines.append("\n[OK] Available Capabilities:")
        for name, info in available:
            version_str = f" (v{info['version']})" if info.get("version") else ""
            lines.append(f"  [OK] {name}{version_str}: {info.get('notes', '')}")
    
    # Missing capabilities
    missing = [(name, info) for name, info in capabilities.items() if not info.get("available", False)]
    if missing:
        lines.append("\n[MISSING] Missing Capabilities (degraded functionality):")
        for name, info in missing:
            lines.append(f"  [MISSING] {name}: {info.get('notes', '')}")
    
    lines.append("\n" + "=" * 70)
    
    result = "\n".join(lines)
    
    # Ensure ASCII-only (for safety)
    try:
        result.encode('ascii')
    except UnicodeEncodeError:
        # Fallback: replace non-ASCII with ASCII equivalents
        result = result.encode('ascii', 'replace').decode('ascii')
    
    return result


def detect_capabilities() -> Dict[str, bool]:
    """
    Detect all optional dependencies and update module-level flags.
    
    Returns:
        Dictionary mapping capability names to availability (True/False)
    """
    global HAS_SENTENCE_TRANSFORMERS, HAS_FAISS, HAS_HTTPX, HAS_PLAYWRIGHT, HAS_PSUTIL, HAS_ANTHROPIC, HAS_OPENAI
    
    caps = get_capabilities()
    
    HAS_SENTENCE_TRANSFORMERS = caps.get("sentence_transformers", {}).get("available", False)
    HAS_FAISS = caps.get("faiss", {}).get("available", False)
    HAS_HTTPX = caps.get("httpx", {}).get("available", False)
    HAS_PLAYWRIGHT = caps.get("playwright", {}).get("available", False)
    HAS_PSUTIL = caps.get("psutil", {}).get("available", False)
    HAS_ANTHROPIC = caps.get("anthropic", {}).get("available", False)
    HAS_OPENAI = caps.get("openai", {}).get("available", False)
    
    return {
        "sentence_transformers": HAS_SENTENCE_TRANSFORMERS,
        "faiss": HAS_FAISS,
        "httpx": HAS_HTTPX,
        "playwright": HAS_PLAYWRIGHT,
        "psutil": HAS_PSUTIL,
        "anthropic": HAS_ANTHROPIC,
        "openai": HAS_OPENAI
    }


# Initialize capabilities on import
detect_capabilities()
