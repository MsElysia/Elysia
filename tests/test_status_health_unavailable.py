"""Contract for GET /health on the unified status server.

The handler under test is the real ``elysia.py`` status server. Health comes
from a local stub, so the test never boots UnifiedElysiaSystem or an external
service. The health-check script and the attach-mode dashboard opener read
that same server.
"""

from __future__ import annotations

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_status_module():
    spec = importlib.util.spec_from_file_location("elysia_status_server", ROOT / "elysia.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Panel:
    def __init__(self, port=5099):
        self.port = port


class Guardian:
    def __init__(self, memory=None, panel=None):
        self.memory = memory if memory is not None else object()
        self.ui_panel = panel if panel is not None else Panel()


class HealthStub:
    def __init__(self, running=True, guardian=None, error=None):
        self._running = running
        self.guardian = guardian
        self.error = error
        self.calls = 0

    @property
    def running(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self._running

    def get_status(self):
        return {
            "system": "Unified Elysia System",
            "running": True,
            "uptime": "0:00:01",
            "components": {
                "architect_core": True,
                "guardian_core": True,
                "runtime_loop": True,
                "integrated_modules": 1,
            },
        }


def _server():
    module = _load_status_module()
    module._status_system = None
    handler = module._make_status_handler()
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return module, server


def _get(port, path="/health"):
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return exc.code, parsed


def test_health_is_ok_only_when_the_system_is_running(monkeypatch):
    module, server = _server()
    try:
        port = server.server_address[1]
        status, body = _get(port)
        assert status == 503
        assert body == {
            "status": "unavailable",
            "system": "elysia",
            "running": False,
            "checks": {},
            "health_available": False,
            "error": "System not initialized",
        }

        stopped = HealthStub(running=False, guardian=Guardian())
        module._status_system = stopped
        status, body = _get(port)
        assert status == 503
        assert body["status"] == "stopped"
        assert body["running"] is False
        assert body["error"] == "System is not running"
        assert body["checks"]["guardian"] is True
        assert body["checks"]["ui_panel"] is True
        assert body["dashboard_url"] == "http://127.0.0.1:5099"
        assert "health_available" not in body
        assert stopped.calls == 1

        failing = HealthStub(error=RuntimeError("fictional-health-failure"))
        module._status_system = failing
        status, body = _get(port)
        assert status == 500
        assert body["health_available"] is False
        assert body["status"] == "unavailable"
        assert body["error"] == "fictional-health-failure"
        assert failing.calls == 1

        running = HealthStub(running=True, guardian=Guardian(memory=object(), panel=Panel(5099)))
        module._status_system = running
        status, body = _get(port)
        assert status == 200
        assert body["status"] == "ok"
        assert body["running"] is True
        assert body["checks"] == {"guardian": True, "memory": True, "ui_panel": True}
        assert body["dashboard_url"] == "http://127.0.0.1:5099"
        assert "error" not in body
        assert "health_available" not in body

        import elysia_health_check

        monkeypatch.setattr(
            "elysia_config.get_status_url",
            lambda: f"http://127.0.0.1:{port}",
        )
        module._status_system = None
        missing = elysia_health_check.check_health()
        assert missing["healthy"] is False
        assert missing["error"] == "System not initialized"
        assert missing["subsystems"]["health"] == "unavailable"
        assert missing["subsystems"]["running"] is False

        module._status_system = running
        healthy = elysia_health_check.check_health()
        assert healthy["healthy"] is True
        assert healthy["error"] is None
        assert healthy["subsystems"]["health"] == "ok"
        assert healthy["running"] is True
        assert healthy["uptime"] == "0:00:01"
    finally:
        module._status_system = None
        server.shutdown()
        server.server_close()


def test_attach_dashboard_reads_a_health_failure(monkeypatch, capsys):
    module, server = _server()
    opened = []
    try:
        port = server.server_address[1]
        import elysia_interface

        elysia_interface.STATUS_URL = f"http://127.0.0.1:{port}"
        monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "")
        monkeypatch.setattr(elysia_interface.webbrowser, "open", lambda url: opened.append(url))
        ui = elysia_interface.ElysiaInterface(attach_only=True)

        ui.open_web_dashboard()
        missing = capsys.readouterr().out
        assert "Health unavailable: System not initialized" in missing
        assert "URL: http://127.0.0.1:5000" in missing
        assert opened == ["http://127.0.0.1:5000"]

        module._status_system = HealthStub(running=False, guardian=Guardian())
        ui.open_web_dashboard()
        stopped = capsys.readouterr().out
        assert "Health unavailable: System is not running" in stopped
        assert "URL: http://127.0.0.1:5099" in stopped
        assert opened[-1] == "http://127.0.0.1:5099"
    finally:
        module._status_system = None
        server.shutdown()
        server.server_close()
