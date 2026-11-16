"""Task022: actual client API pre-connect denial and real Elysia loopback allowance.

One synthetic process, no real owner files, model, Ollama server, credentials or
external network. A forbidden endpoint has a REAL local witness listener whose
request counter must remain at zero. Guard wrappers are removed after each run.
"""
from __future__ import annotations

import asyncio
import builtins
import http.client
import socket
import threading
from contextlib import contextmanager
from types import SimpleNamespace
from urllib import request as urllib_request

import httpx
import pytest
import requests
from werkzeug.serving import make_server

from project_guardian.local_memory_chat import LocalOllama
from project_guardian.memory import MemoryCore
from project_guardian.ui_control_panel import UIControlPanel
from tools.windows_sync.contained_http_probe_guard import (
    ContainedHttpProbeGuard,
    ProbeBlocked,
)


@contextmanager
def _listener(app):
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive(), "synthetic listener must stop"


def _witness(hits):
    def wsgi(environ, start_response):
        hits.append((environ.get("REQUEST_METHOD"), environ.get("PATH_INFO")))
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"witness-received"]
    return wsgi


def _redirect_witness(hits):
    def wsgi(environ, start_response):
        method = environ.get("REQUEST_METHOD")
        path = environ.get("PATH_INFO")
        hits.append((method, path))
        if path == "/api/status":
            start_response("302 Found", [("Location", "/api/tags")])
            return [b"synthetic-redirect"]
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"forbidden-route-reached"]
    return wsgi


def _attempt(transport, method, url, path):
    if transport == "requests":
        return requests.request(method, url, timeout=2)
    if transport == "httpx":
        with httpx.Client(timeout=2, trust_env=False) as client:
            return client.request(method, url)
    if transport == "httpx_async":
        async def go():
            async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
                return await client.request(method, url)
        return asyncio.run(go())
    if transport == "http.client":
        host_port = url.split("/")[2]
        port = int(host_port.split(":")[1])
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        try:
            conn.request(method, path)
        finally:
            conn.close()
        return None
    if transport == "urllib":
        req = urllib_request.Request(url, method=method)
        with urllib_request.urlopen(req, timeout=2) as response:
            return response.status
    if transport == "LocalOllama":
        port = int(url.split("/")[2].split(":")[1])
        local = LocalOllama("llama3.2:3b", endpoint=f"http://127.0.0.1:{port}")
        return local._request(method, path)
    raise AssertionError("Unrecognized transport fixture")


@pytest.mark.parametrize("transport", [
    "requests", "httpx", "httpx_async", "http.client", "urllib", "LocalOllama"
])
@pytest.mark.parametrize("method,path", [
    ("GET", "/api/tags"),
    ("POST", "/api/chat"),
    ("POST", "/api/generate"),
])
def test_forbidden_probe_blocked_before_local_witness_connect(transport, method, path):
    hits = []
    with _listener(_witness(hits)) as witness_port:
        # Different port is authorized ONLY for the synthetic Elysia app.
        app_port = witness_port + 1 if witness_port < 65535 else witness_port - 1
        url = f"http://127.0.0.1:{witness_port}{path}"
        with ContainedHttpProbeGuard(
            app_port, allowed_routes={("GET", "/api/status")}
        ) as guard:
            with pytest.raises(ProbeBlocked):
                _attempt(transport, method, url, path)
        receipt = guard.receipt()
    assert hits == [], "forbidden attempt reached a listening socket"
    assert receipt["blocked_count"] == 1
    assert receipt["unclassified_count"] == 0
    assert receipt["attempts"] == [{
        "reason": "unapproved_loopback_http", "method": method, "path": path
    }]


