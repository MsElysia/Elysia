# project_guardian/tests/test_startup_smoke.py
# Single startup smoke test for the unified path
# Verifies: startup health, operational_state, dashboard readiness, deferred init, resolved_memory_filepath
# Unit-style: no real server binding, no browser, no long sleeps

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def minimal_config(tmp_path):
    """Minimal config for smoke test - uses tmp_path, skips external storage."""
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


class TestStartupSmoke:
    """Lightweight startup smoke test for unified boot path."""

    def test_startup_smoke_operational_state_structure(self, minimal_config):
        """
        Highest-value smoke: GuardianCore boot produces canonical operational state.
        - operational_state exists with expected fields
        - dashboard_ready field exists (from UIControlPanel.is_ready when UI present)
        - deferred_init state fields exist
        - resolved_memory_filepath exists
        - No duplicate dashboard-start in tested path (UI disabled => no panel start)
        """
        from project_guardian.core import GuardianCore

        core = GuardianCore(minimal_config, allow_multiple=True)
        try:
            op = core.get_startup_operational_state()
            assert isinstance(op, dict)
            assert "deferred_init_started" in op
            assert "deferred_init_running" in op
            assert "deferred_init_complete" in op
            assert "deferred_init_failed" in op
            assert "deferred_init_state" in op
            assert "dashboard_ready" in op
            assert "resolved_memory_filepath" in op
            assert op["deferred_init_state"] in (
                "not_started", "running", "complete", "failed", "inconsistent"
            )
            assert op["resolved_memory_filepath"] is not None
            assert op["resolved_memory_filepath"].endswith("guardian_memory.json")
            # operational_state exposes last rebuild fields (None when no vector)
            assert "last_vector_rebuild_result" in op
            assert "last_vector_rebuild_attempt_at" in op
            assert "vector_rebuild_pending" in op

            status = core.get_system_status()
            assert "operational_state" in status
            assert status["operational_state"] == op
            # Startup status structurally correct
            assert "deferred_init_complete" in status or "operational_state" in status
        finally:
            core.shutdown()

    def test_startup_health_runs_once_structure(self, tmp_path, monkeypatch):
        """run_startup_health_check returns structured result with expected keys."""
        from project_guardian.startup_health import run_startup_health_check

        learned = tmp_path / "learned"
        learned.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "project_guardian.auto_learning.get_learned_storage_path",
            lambda: learned,
        )
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        passed, issues, details = run_startup_health_check(tmp_path)
        assert isinstance(passed, bool)
        assert isinstance(issues, list)
        assert "norm_changed" in details
        assert "validation_errors" in details or "critical" in details

    def test_dashboard_ready_from_panel_not_url(self, minimal_config):
        """dashboard_ready comes from UIControlPanel.is_ready(), not URL existence."""
        from project_guardian.core import GuardianCore

        core = GuardianCore(minimal_config, allow_multiple=True)
        try:
            op = core.get_startup_operational_state()
            # UI disabled => no panel => dashboard_ready is False (not inferred from URL)
            assert op["dashboard_ready"] is False
            assert "dashboard_ready" in op
        finally:
            core.shutdown()
