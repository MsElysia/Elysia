"""Attach-mode dashboard open uses only a URL the status server reports."""

import importlib.util
import io
import threading
from contextlib import redirect_stdout
from http.server import HTTPServer
from pathlib import Path

import elysia_interface


def _load_elysia_main():
    path = Path(__file__).resolve().parents[1] / "elysia.py"
    spec = importlib.util.spec_from_file_location("elysia_main_dashboard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Panel:
    def __init__(self, port):
        self.port = port


class _Guardian:
    def __init__(self, panel):
        self.ui_panel = panel


class _System:
    def __init__(self, panel=None, status=None):
        self.running = True
        self.guardian = _Guardian(panel)
        self._status = status or {
            "running": True,
            "components": {
                "architect_core": False,
                "guardian_core": True,
                "runtime_loop": False,
                "integrated_modules": 0,
            },
        }
        if panel is not None:
            self._status["dashboard_url"] = f"http://127.0.0.1:{panel.port}"

    def get_status(self):
        return dict(self._status)


def _serve(system):
    elysia_main = _load_elysia_main()
    elysia_main._status_system = system
    server = HTTPServer(("127.0.0.1", 0), elysia_main._make_status_handler())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _open(monkeypatch, url, system=None, opened_flag=True):
    opened = []

    def _browser(target, *args, **kwargs):
        opened.append(target)
        return opened_flag

    monkeypatch.setattr(elysia_interface.webbrowser, "open", _browser)
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "")
    server = None
    if system is None and url is None:
        monkeypatch.setattr(elysia_interface, "STATUS_URL", "http://127.0.0.1:9")
    else:
        server = _serve(system)
        port = server.server_address[1]
        monkeypatch.setattr(
            elysia_interface, "STATUS_URL", f"http://127.0.0.1:{port}"
        )
    ui = elysia_interface.ElysiaInterface(attach_only=True)
    buffer = io.StringIO()
    try:
        with redirect_stdout(buffer):
            ui.open_web_dashboard()
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
    return opened, buffer.getvalue()


def test_missing_system_does_not_open_guessed_dashboard(monkeypatch):
    opened, text = _open(monkeypatch, "live", system=None)
    assert opened == []
    assert "Dashboard unavailable: System not initialized" in text
    assert "No browser was opened." in text
    assert "[OK]" not in text
    assert "127.0.0.1:5000" not in text


def test_reported_dashboard_url_is_opened(monkeypatch):
    opened, text = _open(monkeypatch, "live", system=_System(panel=_Panel(5999)))
    assert opened == ["http://127.0.0.1:5999"]
    assert "URL: http://127.0.0.1:5999" in text
    assert "[OK] Browser open requested." in text


def test_running_system_without_panel_does_not_guess(monkeypatch):
    opened, text = _open(monkeypatch, "live", system=_System(panel=None))
    assert opened == []
    assert "backend did not report a dashboard URL" in text
    assert "[OK]" not in text
    assert "127.0.0.1:5000" not in text


def test_browser_refusal_is_not_success(monkeypatch):
    opened, text = _open(
        monkeypatch, "live", system=_System(panel=_Panel(5998)), opened_flag=False
    )
    assert opened == ["http://127.0.0.1:5998"]
    assert "[OK]" not in text
    assert "Browser did not open" in text


def test_unreachable_backend_does_not_open_browser(monkeypatch):
    opened, text = _open(monkeypatch, None, system=None)
    assert opened == []
    assert "Dashboard unavailable:" in text
    assert "No browser was opened." in text
    assert "[OK]" not in text
    assert "127.0.0.1:5000" not in text