@pytest.mark.parametrize("transport", [
    "requests", "httpx", "httpx_async", "urllib"
])
def test_redirect_hop_denied_before_forbidden_route_receives_request(transport):
    hits = []
    with _listener(_redirect_witness(hits)) as app_port:
        url = f"http://127.0.0.1:{app_port}/api/status"
        with ContainedHttpProbeGuard(
            app_port, allowed_routes={("GET", "/api/status")}
        ) as guard:
            with pytest.raises(ProbeBlocked):
                if transport == "requests":
                    requests.get(url, timeout=3)  # follows redirects by default
                elif transport == "httpx":
                    httpx.get(url, timeout=3, trust_env=False, follow_redirects=True)
                elif transport == "httpx_async":
                    async def follow_redirect():
                        async with httpx.AsyncClient(
                            timeout=3, trust_env=False, follow_redirects=True
                        ) as client:
                            await client.get(url)
                    asyncio.run(follow_redirect())
                else:
                    with urllib_request.urlopen(url, timeout=3):
                        pass  # urllib follows HTTP 302 by default
        receipt = guard.receipt()
    assert hits == [("GET", "/api/status")], "forbidden redirect reached listener"
    assert receipt["blocked_count"] == 1
    assert receipt["unclassified_count"] == 0
    assert receipt["attempts"] == [{
        "reason": "unapproved_loopback_http", "method": "GET", "path": "/api/tags"
    }]


