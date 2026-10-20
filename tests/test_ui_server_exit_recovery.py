"""Regression: unexpected normal termination of the dashboard thread is recoverable.

Isolated: no providers, autonomous loop, user data or real HTTP listeners.
The Socket.IO server is replaced with a controlled blocking function.
"""
import threading
import time
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("flask")
pytest.importorskip("flask_socketio")

from tests._ui_isolated_loader import UIControlPanel, reset_dashboard_guard


@pytest.fixture(autouse=True)
def fresh_dashboard_guard():
    reset_dashboard_guard()
    yield
    reset_dashboard_guard()


def _wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_immediate_normal_exit_is_failure_and_retryable():
    """A clean return from socketio.run is not an operating server."""
    panel = UIControlPanel(orchestrator=Mock(), host="127.0.0.1", port=5000)
    starts = []

    def run_returns(*args, **kwargs):
        starts.append(True)

    with patch.object(panel, "_check_port_available", return_value=True), \
         patch.object(panel, "_wait_for_server_ready", return_value=False), \
         patch.object(panel.socketio, "run", side_effect=run_returns):
        with pytest.raises(RuntimeError, match="server exited unexpectedly"):
            panel.start(source="synthetic-normal-exit")

        assert _wait_for(lambda: not panel.running)
        assert panel.is_ready() is False
        assert panel._server_ready.is_set() is False
        assert "server exited unexpectedly" in panel._server_error

        # It must be possible to attempt a new start rather than be blocked
        # permanently by the old module-global single-start guard.
        with pytest.raises(RuntimeError, match="server exited unexpectedly"):
            panel.start(source="synthetic-retry")
        assert len(starts) == 2


def test_normal_exit_after_readiness_revokes_status_and_unblocks_retry():
    """Even an instance that previously became ready must relinquish its guard."""
    panel = UIControlPanel(orchestrator=Mock(), host="127.0.0.1", port=5000)
    release = threading.Event()
    entered = threading.Event()
    calls = []

    def run_until_released(*args, **kwargs):
        calls.append(True)
        entered.set()
        release.wait(timeout=5.0)

    with patch.object(panel, "_check_port_available", return_value=True), \
         patch.object(panel, "_wait_for_server_ready", side_effect=lambda timeout: entered.is_set() and not release.is_set()), \
         patch.object(panel.socketio, "run", side_effect=run_until_released):
        try:
            assert panel.start(source="synthetic-start") is True
            assert entered.wait(timeout=2.0)
            assert panel.running is True
            assert panel._server_ready.is_set() is True
        finally:
            release.set()

        assert _wait_for(lambda: not panel.running)
        assert panel._server_ready.is_set() is False
        assert panel.is_ready() is False

        # Since release is set, the retry's fake server exits immediately.
        # A genuine retry should call the runner a second time.
        with pytest.raises(RuntimeError, match="server exited unexpectedly"):
            panel.start(source="synthetic-retry-after-exit")
        assert len(calls) == 2
