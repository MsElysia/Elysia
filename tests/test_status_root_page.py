"""Contract for GET / on the unified status server.

The handler under test is the real ``elysia.py`` status server. The page is
read from a local stub, so the test never boots UnifiedElysiaSystem or an
external service.
"""

from __future__ import annotations

import importlib.util
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_status_module():
    spec = importlib.util.spec_from_file_location("elysia_status_root", ROOT / "elysia.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Panel:
    def __init__(self, port=5099):
        self.port = port


class Guardian:
    def __init__(self, panel=None):
        self.ui_panel = panel if panel is not None else Panel()


class RootStub:
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


def _server():
    module = _load_status_module()
    module._status_system = None
    handler = module._make_status_handler()
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return module, server


def _get(port, path="/"):
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def test_root_page_says_running_only_when_the_system_is_running():
    module, server = _server()
    try:
        port = server.server_address[1]

        status, body = _get(port)
        assert status == 503
        assert "<h1>System not initialized</h1>" in body
        assert "Elysia is running" not in body
        assert "Open Control Panel" not in body

        stopped = RootStub(running=False, guardian=Guardian(Panel(5099)))
        module._status_system = stopped
        status, body = _get(port)
        assert status == 503
        assert "<h1>System is not running</h1>" in body
        assert "http://127.0.0.1:5099" in body
        assert "Elysia is running" not in body
        assert "Open Control Panel" not in body
        assert stopped.calls == 1

        failing = RootStub(error=RuntimeError("fictional-root-failure"))
        module._status_system = failing
        status, body = _get(port)
        assert status == 500
        assert "<h1>Status page unavailable</h1>" in body
        assert "fictional-root-failure" in body
        assert "Elysia is running" not in body
        assert failing.calls == 1

        running = RootStub(running=True, guardian=Guardian(Panel(5099)))
        module._status_system = running
        status, body = _get(port)
        assert status == 200
        assert "<h1>Elysia is running</h1>" in body
        assert "Open Control Panel" in body
        assert "href='http://127.0.0.1:5099'" in body
        assert running.calls == 1

        bare = RootStub(running=True, guardian=None)
        module._status_system = bare
        status, body = _get(port)
        assert status == 200
        assert "<h1>Elysia is running</h1>" in body
        assert "href='http://127.0.0.1:5000'" in body

        hostile = RootStub(running=False, guardian=Guardian(Panel("5099\"><h1>Elysia is running</h1>")))
        module._status_system = hostile
        status, body = _get(port)
        assert status == 503
        assert "<h1>System is not running</h1>" in body
        assert "<h1>Elysia is running</h1>" not in body
        assert "&lt;h1&gt;Elysia is running&lt;/h1&gt;" in body

        status, body = _get(port, "/missing-fictional")
        assert status == 404
        assert body == ""
    finally:
        module._status_system = None
        server.shutdown()
        server.server_close()
