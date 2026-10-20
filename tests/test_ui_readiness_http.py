"""Exact-instance HTTP readiness regressions for Elysia's existing Flask UI.

No Elysia runtime, providers, autonomy, or user memory are started. All HTTP
listeners are loopback-only and live only for the duration of a test.
"""

import json
import threading
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("flask")
pytest.importorskip("flask_socketio")

from flask import Flask, jsonify
from werkzeug.serving import make_server

from project_guardian.ui_control_panel import UIControlPanel, reset_dashboard_guard


@pytest.fixture(autouse=True)
def clear_dashboard_guard():
    reset_dashboard_guard()
    yield
    reset_dashboard_guard()


@pytest.fixture
def panel():
    return UIControlPanel(orchestrator=Mock(), host="127.0.0.1", port=5000)


def serve_until_done(flask_app):
    """Start an ephemeral local HTTP server. Caller must shut it down."""
    server = make_server("127.0.0.1", 0, flask_app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def stop_server(server, thread):
    server.shutdown()
    thread.join(timeout=3)
    server.server_close()


def test_timeout_never_signals_ready(panel):
    """A server that does not bind cannot produce a ready event or status."""
    unblock = threading.Event()

    def blocked_run(*args, **kwargs):
        unblock.wait(timeout=6)

    try:
        with patch.object(panel, "_check_port_available", return_value=True), \
             patch.object(panel, "_wait_for_server_ready", return_value=False), \
             patch.object(panel.socketio, "run", side_effect=blocked_run):
            panel.start(source="readiness-timeout-regression")
            assert not panel._server_ready.is_set()
            assert panel.is_ready() is False
    finally:
        unblock.set()


def test_server_exception_never_signals_ready(panel):
    """A startup failure must not be mistaken for successful readiness."""
    with patch.object(panel, "_check_port_available", return_value=True), \
         patch.object(panel.socketio, "run", side_effect=OSError("synthetic bind failure")):
        try:
            panel.start(source="readiness-error-regression")
        except RuntimeError:
            pass  # Either an exception or an explicit failure status is acceptable.
    assert panel._server_error is not None
    assert panel._server_ready.is_set() is False
    assert panel.is_ready() is False


def test_foreign_http_listener_is_not_our_dashboard(panel):
    """An unrelated server, even one spoofing the service label, is not ready."""
    foreign = Flask("foreign-elysia-test")

    @foreign.get("/api/ping")
    def fake_ping():
        return jsonify({"ok": True, "service": "elysia-control-panel",
                        "instance_id": "different-process"})

    server, thread = serve_until_done(foreign)
    try:
        panel._actual_port = server.server_port
        assert panel._wait_for_server_ready(timeout=0.3) is False
    finally:
        stop_server(server, thread)


def test_malformed_ping_is_not_ready(panel):
    """A JSON response of the wrong shape is not a successful health check."""
    foreign = Flask("malformed-ping-test")

    @foreign.get("/api/ping")
    def malformed_ping():
        return jsonify(["not", "a", "health", "object"])

    server, thread = serve_until_done(foreign)
    try:
        panel._actual_port = server.server_port
        assert panel._wait_for_server_ready(timeout=0.3) is False
    finally:
        stop_server(server, thread)


def test_own_http_ping_confirms_readiness(panel):
    """The running Flask instance, not merely its TCP port, supplies proof."""
    server, thread = serve_until_done(panel.app)
    try:
        panel._actual_port = server.server_port
        assert panel._wait_for_server_ready(timeout=1.0) is True
    finally:
        stop_server(server, thread)


def test_ready_revoked_after_listener_stops(panel):
    """A previously healthy dashboard cannot remain ready after HTTP stops."""
    server, thread = serve_until_done(panel.app)
    panel._actual_port = server.server_port
    panel.running = True
    panel._server_ready.set()
    try:
        assert panel.is_ready() is True
    finally:
        stop_server(server, thread)
    assert panel.is_ready() is False
    assert panel._server_ready.is_set() is False
