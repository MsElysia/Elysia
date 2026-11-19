"""Contract for GET /status on the unified status server.

The handler under test is the real ``elysia.py`` status server. Status comes
from a local stub, so the test never boots UnifiedElysiaSystem or an external
service. The attach menu reads that same server.
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


class StatusStub:
    def __init__(self, result=None, error=None):
        self.result = result if result is not None else {
            "system": "Unified Elysia System",
            "running": False,
            "uptime": "0:00:01",
            "components": {"architect_core": False},
        }
        self.error = error
        self.calls = 0

    def get_status(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


def _server():
    module = _load_status_module()
    module._status_system = None
    handler = module._make_status_handler()
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return module, server


def _get(port, path="/status"):
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


def test_status_reports_a_collector_failure_instead_of_success():
    module, server = _server()
    try:
        port = server.server_address[1]
        status, body = _get(port)
        assert status == 503
        assert body == {"error": "System not initialized", "status_available": False}

        failing = StatusStub(error=RuntimeError("fictional-status-failure"))
        module._status_system = failing
        status, body = _get(port)
        assert status == 500
        assert body == {
            "error": "fictional-status-failure",
            "status": "degraded",
            "status_available": False,
        }
        assert failing.calls == 1

        module._status_system = StatusStub(result=["not-a-status"])
        status, body = _get(port)
        assert status == 500
        assert body == {"error": "Invalid status format", "status_available": False}

        module._status_system = StatusStub(result={("bad-key",): "fictional"})
        status, body = _get(port)
        assert status == 500
        assert body["status_available"] is False
        assert "Status could not be encoded" in body["error"]
    finally:
        module._status_system = None
        server.shutdown()
        server.server_close()


def test_status_returns_a_dict_and_the_attach_menu_shows_a_failure(monkeypatch, capsys):
    module, server = _server()
    try:
        port = server.server_address[1]
        ok = StatusStub()
        module._status_system = ok
        status, body = _get(port)
        assert status == 200
        assert body["system"] == "Unified Elysia System"
        assert body["running"] is False
        assert "status_available" not in body
        assert ok.calls == 1

        import elysia_interface

        elysia_interface.STATUS_URL = f"http://127.0.0.1:{port}"
        ui = elysia_interface.ElysiaInterface(attach_only=True)
        fetched = ui._fetch_status_from_api()
        assert fetched["system"] == "Unified Elysia System"
        assert ui._status_problem_text(fetched) is None

        module._status_system = StatusStub(error=RuntimeError("fictional-status-failure"))
        monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "")
        ui.view_status()
        out = capsys.readouterr().out
        assert "Status unavailable: fictional-status-failure" in out
        assert "Status request failed." in out
        assert "Uptime:" not in out

        ui.view_memories()
        memories = capsys.readouterr().out
        assert "Status unavailable: fictional-status-failure" in memories
        assert "Total memories" not in memories
    finally:
        module._status_system = None
        server.shutdown()
        server.server_close()