@pytest.mark.parametrize("import_target", [
    "requests", "httpx", "project_guardian.local_memory_chat",
])
def test_import_time_socket_probe_blocked_before_client_or_project_import(
    import_target, monkeypatch,
):
    hits = []
    with _listener(_witness(hits)) as witness_port:
        original_import = builtins.__import__
        original_connect = socket.socket.connect
        original_dns = socket.getaddrinfo
        triggered = []

        def import_with_synthetic_probe(name, *args, **kwargs):
            if name == import_target and not triggered:
                triggered.append((
                    name,
                    socket.socket.connect is not original_connect,
                    socket.getaddrinfo is not original_dns,
                ))
                # Import-hook injection: baseline reaches witness, while the
                # repaired guard must block before this local request can send.
                with socket.create_connection(("127.0.0.1", witness_port), timeout=2) as sock:
                    sock.sendall(
                        b"GET /api/tags HTTP/1.1\r\n"
                        b"Host: 127.0.0.1\r\nConnection: close\r\n\r\n"
                    )
                    sock.recv(256)
            return original_import(name, *args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(builtins, "__import__", import_with_synthetic_probe)
            guard = ContainedHttpProbeGuard(
                witness_port, allowed_routes={("GET", "/api/status")}
            )
            with pytest.raises(ProbeBlocked):
                with guard:
                    pass
        receipt = guard.receipt()
    assert triggered == [(import_target, True, True)]
    assert hits == [], "import-time outbound traffic reached witness"
    assert receipt["allowed_http_calls"] == 0
    assert receipt["blocked_count"] == receipt["unclassified_count"] == 1
    assert receipt["attempts"] == [{
        "reason": "unclassified_socket_connect",
        "method": "UNKNOWN",
        "path": "<unclassified>",
    }]
    assert socket.socket.connect is original_connect
    assert socket.getaddrinfo is original_dns


def test_import_time_dns_probe_denied_before_real_resolver(monkeypatch):
    original_import = builtins.__import__
    original_dns = socket.getaddrinfo
    resolver_calls = []
    observed = []

    def witness_resolver(*args, **kwargs):
        resolver_calls.append("reached")
        return []

    with monkeypatch.context() as patch:
        patch.setattr(socket, "getaddrinfo", witness_resolver)

        def import_with_dns_probe(name, *args, **kwargs):
            if name == "project_guardian.local_memory_chat" and not observed:
                observed.append(socket.getaddrinfo is not witness_resolver)
                socket.getaddrinfo("example.invalid", 443)
            return original_import(name, *args, **kwargs)

        patch.setattr(builtins, "__import__", import_with_dns_probe)
        guard = ContainedHttpProbeGuard(
            5078, allowed_routes={("GET", "/api/status")}
        )
        with pytest.raises(ProbeBlocked):
            with guard:
                pass
        assert socket.getaddrinfo is witness_resolver
    receipt = guard.receipt()
    assert observed == [True]
    assert resolver_calls == []
    assert socket.getaddrinfo is original_dns
    assert receipt["blocked_count"] == receipt["unclassified_count"] == 1
    assert receipt["attempts"] == [{
        "reason": "non_loopback_dns",
        "method": "UNKNOWN",
        "path": "<unclassified>",
    }]


def test_actual_elysia_panel_loopback_listener_still_works(tmp_path, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")
    memory = MemoryCore(
        filepath=str(tmp_path / "synthetic_memory.json"),
        enable_timeline_logging=False,
        enable_vector_search=False,
    )
    orchestrator = SimpleNamespace(memory=memory, config={})
    panel = UIControlPanel(orchestrator=orchestrator, host="127.0.0.1", port=5000)
    with _listener(panel.app) as app_port:
        base = f"http://127.0.0.1:{app_port}"
        with ContainedHttpProbeGuard(
            app_port, allowed_routes={("GET", "/api/status")}
        ) as guard:
            a = requests.get(base + "/api/status", timeout=3)
            b = httpx.get(base + "/api/status", timeout=3, trust_env=False)
            with urllib_request.urlopen(base + "/api/status", timeout=3) as c:
                status_c = c.status
            conn = http.client.HTTPConnection("127.0.0.1", app_port, timeout=3)
            try:
                conn.request("GET", "/api/status")
                d = conn.getresponse()
                status_d = d.status
                d.read()
            finally:
                conn.close()
            async def guarded_async_status():
                async with httpx.AsyncClient(timeout=3, trust_env=False) as client:
                    return await client.get(base + "/api/status")

            status_async = asyncio.run(guarded_async_status()).status_code
            assert a.status_code == b.status_code == status_c == status_d == status_async == 200
            assert a.json()["system"] is not None
            assert guard.receipt()["blocked_count"] == 0
            assert guard.receipt()["allowed_http_calls"] >= 4
            with pytest.raises(ProbeBlocked):
                requests.post(base + "/api/chat", json={}, timeout=3)
            assert guard.receipt()["attempts"] == [{
                "reason": "unapproved_loopback_http",
                "method": "POST", "path": "/api/chat",
            }]



def _synthetic_dashboard_panel(tmp_path, port):
    memory = MemoryCore(
        filepath=str(tmp_path / "dashboard_probe_memory.json"),
        enable_timeline_logging=False,
        enable_vector_search=False,
    )
    return UIControlPanel(
        orchestrator=SimpleNamespace(memory=memory, config={}),
        host="127.0.0.1", port=port,
    )


def test_actual_dashboard_availability_and_readiness_are_classified(tmp_path):
    hits = []
    with _listener(_witness(hits)) as app_port:
        panel = _synthetic_dashboard_panel(tmp_path, app_port)
        panel._actual_port = app_port
        panel._server_error = None
        with ContainedHttpProbeGuard(
            app_port, allowed_routes={("GET", "/api/status")}
        ) as guard:
            assert panel._check_port_available("127.0.0.1", app_port) is False
            assert panel._wait_for_server_ready(timeout=0.75) is True
        receipt = guard.receipt()
    assert hits == [], "raw dashboard TCP check must not send HTTP"
    assert receipt["blocked_count"] == receipt["unclassified_count"] == 0
    assert receipt["dashboard_probe_count"] == 2
    assert receipt["dashboard_probes"] == [
        {"operation": "port_availability"},
        {"operation": "server_readiness"},
    ]


def test_dashboard_port_availability_when_not_listening(tmp_path):
    # Bind without listen() to reserve a known unused local listener port.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as reserved:
        reserved.bind(("127.0.0.1", 0))
        app_port = reserved.getsockname()[1]
        panel = _synthetic_dashboard_panel(tmp_path, app_port)
        with ContainedHttpProbeGuard(
            app_port, allowed_routes={("GET", "/api/status")}
        ) as guard:
            assert panel._check_port_available("127.0.0.1", app_port) is True
        receipt = guard.receipt()
    assert receipt["dashboard_probes"] == [{"operation": "port_availability"}]
    assert receipt["dashboard_probe_count"] == 1
    assert receipt["blocked_count"] == receipt["unclassified_count"] == 0


@pytest.mark.parametrize("attempt", [
    "raw_connect_ex", "raw_connect", "wrong_port", "wrong_host",
    "wrong_panel_port", "readiness_wrong_port",
])
def test_dashboard_probe_exemption_never_admits_other_sockets(
    attempt, tmp_path,
):
    hits = []
    with _listener(_witness(hits)) as app_port:
        panel = _synthetic_dashboard_panel(tmp_path, app_port)
        wrong_port = app_port + 1 if app_port < 65535 else app_port - 1
        with ContainedHttpProbeGuard(
            app_port, allowed_routes={("GET", "/api/status")}
        ) as guard:
            if attempt in {"raw_connect_ex", "raw_connect"}:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    with pytest.raises(ProbeBlocked):
                        if attempt == "raw_connect_ex":
                            sock.connect_ex(("127.0.0.1", app_port))
                        else:
                            sock.connect(("127.0.0.1", app_port))
            elif attempt == "wrong_port":
                assert panel._check_port_available("127.0.0.1", wrong_port) is False
            elif attempt == "wrong_host":
                assert panel._check_port_available("127.0.0.2", app_port) is False
            elif attempt == "wrong_panel_port":
                panel.port = wrong_port
                assert panel._check_port_available("127.0.0.1", app_port) is False
            else:
                panel._actual_port = wrong_port
                panel._server_error = None
                assert panel._wait_for_server_ready(timeout=0.02) is False
        receipt = guard.receipt()
    assert hits == []
    assert receipt["dashboard_probe_count"] == 0
    assert receipt["blocked_count"] >= 1
    assert receipt["unclassified_count"] == receipt["blocked_count"]
    assert all(
        item["reason"] == "unclassified_socket_connect"
        for item in receipt["attempts"]
    )


def test_direct_unknown_socket_and_external_dns_are_fail_closed():
    hits = []
    with _listener(_witness(hits)) as witness_port:
        with ContainedHttpProbeGuard(
            witness_port, allowed_routes={("GET", "/api/status")}
        ) as guard:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                with pytest.raises(ProbeBlocked):
                    sock.connect(("127.0.0.1", witness_port))
            finally:
                sock.close()
            sock_ex = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                with pytest.raises(ProbeBlocked):
                    sock_ex.connect_ex(("127.0.0.1", witness_port))
            finally:
                sock_ex.close()
            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                with pytest.raises(ProbeBlocked):
                    udp.sendto(b"synthetic-only", ("127.0.0.1", witness_port))
            finally:
                udp.close()
            with pytest.raises(ProbeBlocked):
                socket.getaddrinfo("example.invalid", 80)
            with pytest.raises(ProbeBlocked):
                requests.get("http://192.0.2.44/api/tags", timeout=2)
        receipt = guard.receipt()
    assert hits == []
    assert receipt["blocked_count"] == 5
    assert receipt["unclassified_count"] == 4
    assert [e["reason"] for e in receipt["attempts"]] == [
        "unclassified_socket_connect", "unclassified_socket_connect",
        "unclassified_socket_sendto", "non_loopback_dns", "non_loopback_http"
    ]
    assert receipt["attempts"][-1]["path"] == "/api/tags"


def test_exception_cleanup_restores_every_transport_patch():
    old_connect = socket.socket.connect
    old_connect_ex = socket.socket.connect_ex
    old_dns = socket.getaddrinfo
    old_session = requests.sessions.Session.request
    old_session_send = requests.sessions.Session.send
    old_httpx_hop = httpx.Client._send_single_request
    old_async_hop = httpx.AsyncClient._send_single_request
    old_httpx = httpx.Client.request
    old_urllib = urllib_request.urlopen
    old_ollama = LocalOllama._request
    guard = ContainedHttpProbeGuard(5078, allowed_routes={("GET", "/api/status")})
    with pytest.raises(RuntimeError, match="synthetic failure"):
        with guard:
            assert socket.socket.connect is not old_connect
            raise RuntimeError("synthetic failure")
    assert socket.socket.connect is old_connect
    assert socket.socket.connect_ex is old_connect_ex
    assert socket.getaddrinfo is old_dns
    assert guard._dashboard_panel_type is None
    assert guard._dashboard_check_codes == {}
    assert requests.sessions.Session.request is old_session
    assert requests.sessions.Session.send is old_session_send
    assert httpx.Client._send_single_request is old_httpx_hop
    assert httpx.AsyncClient._send_single_request is old_async_hop
    assert httpx.Client.request is old_httpx
    assert urllib_request.urlopen is old_urllib
    assert LocalOllama._request is old_ollama
    assert guard.receipt()["blocked_count"] == 0


def test_socketpair_ipc_is_scoped_and_raw_loopback_still_denied():
    hits = []
    with _listener(_witness(hits)) as witness_port:
        with ContainedHttpProbeGuard(
            witness_port, allowed_routes={("GET", "/api/status")}
        ) as guard:
            left, right = socket.socketpair()
            try:
                left.sendall(b"synthetic-IPC")
                assert right.recv(64) == b"synthetic-IPC"
            finally:
                left.close()
                right.close()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                with pytest.raises(ProbeBlocked):
                    sock.connect(("127.0.0.1", witness_port))
            finally:
                sock.close()
        receipt = guard.receipt()
    assert hits == []
    assert receipt["attempts"] == [{
        "reason": "unclassified_socket_connect",
        "method": "UNKNOWN",
        "path": "<unclassified>",
    }]


def _synthetic_child_command(root, app_port):
    from pathlib import Path
    import sys
    helper = Path(__file__).resolve().parents[1] / "tools" / "windows_sync" / "contained_http_probe_guard.py"
    return [
        sys.executable, "-B", str(helper),
        "--mode", "synthetic", "--disposable-root", str(root),
        "--app-port", str(app_port), "--route", "GET:/api/status",
    ]


def _synthetic_root(tmp_path, fixture_source):
    from tools.windows_sync.contained_http_probe_guard import (
        _GUARDED_ROOT_MARKER, _GUARDED_ROOT_CONTENT,
    )
    root = tmp_path / "isolated-synthetic-child"
    root.mkdir()
    (root / _GUARDED_ROOT_MARKER).write_text(
        _GUARDED_ROOT_CONTENT, encoding="utf-8"
    )
    (root / "synthetic_fixture.py").write_text(fixture_source, encoding="utf-8")
    return root


def _unused_local_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_guarded_child_executable_scrubs_only_child_environment(tmp_path, monkeypatch):
    import json
    import os
    import subprocess
    root = _synthetic_root(tmp_path, """
import os
from pathlib import Path
assert "ELYSIA_LOCAL_MODEL" not in os.environ
assert "OPENAI_API_KEY" not in os.environ
def main():
    Path(__file__).with_name("fixture-complete").write_text("done", encoding="utf-8")
    return 0
""")
    monkeypatch.setenv("ELYSIA_LOCAL_MODEL", "SYNTHETIC_SENTINEL_MODEL")
    monkeypatch.setenv("OPENAI_API_KEY", "SYNTHETIC_SENTINEL_KEY")
    child = subprocess.run(
        _synthetic_child_command(root, _unused_local_port()),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=40,
    )
    receipt = json.loads((root / "guarded-child-receipt.json").read_text(encoding="utf-8"))
    assert child.returncode == 0, "test-only child failed"
    assert receipt["status"] == "COMPLETE_TEST_HARNESS_ONLY"
    assert receipt["blocked_count"] == receipt["unclassified_count"] == 0
    assert (root / "fixture-complete").read_text(encoding="utf-8") == "done"
    assert os.environ["ELYSIA_LOCAL_MODEL"] == "SYNTHETIC_SENTINEL_MODEL"
    assert os.environ["OPENAI_API_KEY"] == "SYNTHETIC_SENTINEL_KEY"
    assert "SYNTHETIC_SENTINEL" not in str(receipt) + child.stdout + child.stderr


def test_guarded_child_import_time_raw_connection_records_stop(tmp_path):
    import json
    import subprocess
    hits = []
    with _listener(_witness(hits)) as witness_port:
        root = _synthetic_root(tmp_path, f"""
import socket
with socket.create_connection(("127.0.0.1", {witness_port}), timeout=2):
    pass
def main():
    return 0
""")
        child = subprocess.run(
            _synthetic_child_command(root, _unused_local_port()),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=40,
        )
        receipt = json.loads(
            (root / "guarded-child-receipt.json").read_text(encoding="utf-8")
        )
    assert child.returncode != 0
    assert hits == [], "forbidden import-time connection reached witness"
    assert receipt["status"] == "STOP_PROHIBITED_NETWORK"
    assert receipt["blocked_count"] == receipt["unclassified_count"] == 1
    assert receipt["attempts"] == [{
        "reason": "unclassified_socket_connect",
        "method": "UNKNOWN", "path": "<unclassified>",
    }]


def test_guarded_child_exception_receipt_never_exposes_error_details(tmp_path):
    import json
    import subprocess
    root = _synthetic_root(
        tmp_path, 'raise RuntimeError("SYNTHETIC_SECRET_MUST_NOT_LEAK")\n'
    )
    child = subprocess.run(
        _synthetic_child_command(root, _unused_local_port()),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=40,
    )
    receipt = json.loads((root / "guarded-child-receipt.json").read_text(encoding="utf-8"))
    assert child.returncode != 0
    assert receipt["status"] == "STOP_EXCEPTION"
    assert receipt["blocked_count"] == 0
    assert "SYNTHETIC_SECRET_MUST_NOT_LEAK" not in (
        str(receipt) + child.stdout + child.stderr
    )


def test_guarded_child_rejects_missing_marker_or_unsafe_route_before_launch(tmp_path):
    import subprocess
    root = _synthetic_root(
        tmp_path, 'raise RuntimeError("fixture must not execute")\n'
    )
    (root / ".elysia-guarded-synthetic-root").unlink()
    child = subprocess.run(
        _synthetic_child_command(root, _unused_local_port()),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=40,
    )
    assert child.returncode == 2
    assert "STOP_PREFLIGHT" in child.stderr
    assert not (root / "guarded-child-receipt.json").exists()
    (root / ".elysia-guarded-synthetic-root").write_text(
        "ELYSIA_SYNTHETIC_ACCEPTANCE_V1\n", encoding="utf-8"
    )
    bad_route = _synthetic_child_command(root, _unused_local_port())
    bad_route[-1] = "GET:/api/tags"
    child = subprocess.run(
        bad_route, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=40,
    )
    assert child.returncode == 2
    assert not (root / "guarded-child-receipt.json").exists()
    # A contained Guardian startup cannot happen by merely switching modes.
    (root / "synthetic_fixture.py").unlink()
    contained = _synthetic_child_command(root, _unused_local_port())
    contained[contained.index("synthetic")] = "contained"
    child = subprocess.run(
        contained, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, timeout=40,
    )
    assert child.returncode == 2
    assert not (root / "guarded-child-receipt.json").exists()
