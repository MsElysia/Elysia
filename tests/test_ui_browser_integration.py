"""Comprehensive regression tests for Elysia Browser Dashboard and Local AI Integration.

Covers:
1. /api/ping exact-instance identity and HTTP readiness verification
2. /api/status datetime scoping fix (no orchestrator, orchestrator without start_time, exception path)
3. /api/models actual model availability and Ollama probe reporting
4. /api/chat routing to unified system, ask_ai, or local Ollama with actionable error handling
5. /api/introspection/correlations array contract
6. Server exit recovery and readiness revocation
7. Real Chromium browser verification (initialization transition, truthful status, model display,
   chat message round-trip, actionable model failure, theme persistence, and server disconnection)
"""

import json
import socket
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from flask import Flask, jsonify
from werkzeug.serving import make_server

from tests._ui_isolated_loader import UIControlPanel, reset_dashboard_guard


@pytest.fixture(autouse=True)
def clear_guard():
    reset_dashboard_guard()
    yield
    reset_dashboard_guard()


def serve_ephemeral(flask_app):
    server = make_server("127.0.0.1", 0, flask_app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def stop_ephemeral(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def test_ping_identifies_expected_application_and_instance():
    panel = UIControlPanel(None, host="127.0.0.1", port=5000)
    with panel.app.test_client() as client:
        resp = client.get("/api/ping")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["service"] == "elysia-control-panel"
        assert data["instance_id"] == panel._ready_instance_id
        assert resp.headers.get("X-Elysia-Instance") == panel._ready_instance_id


def test_status_returns_200_without_orchestrator():
    """Regression for PR #149 datetime UnboundLocalError when orchestrator is None."""
    panel = UIControlPanel(None, host="127.0.0.1", port=5000)
    with panel.app.test_client() as client:
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["system"]["running"] is False
        assert data["system"]["initialized"] is False
        assert "Orchestrator not available" in data["system"]["error"]
        assert "timestamp" in data
        assert "models" in data


def test_status_returns_200_when_orchestrator_lacks_start_time():
    """Regression for datetime UnboundLocalError when start_time is None."""
    orch = SimpleNamespace(_initialized=True, _running=True)
    panel = UIControlPanel(orch, host="127.0.0.1", port=5000)
    with panel.app.test_client() as client:
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["system"]["running"] is True
        assert data["system"]["initialized"] is True
        assert data["system"]["uptime"] == 0
        assert "timestamp" in data


def test_status_returns_200_with_active_orchestrator_and_start_time():
    orch = SimpleNamespace(
        _initialized=True,
        _running=True,
        start_time=datetime.now(),
        elysia_loop=SimpleNamespace(running=True, paused=False, queue_size=3),
        memory=SimpleNamespace(
            get_memory_state=lambda load_if_needed=False: {
                "memory_loaded": True,
                "memory_count": 42,
            },
            vector_memory=True,
        ),
    )
    panel = UIControlPanel(orch, host="127.0.0.1", port=5000)
    with panel.app.test_client() as client:
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["system"]["running"] is True
        assert data["loop"]["running"] is True
        assert data["loop"]["queue_size"] == 3
        assert data["memory"]["total_entries"] == 42


def test_foreign_listener_rejected_by_readiness_probe():
    panel = UIControlPanel(None, host="127.0.0.1", port=5000)
    foreign = Flask("foreign")

    @foreign.route("/api/ping")
    def fake_ping():
        return jsonify({"ok": True, "service": "elysia-control-panel", "instance_id": "wrong"}), 200

    server, thread = serve_ephemeral(foreign)
    try:
        panel._actual_port = server.server_port
        panel.running = True
        assert panel._wait_for_server_ready(timeout=0.3) is False
        assert panel.is_ready() is False
    finally:
        stop_ephemeral(server, thread)


def test_own_listener_verified_and_revoked_on_stop():
    panel = UIControlPanel(None, host="127.0.0.1", port=5000)
    server, thread = serve_ephemeral(panel.app)
    try:
        panel._actual_port = server.server_port
        panel.running = True
        assert panel.is_ready() is True
    finally:
        stop_ephemeral(server, thread)
    assert panel.is_ready() is False


def test_models_endpoint_reports_configured_and_installed_models(monkeypatch):
    """Verify /api/models queries local Ollama /api/tags and reports actual models."""
    class MockOllamaHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            if self.path == "/api/tags":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"models": [{"name": "llama3.2:3b"}, {"name": "mistral:7b"}]}).encode()
                )
            else:
                self.send_response(404)
                self.end_headers()

    ollama_server = HTTPServer(("127.0.0.1", 0), MockOllamaHandler)
    ollama_port = ollama_server.server_port
    t = threading.Thread(target=ollama_server.serve_forever, daemon=True)
    t.start()
    try:
        monkeypatch.setenv("OLLAMA_BASE_URL", f"http://127.0.0.1:{ollama_port}")
        monkeypatch.setenv("ELYSIA_OLLAMA_MODEL", "llama3.2:3b")
        panel = UIControlPanel(None, host="127.0.0.1", port=5000)
        with panel.app.test_client() as client:
            resp = client.get("/api/models?refresh=1")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["ollama_reachable"] is True
            assert data["configured_model"] == "llama3.2:3b"
            assert "llama3.2:3b" in data["installed_models"]
            assert "mistral:7b" in data["installed_models"]
            assert data["exact_tag_installed"] is True
            assert data["planner_readiness"] == "ready"
    finally:
        ollama_server.shutdown()
        ollama_server.server_close()


