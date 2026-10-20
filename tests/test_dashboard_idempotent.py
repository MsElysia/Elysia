"""Control panel single-start/idempotency regressions.

A mocked server which returns immediately is NOT a running server.
These tests deliberately keep the fake server alive until the assertions end.
"""

import threading
import time
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("flask")
pytest.importorskip("flask_socketio")

from tests._ui_isolated_loader import UIControlPanel, reset_dashboard_guard, ui_panel_module


@pytest.fixture(autouse=True)
def reset_single_start_guard():
    reset_dashboard_guard()
    yield
    reset_dashboard_guard()


@pytest.fixture
def long_running_runner():
    release = threading.Event()
    entered = threading.Event()

    def run(*args, **kwargs):
        entered.set()
        release.wait(timeout=8.0)

    yield run, entered
    release.set()


def _mock_health(panel):
    """Only the startup/idempotency behavior is under test here."""
    return [
        patch.object(panel, "_check_port_available", return_value=True),
        patch.object(panel, "_wait_for_server_ready", return_value=True),
    ]


def test_start_twice_launches_only_one_server(long_running_runner):
    run, entered = long_running_runner
    panel = UIControlPanel(orchestrator=Mock(), port=9999)
    check_port, check_health = _mock_health(panel)
    with check_port, check_health, patch.object(panel.socketio, "run", side_effect=run) as mock_run:
        assert panel.start(source="test_first") is True
        assert entered.wait(timeout=2)
        assert panel.running is True
        assert panel.start(source="test_second") is True
        assert mock_run.call_count == 1
        assert panel.is_ready() is True


def test_two_panels_respect_global_guard(long_running_runner):
    run, entered = long_running_runner
    panel1 = UIControlPanel(orchestrator=Mock(), port=9998)
    panel2 = UIControlPanel(orchestrator=Mock(), port=9997)
    check_port1, check_health1 = _mock_health(panel1)
    check_port2, check_health2 = _mock_health(panel2)
    with check_port1, check_health1, check_port2, check_health2, \
         patch.object(panel1.socketio, "run", side_effect=run) as mock_run1, \
         patch.object(panel2.socketio, "run") as mock_run2:
        assert panel1.start(source="first_instance") is True
        assert entered.wait(timeout=2)
        assert panel2.start(source="second_instance") is False
        assert mock_run1.call_count == 1
        assert mock_run2.call_count == 0
        assert panel1.running is True
        assert panel2.running is False


def test_repeated_start_is_logged(long_running_runner):
    run, entered = long_running_runner
    panel = UIControlPanel(orchestrator=Mock(), port=9996)
    check_port, check_health = _mock_health(panel)
    with check_port, check_health, \
         patch.object(panel.socketio, "run", side_effect=run) as mock_run, \
         patch.object(ui_panel_module, "logger") as mock_logger:
        assert panel.start(source="instrument_first") is True
        assert entered.wait(timeout=2)
        assert panel.start(source="instrument_second") is True
        assert mock_run.call_count == 1
        assert mock_logger.info.called
