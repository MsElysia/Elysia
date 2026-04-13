# project_guardian/tests/test_deferred_init.py
# Regression tests for deferred-init state machine

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def minimal_config(tmp_path):
    """Minimal config with defer_heavy_startup."""
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


def _force_inconsistent_state(core):
    """Force deferred-init into inconsistent state: started but not running/complete/failed."""
    core.deferred_init_started = True
    core.deferred_init_running = False
    core.deferred_init_complete = False
    core.deferred_init_failed = False
    core.deferred_init_error = None


class TestDeferredInitState:
    """Deferred-init state transitions: not_started, running, complete, failed, inconsistent."""

    def test_deferred_init_state_fields_exist(self, minimal_config):
        """operational_state has deferred_init state fields."""
        from project_guardian.core import GuardianCore

        core = GuardianCore(minimal_config, allow_multiple=True)
        try:
            op = core.get_startup_operational_state()
            assert "deferred_init_started" in op
            assert "deferred_init_running" in op
            assert "deferred_init_complete" in op
            assert "deferred_init_failed" in op
            assert "deferred_init_state" in op
            assert "deferred_init_error" in op
        finally:
            core.shutdown()

    def test_deferred_init_state_valid_values(self, minimal_config):
        """deferred_init_state is one of: not_started, running, complete, failed, inconsistent."""
        from project_guardian.core import GuardianCore

        core = GuardianCore(minimal_config, allow_multiple=True)
        try:
            op = core.get_startup_operational_state()
            valid = {"not_started", "running", "complete", "failed", "inconsistent"}
            assert op["deferred_init_state"] in valid
        finally:
            core.shutdown()

    def test_not_started_when_defer_and_not_started(self, minimal_config):
        """When defer_heavy_startup and init not started, state can be not_started."""
        from project_guardian.core import GuardianCore

        core = GuardianCore(minimal_config, allow_multiple=True)
        try:
            op = core.get_startup_operational_state()
            # With defer, we may have not_started or complete depending on timing
            assert op["deferred_init_state"] in ("not_started", "running", "complete")
        finally:
            core.shutdown()

    def test_status_helpers_do_not_interpret_unloaded_as_empty(self, minimal_config):
        """get_memory_state(load_if_needed=False) returns memory_count=None when unloaded, not 0."""
        from project_guardian.core import GuardianCore

        core = GuardianCore(minimal_config, allow_multiple=True)
        try:
            if hasattr(core.memory, "json_memory"):
                mem = core.memory.json_memory
            else:
                mem = core.memory
            if hasattr(mem, "get_memory_state") and getattr(mem, "loaded", True) is False:
                st = mem.get_memory_state(load_if_needed=False)
                assert st.get("memory_count") is None or st.get("memory_loaded") is True
        finally:
            core.shutdown()

    def test_inconsistent_state_branch_reported_and_not_normal(self, minimal_config):
        """Deferred init forced into inconsistent state: operational_state, startup warning, not normal."""
        from project_guardian.core import GuardianCore
        from project_guardian.startup_verification import verify_guardian_startup

        core = GuardianCore(minimal_config, allow_multiple=True)
        try:
            _force_inconsistent_state(core)

            op = core.get_startup_operational_state()
            assert op["deferred_init_state"] == "inconsistent"
            assert op["deferred_init_started"] is True
            assert op["deferred_init_running"] is False
            assert op["deferred_init_complete"] is False
            assert op["deferred_init_failed"] is False

            summary = verify_guardian_startup(core)
            inconsistent_checks = [
                c for c in summary.get("checks", [])
                if c.get("name") == "deferred_init_inconsistent"
            ]
            assert len(inconsistent_checks) == 1
            assert "inconsistent" in (inconsistent_checks[0].get("message") or "").lower()

            status = core.get_system_status()
            op_status = status.get("operational_state", {})
            assert op_status.get("deferred_init_state") == "inconsistent"
            assert op_status.get("deferred_init_state") not in ("complete", "running")
        finally:
            core.shutdown()
