import threading
import socket
import subprocess
import sys
import time
import json
import os
from pathlib import Path
from urllib.request import ProxyHandler, build_opener
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from flask import Flask, jsonify
from werkzeug.serving import make_server

from scripts.dashboard_verification_loader import load_dashboard

ui = load_dashboard()
UIControlPanel = ui.UIControlPanel
reset_dashboard_guard = ui.reset_dashboard_guard


@pytest.fixture
def panel(tmp_path):
    reset_dashboard_guard()
    instance = UIControlPanel(SimpleNamespace(conversation_store_dir=tmp_path), port=0)
    yield instance
    instance.stop()
    reset_dashboard_guard()


@pytest.fixture
def serve():
    servers = []

    def start(app, panel):
        server = make_server("127.0.0.1", 0, app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        servers.append((server, thread))
        panel.port = server.server_port
        panel._actual_port = server.server_port
        panel.running = True
        thread.start()
        return server

    yield start
    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_timeout_does_not_signal_ready(panel):
    with patch.object(panel.socketio, "run"), patch.object(
        panel, "_wait_for_server_ready", return_value=False
    ):
        panel.start(source="timeout-regression")
    assert not panel._server_ready.is_set()
    assert not panel.is_ready()


def test_startup_error_does_not_signal_ready_and_can_retry(panel):
    with patch.object(panel.socketio, "run", side_effect=OSError("fictional bind failure")):
        with pytest.raises(RuntimeError, match="fictional bind failure"):
            panel.start(source="failure-regression")
    assert not panel._server_ready.is_set()
    assert not panel.is_ready()
    assert not panel.running
    with patch.object(panel.socketio, "run"), patch.object(
        panel, "_wait_for_server_ready", return_value=True
    ):
        panel.start(source="retry-regression")
    assert panel._server_ready.is_set()


@pytest.mark.parametrize("status", [200, 503])
def test_other_http_server_is_not_elysia(panel, serve, status):
    foreign = Flask("fictional-other-server")

    @foreign.route("/api/ping")
    def ping():
        return jsonify(ok=True, service="elysia-control-panel"), status

    serve(foreign, panel)
    assert not panel._wait_for_server_ready(timeout=0.2)
    assert not panel.is_ready()


def test_own_http_success_and_shutdown_are_probed(panel, serve):
    server = serve(panel.app, panel)
    assert panel.is_ready()
    server.shutdown()
    server.server_close()
    assert not panel.is_ready()


def test_late_http_start_recovers_after_timeout(panel, serve):
    with patch.object(panel.socketio, "run"), patch.object(
        panel, "_wait_for_server_ready", return_value=False
    ):
        panel.start(source="late-regression")
    assert not panel.is_ready()
    serve(panel.app, panel)
    assert panel.is_ready()
    assert panel._server_ready.is_set()


def test_stop_clears_readiness_signal(panel):
    panel._server_ready.set()
    panel.stop()
    assert not panel._server_ready.is_set()


def test_tcp_listener_that_never_returns_http_is_not_ready(panel):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(5)
        panel.port = listener.getsockname()[1]
        panel.running = True
        assert not panel.is_ready()


def test_own_ping_error_is_not_ready(panel, serve):
    panel.app.view_functions["ping"] = lambda: (
        "unavailable", 503, {"X-Elysia-Instance": panel._server_identity}
    )
    serve(panel.app, panel)
    assert not panel.is_ready()


def test_restart_uses_a_fresh_http_probe(panel, serve):
    server = serve(panel.app, panel)
    assert panel.is_ready()
    server.shutdown()
    server.server_close()
    panel.stop()
    assert not panel.is_ready()
    serve(panel.app, panel)
    assert panel.is_ready()


def test_fictional_process_conflict_shutdown_restart(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "verify_dashboard_windows.py"
    opener = build_opener(ProxyHandler({}))
    for attempt in range(20):
        blocker = socket.socket()
        blocker.bind(("127.0.0.1", 0))
        if blocker.getsockname()[1] < 65000:
            break
        blocker.close()
    with blocker:
        blocker.listen(5)
        requested = blocker.getsockname()[1]
        assert requested < 65000
        for cycle in range(2):
            with (tmp_path / f"process-{cycle}.log").open("w+") as output:
                process = subprocess.Popen(
                    [sys._base_executable, str(script), "--port", str(requested)],
                    cwd=tmp_path, stdout=output, stderr=subprocess.STDOUT,
                    env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
                )
                try:
                    deadline = time.monotonic() + 15
                    actual = None
                    while time.monotonic() < deadline:
                        output.seek(0)
                        logs = output.read()
                        for line in logs.splitlines():
                            if line.startswith("FICTIONAL_READ_ONLY_READY "):
                                actual = int(line.rsplit(":", 1)[1])
                        if actual is not None or process.poll() is not None:
                            break
                        time.sleep(0.1)
                    assert actual is not None, logs
                    assert actual > requested
                    with opener.open(f"http://127.0.0.1:{actual}/api/ping", timeout=2) as response:
                        assert response.status == 200
                        assert json.load(response)["service"] == "elysia-control-panel"
                    with opener.open(f"http://127.0.0.1:{actual}/", timeout=2) as response:
                        assert response.status == 200
                finally:
                    process.terminate()
                    process.wait(timeout=5)
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    with socket.socket() as probe:
                        probe.settimeout(0.2)
                        if probe.connect_ex(("127.0.0.1", actual)) != 0:
                            break
                    time.sleep(0.1)
                else:
                    pytest.fail(f"Owned process left port {actual} listening")
