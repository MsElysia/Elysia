# project_guardian/tests/test_dashboard_readiness.py
# Regression tests for dashboard readiness and ownership

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def minimal_config(tmp_path):
    """Minimal config - UI disabled for most tests."""
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


class TestDashboardReadiness:
    """Dashboard readiness from UIControlPanel.is_ready(), not URL."""

    def test_dashboard_ready_from_panel_is_ready_not_url(self, minimal_config):
        """dashboard_ready comes from UIControlPanel.is_ready(), not URL existence."""
        from project_guardian.core import GuardianCore

        core = GuardianCore(minimal_config, allow_multiple=True)
        try:
            op = core.get_startup_operational_state()
            assert "dashboard_ready" in op
            # UI disabled => no panel => dashboard_ready False
            assert op["dashboard_ready"] is False
        finally:
            core.shutdown()

    def test_dashboard_ready_true_when_panel_is_ready(self, minimal_config):
        """When mock panel reports is_ready=True, operational_state has dashboard_ready=True."""
        from project_guardian.core import GuardianCore

        core = GuardianCore(minimal_config, allow_multiple=True)
        try:
            # Mock panel that reports ready (needs running, stop for shutdown)
            class MockPanel:
                running = False
                def is_ready(self):
                    return True
                def stop(self):
                    pass

            core.ui_panel = MockPanel()
            op = core.get_startup_operational_state()
            assert op["dashboard_ready"] is True
        finally:
            core.shutdown()

    def test_start_ui_panel_is_canonical_wrapper(self, minimal_config):
        """GuardianCore.start_ui_panel exists and is the canonical entry point."""
        from project_guardian.core import GuardianCore

        core = GuardianCore(minimal_config, allow_multiple=True)
        try:
            assert hasattr(core, "start_ui_panel")
            assert callable(core.start_ui_panel)
        finally:
            core.shutdown()

    def test_second_start_skips_when_panel_already_running(self, minimal_config, monkeypatch):
        """Second start_ui_panel call skips cleanly when panel already running."""
        from project_guardian.core import GuardianCore

        start_calls = []

        class MockPanel:
            running = False
            def __init__(self, orchestrator, host, port):
                self.orchestrator = orchestrator
                self.host = host
                self.port = port
            def is_ready(self):
                return self.running
            def start(self, debug=False, source=None):
                start_calls.append(1)
                self.running = True
            def stop(self):
                self.running = False

        monkeypatch.setattr(
            "project_guardian.core.UIControlPanel",
            MockPanel,
        )
        core = GuardianCore(minimal_config, allow_multiple=True)
        try:
            core.start_ui_panel()
            assert len(start_calls) == 1
            core.start_ui_panel()  # Second call should skip
            assert len(start_calls) == 1
        finally:
            core.shutdown()

    def test_unified_path_dashboard_single_start_no_duplicate(
        self, tmp_path, monkeypatch
    ):
        """
        Unified GuardianCore startup uses canonical start_ui_panel wrapper.
        UIControlPanel.start invoked at most once; second attempts skipped cleanly.
        Dashboard ownership not bypassed by unified path.
        """
        from project_guardian.core import GuardianCore

        start_calls = []

        class MockPanel:
            running = False

            def __init__(self, orchestrator, host, port):
                self.orchestrator = orchestrator
                self.host = host
                self.port = port

            def is_ready(self):
                return self.running

            def start(self, debug=False, source=None):
                start_calls.append(1)
                self.running = True

            def stop(self):
                self.running = False

        monkeypatch.setattr("project_guardian.core.UIControlPanel", MockPanel)

        mem_path = tmp_path / "guardian_memory.json"
        mem_path.write_text("[]", encoding="utf-8")
        config = {
            "memory_filepath": str(mem_path),
            "storage_path": str(tmp_path),
            "ui_config": {"enabled": True, "auto_start": True},
            "defer_heavy_startup": True,
            "_test_skip_external_storage": True,
            "enable_resource_monitoring": False,
            "enable_vector_memory": False,
        }

        core = GuardianCore(config, allow_multiple=True)
        try:
            assert len(start_calls) == 1, (
                "Unified path must invoke panel.start() exactly once during init; "
                f"got {len(start_calls)}"
            )
            core.start_ui_panel()
            assert len(start_calls) == 1, (
                "Second start_ui_panel must skip; start() must not be called again; "
                f"got {len(start_calls)}"
            )
        finally:
            core.shutdown()
