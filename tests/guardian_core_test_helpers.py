"""Test helpers for GuardianCore singleton / shared-state isolation."""

from __future__ import annotations

import importlib.util
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple
from unittest.mock import MagicMock, patch

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CORE_SMOKE_WS_ROOT = _REPO_ROOT / "tests" / "_core_smoke_workspace"


def minimal_guardian_core_test_config() -> Dict[str, Any]:
    """Fast, isolated GuardianCore config for router/smoke tests."""
    return {
        "enable_vector_memory": False,
        "enable_resource_monitoring": False,
        "_test_skip_external_storage": True,
    }


def write_task_contract_file(path: Path, body: str) -> None:
    """Write task markdown as UTF-8 (avoid Windows cp1252 dash encoding issues)."""
    path.write_text(body, encoding="utf-8")


@contextmanager
def repo_relative_mutation_workspace(
    initial_content: str = "CURRENT_TASK: NONE\n",
) -> Iterator[Tuple[str, Path]]:
    """
    Create CONTROL.md under the repo root for MutationEngine path validation.

    Yields (repo_relative_path, absolute_control_path). Caller must pass only the
    relative path to propose_mutation / apply — absolute paths are rejected.
    """
    run_dir = _CORE_SMOKE_WS_ROOT / uuid.uuid4().hex
    run_dir.mkdir(parents=True, exist_ok=True)
    control = run_dir / "CONTROL.md"
    control.write_text(initial_content, encoding="utf-8")
    # Match MutationEngine._validate_and_resolve_path normalized_rel_path (OS separators).
    rel_str = str(control.relative_to(_REPO_ROOT))
    try:
        yield rel_str, control
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def reset_guardian_core_test_state() -> None:
    """Clear module singleton slot and class-level init flag (tests only)."""
    try:
        from project_guardian.core import GuardianCore
        from project_guardian.guardian_singleton import reset_singleton
    except ImportError:
        # Lineage/control-plane suites may run without optional Guardian deps.
        return

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

    patches = [
        patch.object(mod, "load_api_keys"),
        patch(
            "project_guardian.startup_health.run_startup_health_check",
            return_value=(True, [], {"passed": True, "issues": [], "critical": False}),
        ),
        patch(
            "project_guardian.external_storage.log_startup_external_volume_hints",
            return_value={},
        ),
        patch.object(mod, "init_guardian_core", return_value=g),
        patch.object(mod, "init_architect_core", return_value=MagicMock()),
        patch.object(mod, "init_runtime_loop", return_value=MagicMock()),
        patch.object(mod, "init_integrated_modules", return_value={}),
        patch.object(mod, "init_income_modules"),
        patch.object(mod, "register_all_modules"),
    ]
    # OpenClawAdapter is obsolete on AUTOPILOT-003 tip; patch only if present.
    if hasattr(mod, "OpenClawAdapter"):
        patches.append(
            patch.object(
                mod, "OpenClawAdapter", return_value=MagicMock(is_available=lambda: False)
            )
        )

    from contextlib import ExitStack

    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        system = UnifiedElysiaSystem(config=config or {})
        yield system
