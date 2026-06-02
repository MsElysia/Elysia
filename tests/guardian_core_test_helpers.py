"""Test helpers for GuardianCore singleton / shared-state isolation."""

from __future__ import annotations

import importlib.util
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional
from unittest.mock import MagicMock, patch

_REPO_ROOT = Path(__file__).resolve().parents[1]


def reset_guardian_core_test_state() -> None:
    """Clear module singleton slot and class-level init flag (tests only)."""
    from project_guardian.core import GuardianCore
    from project_guardian.guardian_singleton import reset_singleton

    reset_singleton()
    GuardianCore._any_instance_initialized = False


def load_unified_elysia_system_class():
    """Load UnifiedElysiaSystem from root elysia.py (not the elysia/ package)."""
    spec = importlib.util.spec_from_file_location("elysia_unified_app", _REPO_ROOT / "elysia.py")
    if spec is None or spec.loader is None:
        raise ImportError("Unable to load elysia.py for UnifiedElysiaSystem tests")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.UnifiedElysiaSystem


@contextmanager
def minimal_unified_elysia_system(
    config: Optional[Dict[str, Any]] = None,
    guardian: Any = None,
) -> Iterator[Any]:
    """
    Construct UnifiedElysiaSystem with heavy startup paths mocked.
    Yields the system instance.
    """
    from project_guardian.guardian_singleton import get_guardian_core

    spec = importlib.util.spec_from_file_location("elysia_unified_app", _REPO_ROOT / "elysia.py")
    if spec is None or spec.loader is None:
        raise ImportError("Unable to load elysia.py for UnifiedElysiaSystem tests")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    UnifiedElysiaSystem = mod.UnifiedElysiaSystem

    g = guardian if guardian is not None else get_guardian_core(config=config or {})

    with patch.object(mod, "load_api_keys"), patch(
        "project_guardian.startup_health.run_startup_health_check",
        return_value=(True, [], {"passed": True, "issues": [], "critical": False}),
    ), patch(
        "project_guardian.external_storage.log_startup_external_volume_hints",
        return_value={},
    ), patch.object(mod, "init_guardian_core", return_value=g), patch.object(
        mod, "init_architect_core", return_value=MagicMock()
    ), patch.object(mod, "init_runtime_loop", return_value=MagicMock()), patch.object(
        mod, "init_integrated_modules", return_value={}
    ), patch.object(mod, "init_income_modules"), patch.object(
        mod, "register_all_modules"
    ), patch.object(
        mod, "OpenClawAdapter", return_value=MagicMock(is_available=lambda: False)
    ):
        system = UnifiedElysiaSystem(config=config or {})
        yield system