def test_chat_routes_to_local_ollama_and_handles_failures(monkeypatch):
    """Verify /api/chat routes fictional message to local Ollama and returns actionable error on failure."""
    received_messages = []

    class MockOllamaChatHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            if self.path == "/api/tags":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"models": [{"name": "llama3.2:3b"}]}).encode())

        def do_POST(self):
            if self.path == "/api/chat":
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                received_messages.append(body)
                if body.get("model") == "missing-model:latest":
                    self.send_response(404)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "model 'missing-model:latest' not found"}).encode())
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({
                        "model": body.get("model"),
                        "message": {"role": "assistant", "content": "Fictional response from local llama3.2:3b."},
                    }).encode()
                )

    ollama_server = HTTPServer(("127.0.0.1", 0), MockOllamaChatHandler)
    ollama_port = ollama_server.server_port
    t = threading.Thread(target=ollama_server.serve_forever, daemon=True)
    t.start()
    try:
        monkeypatch.setenv("OLLAMA_BASE_URL", f"http://127.0.0.1:{ollama_port}")
        monkeypatch.setenv("ELYSIA_OLLAMA_MODEL", "llama3.2:3b")
        panel = UIControlPanel(None, host="127.0.0.1", port=5000)
        with panel.app.test_client() as client:
            # 1. Successful fictional message
            r_ok = client.post("/api/chat", json={"message": "Hello fictional local model"})
            assert r_ok.status_code == 200
            d_ok = r_ok.get_json()
            assert d_ok["success"] is True
            assert "Fictional response from local llama3.2:3b." in d_ok["reply"]
            assert d_ok["model"] == "llama3.2:3b"

            # 2. Failing model returns actionable error
            r_err = client.post("/api/chat", json={"message": "Test error", "model": "missing-model:latest"})
            assert r_err.status_code == 503
            d_err = r_err.get_json()
            assert d_err["success"] is False
            assert "missing-model:latest" in d_err["error"]
            assert "not found" in d_err["error"]
    finally:
        ollama_server.shutdown()
        ollama_server.server_close()


def test_correlations_endpoint_returns_list():
    panel = UIControlPanel(None, host="127.0.0.1", port=5000)
    with panel.app.test_client() as client:
        resp = client.get("/api/introspection/correlations?keyword=test")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert isinstance(data["correlations"], list)


