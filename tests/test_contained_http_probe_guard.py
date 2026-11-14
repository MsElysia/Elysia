"""Task022: actual client API pre-connect denial and real Elysia loopback allowance.

One synthetic process, no real owner files, model, Ollama server, credentials or
external network. A forbidden endpoint has a REAL local witness listener whose
request counter must remain at zero. Guard wrappers are removed after each run.
"""
from __future__ import annotations

import asyncio
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
    old_dns = socket.getaddrinfo
    old_session = requests.sessions.Session.request
    old_httpx = httpx.Client.request
    old_urllib = urllib_request.urlopen
    old_ollama = LocalOllama._request
    guard = ContainedHttpProbeGuard(5078, allowed_routes={("GET", "/api/status")})
    with pytest.raises(RuntimeError, match="synthetic failure"):
        with guard:
            assert socket.socket.connect is not old_connect
            raise RuntimeError("synthetic failure")
    assert socket.socket.connect is old_connect
    assert socket.getaddrinfo is old_dns
    assert requests.sessions.Session.request is old_session
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
