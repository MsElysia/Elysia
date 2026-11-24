"""Attach startup does not treat a live status error as a closed port."""

import importlib.util
import io
import threading
import time
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import elysia_interface


def _load_elysia_main():
    path = Path(__file__).resolve().parents[1] / "elysia.py"
    spec = importlib.util.spec_from_file_location("elysia_main_attach_startup", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _ReadySystem:
    def __init__(self):
        self.running = True
        self.guardian = None

    def get_status(self):
        return {
            "system": "Unified Elysia System",
            "running": True,
            "startup_phase": "fictional-running",
            "components": {
                "architect_core": False,
                "guardian_core": False,
                "runtime_loop": False,
                "integrated_modules": 0,
            },
        }


class _FailingSystem:
    def get_status(self):
        raise RuntimeError("fictional-status-failure")


class _ListHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        body = b"[1, 2]"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _serve_status(system):
    elysia_main = _load_elysia_main()
    elysia_main._status_system = system
    server = HTTPServer(("127.0.0.1", 0), elysia_main._make_status_handler())
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _serve_list():
    server = HTTPServer(("127.0.0.1", 0), _ListHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _run_attach(monkeypatch, server, wait="5", interval="0.3", choice="9"):
    monkeypatch.setenv("ELYSIA_STARTUP_WAIT_SEC", wait)
    monkeypatch.setenv("ELYSIA_STARTUP_POLL_SEC", interval)
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: choice)
    if server is None:
        monkeypatch.setattr(elysia_interface, "STATUS_URL", "http://127.0.0.1:9")
    else:
        port = server.server_address[1]
        monkeypatch.setattr(elysia_interface, "STATUS_URL", f"http://127.0.0.1:{port}")
    ui = elysia_interface.ElysiaInterface(attach_only=True)
    buffer = io.StringIO()
    started = time.perf_counter()
    try:
        with redirect_stdout(buffer):
            ui.run()
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
    return time.perf_counter() - started, buffer.getvalue()


def test_missing_system_opens_menu_without_boot_wait(monkeypatch):
    elapsed, text = _run_attach(monkeypatch, _serve_status(None))
    assert elapsed < 1.5
    assert "Status unavailable: System not initialized" in text
    assert "The status server answered. The menu will open." in text
    assert "Goodbye!" in text
    assert "still booting" not in text
    assert "Backend not reachable" not in text
    assert "[OK] Backend connected" not in text


def test_status_exception_opens_menu_without_boot_wait(monkeypatch):
    elapsed, text = _run_attach(monkeypatch, _serve_status(_FailingSystem()))
    assert elapsed < 1.5
    assert "Status unavailable: fictional-status-failure" in text
    assert "Goodbye!" in text
    assert "still booting" not in text
    assert "Backend not reachable" not in text
    assert "[OK] Backend connected" not in text


def test_non_object_status_opens_menu_without_boot_wait(monkeypatch):
    elapsed, text = _run_attach(monkeypatch, _serve_list())
    assert elapsed < 1.5
    assert "Status unavailable: Invalid status format" in text
    assert "Goodbye!" in text
    assert "still booting" not in text
    assert "[OK] Backend connected" not in text


def test_ready_status_reports_connected(monkeypatch):
    elapsed, text = _run_attach(monkeypatch, _serve_status(_ReadySystem()))
    assert elapsed < 1.5
    assert "[OK] Backend connected" in text
    assert "startup_phase: fictional-running" in text
    assert "Goodbye!" in text
    assert "still booting" not in text
    assert "Status unavailable" not in text


def test_closed_port_still_waits_and_exits(monkeypatch):
    elapsed, text = _run_attach(monkeypatch, None, wait="0.8", interval="0.2")
    assert elapsed >= 0.6
    assert "still booting" in text
    assert "Backend not reachable" in text
    assert "Goodbye!" not in text
    assert "[OK] Backend connected" not in text


def test_view_status_names_unavailable_not_unreachable(monkeypatch):
    server = _serve_status(None)
    port = server.server_address[1]
    monkeypatch.setattr(elysia_interface, "STATUS_URL", f"http://127.0.0.1:{port}")
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "")
    ui = elysia_interface.ElysiaInterface(attach_only=True)
    buffer = io.StringIO()
    try:
        with redirect_stdout(buffer):
            ui.view_status()
            ui.view_memories()
    finally:
        server.shutdown()
        server.server_close()
    text = buffer.getvalue()
    assert text.count("Status unavailable: System not initialized") == 2
    assert "Could not reach backend" not in text