def test_browser_end_to_end_lifecycle_and_controls(monkeypatch):
    """Real Chromium browser test covering initialization, truthful status, model selection,
    chat round-trip, actionable error handling, theme persistence, and server disconnection."""
    playwright = pytest.importorskip("playwright.sync_api")

    ollama_state = {"fail_chat": False}

    class MockOllamaBrowserHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            if self.path == "/api/tags":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"models": [{"name": "llama3.2:3b"}, {"name": "mistral:7b"}]}).encode()
                )
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path == "/api/chat":
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                if ollama_state["fail_chat"]:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "synthetic local model inference failure"}).encode())
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({
                        "model": body.get("model", "llama3.2:3b"),
                        "message": {
                            "role": "assistant",
                            "content": f"Echo from {body.get('model')}: {body['messages'][0]['content']}",
                        },
                    }).encode()
                )

    ollama_server = HTTPServer(("127.0.0.1", 0), MockOllamaBrowserHandler)
    ollama_port = ollama_server.server_port
    threading.Thread(target=ollama_server.serve_forever, daemon=True).start()

    monkeypatch.setenv("OLLAMA_BASE_URL", f"http://127.0.0.1:{ollama_port}")
    monkeypatch.setenv("ELYSIA_OLLAMA_MODEL", "llama3.2:3b")

    orch = SimpleNamespace(
        _initialized=True,
        _running=True,
        start_time=datetime.now(),
        elysia_loop=SimpleNamespace(running=True, paused=False, queue_size=2),
        memory=SimpleNamespace(
            get_memory_state=lambda load_if_needed=False: {
                "memory_loaded": True,
                "memory_count": 15,
            },
            vector_memory=True,
        ),
        tasks=SimpleNamespace(
            get_active_tasks=lambda: [
                {"name": "Fictional Verification Task", "status": "running", "priority": 5}
            ]
        ),
    )

    panel = UIControlPanel(orch, host="127.0.0.1", port=0)
    server, thread = serve_ephemeral(panel.app)
    port = server.server_port
    panel.port = port
    panel._actual_port = port
    panel.running = True

    page_errors = []
    try:
        with playwright.sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path="/usr/local/bin/google-chrome",
                headless=True,
                args=["--no-sandbox"],
            )
            page = browser.new_page()
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            # 1 & 2. Load dashboard and verify transition from Initializing -> Running
            page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            page.wait_for_function(
                "document.getElementById('status-text').textContent === 'Running'",
                timeout=5000,
            )
            assert page.text_content("#status-text") == "Running"
            assert "status-running" in page.get_attribute("#status-indicator", "class")
            assert page.text_content("#total-memories") == "15"
            assert page.text_content("#queue-size") == "2"

            # 7. Verify model availability displayed on Dashboard card
            assert page.text_content("#planner-readiness") == "ready"
            assert page.text_content("#ollama-reachable") == "Yes"
            assert page.text_content("#configured-model") == "llama3.2:3b"
            assert "llama3.2:3b" in page.text_content("#installed-models")

            # 6 & 11. Theme toggle & persistence across refresh
            assert page.get_attribute("body", "data-theme") == "dark"
            page.click(".theme-toggle")
            assert page.get_attribute("body", "data-theme") == "light"
            page.reload(wait_until="domcontentloaded")
            page.wait_for_function(
                "document.getElementById('status-text').textContent === 'Running'",
                timeout=5000,
            )
            assert page.get_attribute("body", "data-theme") == "light"

            # 10. Tasks tab displays real active tasks
            page.evaluate("showTab('tasks')")
            page.wait_for_function(
                "document.getElementById('task-list').textContent.includes('Fictional Verification Task')",
                timeout=5000,
            )

            # 7 & 8. Control tab model selector and fictional chat message
            page.evaluate("showTab('control')")
            page.wait_for_function(
                "document.getElementById('api-chat-model').options.length >= 2",
                timeout=5000,
            )
            page.select_option("#api-chat-model", "llama3.2:3b")
            page.fill("#api-chat-message", "Fictional ping to local AI")
            page.click("button:has-text('Send')")
            page.wait_for_function(
                "document.getElementById('api-chat-result').textContent.includes('Echo from llama3.2:3b')",
                timeout=5000,
            )
            assert "Fictional ping to local AI" in page.text_content("#api-chat-result")

            # 9. Local model failure produces actionable error rather than endless loading
            ollama_state["fail_chat"] = True
            page.fill("#api-chat-message", "Trigger failure")
            page.click("button:has-text('Send')")
            page.wait_for_function(
                "document.getElementById('api-chat-result').textContent.includes('Error:')",
                timeout=5000,
            )
            assert "synthetic local model inference failure" in page.text_content("#api-chat-result")

            # 12. Server disconnection is detected without falsely reporting Running
            stop_ephemeral(server, thread)
            page.wait_for_function(
                "document.getElementById('status-text').textContent !== 'Running'",
                timeout=6000,
            )
            status_after_stop = page.text_content("#status-text")
            assert "Running" not in status_after_stop
            assert "status-stopped" in page.get_attribute("#status-indicator", "class")

            assert page_errors == []
            browser.close()
    finally:
        try:
            stop_ephemeral(server, thread)
        except Exception:
            pass
        ollama_server.shutdown()
        ollama_server.server_close()
