# pytest configuration and fixtures
import pytest
import sys
from pathlib import Path
from typing import Any, Dict, Generator

# Add project to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(autouse=True)
def _reset_guardian_singleton_after_each_test():
    """Avoid RuntimeError when multiple tests construct GuardianCore in one session."""
    yield
    try:
        from project_guardian.guardian_singleton import reset_singleton

        reset_singleton()
    except Exception:
        pass


@pytest.fixture
def minimal_guardian_config(tmp_path: Path) -> Dict[str, Any]:
    """Lightweight GuardianCore config: temp memory, no UI server, deferred heavy work."""
    mem_path = tmp_path / "guardian_memory.json"
    mem_path.write_text("[]", encoding="utf-8")
    return {
        "memory_filepath": str(mem_path),
        "storage_path": str(tmp_path),
        "ui_config": {"enabled": False},
        "defer_heavy_startup": True,
        "_test_skip_external_storage": True,
        "enable_resource_monitoring": False,
        "enable_vector_memory": False,
    }


@pytest.fixture
def guardian_core(minimal_guardian_config: Dict[str, Any]) -> Generator[Any, None, None]:
    """Shared GuardianCore for UI/introspection/integration tests (allow_multiple + shutdown)."""
    from project_guardian.core import GuardianCore

    core = GuardianCore(minimal_guardian_config, allow_multiple=True)
    try:
        yield core
    finally:
        try:
            core.shutdown()
        except Exception:
            pass
