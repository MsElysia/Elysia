import socket
import time
from unittest.mock import Mock, patch

import pytest


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _panel():
    try:
        from project_guardian.ui_control_panel import UIControlPanel, reset_dashboard_guard
    except ImportError:
        pytest.skip("UIControlPanel not available")
    reset_dashboard_guard()
    return UIControlPanel(orchestrator=Mock(), host="127.0.0.1", port=_free_port())


def test_ui_panel_not_ready_when_start_probe_times_out():
    panel = _panel()
    try:
        with patch.object(panel, "_check_port_available", return_value=True), \
             patch.object(panel, "_wait_for_server_ready", return_value=False), \
             patch.object(panel.socketio, "run", side_effect=lambda *args, **kwargs: time.sleep(1.0)):
            panel.start(source="test-timeout")

        state = panel.get_readiness_state()
        assert panel.running is True
        assert panel._server_ready.is_set()
        assert panel.is_ready() is False
        assert state["startup_checked"] is True
        assert state["listening"] is False
        assert state["ready"] is False
    finally:
        panel.stop()


def test_ui_panel_late_readiness_probe_recovers_after_timeout():
    panel = _panel()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with patch.object(panel, "_check_port_available", return_value=True), \
             patch.object(panel, "_wait_for_server_ready", return_value=False), \
             patch.object(panel.socketio, "run", side_effect=lambda *args, **kwargs: time.sleep(1.0)):
            panel.start(source="test-late-ready")

        assert panel.is_ready() is False

        listener.bind((panel.host, panel.port))
        listener.listen(1)

        assert panel.is_ready() is True
        state = panel.get_readiness_state()
        assert state["ready"] is True
        assert state["listening"] is True
    finally:
        listener.close()
        panel.stop()


def test_ui_panel_ready_only_after_successful_start_probe():
    panel = _panel()
    try:
        with patch.object(panel, "_check_port_available", return_value=True), \
             patch.object(panel, "_wait_for_server_ready", return_value=True), \
             patch.object(panel.socketio, "run", side_effect=lambda *args, **kwargs: time.sleep(1.0)):
            panel.start(source="test-ready")

        state = panel.get_readiness_state()
        assert panel.is_ready() is True
        assert state["listening"] is True
        assert state["ready"] is True
        assert state["port"] == panel.port
    finally:
        panel.stop()


def test_ui_panel_start_raises_on_immediate_server_error():
    panel = _panel()

    def fail_run(*args, **kwargs):
        raise OSError("Port already in use")

    try:
        with patch.object(panel, "_check_port_available", return_value=True), \
             patch.object(panel, "_wait_for_server_ready", return_value=False), \
             patch.object(panel.socketio, "run", side_effect=fail_run):
            with pytest.raises(RuntimeError):
                panel.start(source="test-error")

        state = panel.get_readiness_state()
        assert panel.running is False
        assert state["ready"] is False
        assert state["error"]
    finally:
        panel.stop()
