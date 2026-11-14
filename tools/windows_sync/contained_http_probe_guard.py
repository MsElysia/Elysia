"""Test-only in-process HTTP egress guard for contained synthetic Dev startup.

Install INSIDE the actual app child before invoking the existing contained
startup entrypoint. A guard in a parent process does NOT cover subprocesses.
No production module or persistent firewall/env/config is changed.

Each allowed HTTP method/path is scoped to the existing Elysia loopback
listener's literal 127.0.0.1:port. No Ollama API is allowed by default.
High-level calls are checked before their transport; unclassified sockets
are refused at connect. A nonzero unclassified event means STOP, never
"zero Ollama probes verified". Events omit URL queries, headers and bodies.

This is an auditable acceptance guard, not an OS firewall/security boundary.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import http.client
import socket
import threading
from typing import Iterable
from urllib import request as urllib_request
from urllib.parse import urlsplit


class ProbeBlocked(OSError):
    """An attempted outbound operation was rejected before transport."""


class ContainedHttpProbeGuard:
    def __init__(self, app_port: int, *, allowed_routes: Iterable[tuple[str, str]]):
        if not isinstance(app_port, int) or not 1 <= app_port <= 65535:
            raise ValueError("A concrete Elysia loopback listener port is required")
        self.app_port = app_port
        self.allowed_routes = frozenset(
            (method.upper(), path)
            for method, path in allowed_routes
        )
        if not self.allowed_routes or any(
            not path.startswith("/") or "?" in path or "#" in path
            or method not in {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"}
            for method, path in self.allowed_routes
        ):
            raise ValueError("Explicit safe method/path pairs are required")
        self.events: list[dict[str, str]] = []
        self.allowed_http_count = 0
        self._lock = threading.Lock()
        self._patches: list[tuple[object, str, object]] = []
        self._authorized: ContextVar[int] = ContextVar("elysia_guard_authorized", default=0)
        self._active = False

    def _record(self, *, reason: str, method: str = "UNKNOWN", path: str = "") -> None:
        # Only known method/path labels; never expose query strings, body or URL.
        public_path = path if path in {
            "/api/tags", "/api/chat", "/api/generate", "/api/status"
        } else ("<other>" if path else "<unclassified>")
        with self._lock:
            self.events.append({
                "reason": reason,
                "method": method if method in {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"} else "UNKNOWN",
                "path": public_path,
            })

    @contextmanager
    def _admit_http(self, method: str, url: str):
        try:
            parsed = urlsplit(str(url))
            port = parsed.port
            hostname = parsed.hostname
            username, password = parsed.username, parsed.password
        except (ValueError, TypeError):
            parsed, port, hostname, username, password = None, None, None, None, None
        m = str(method).upper()
        p = (parsed.path or "/") if parsed is not None else ""
        ok = (
            parsed is not None
            and parsed.scheme == "http"
            and hostname == "127.0.0.1"
            and username is None
            and password is None
            and port == self.app_port
            and (m, p) in self.allowed_routes
        )
        if not ok:
            reason = (
                "unapproved_loopback_http"
                if hostname in {"127.0.0.1", "::1", "localhost"}
                else "non_loopback_http"
            )
            self._record(reason=reason, method=m, path=p)
            raise ProbeBlocked("contained HTTP guard blocked " + reason)
        with self._lock:
            self.allowed_http_count += 1
        token = self._authorized.set(self._authorized.get() + 1)
        try:
            yield
        finally:
            self._authorized.reset(token)

    def _is_authorized_connect(self, destination) -> bool:
        if not (isinstance(destination, tuple) and len(destination) >= 2):
            return False
        host, port = destination[:2]
        return (
            host in ("127.0.0.1", b"127.0.0.1")
            and type(port) is int
            and port == self.app_port
            and self._authorized.get() > 0
        )

    def _patch(self, obj: object, name: str, replacement: object) -> None:
        original = getattr(obj, name)
        setattr(obj, name, replacement)
        self._patches.append((obj, name, original))

    def __enter__(self):
        if self._active:
            raise RuntimeError("guard already installed")
        self._active = True
        try:
            import requests
            import httpx
            from project_guardian.local_memory_chat import LocalOllama

            orig_session = requests.sessions.Session.request
            orig_httpx = httpx.Client.request
            orig_async = httpx.AsyncClient.request
            orig_http_request = http.client.HTTPConnection.request
            orig_urlopen = urllib_request.urlopen
            orig_opener = urllib_request.OpenerDirector.open
            orig_local_ollama = LocalOllama._request
            orig_connect = socket.socket.connect
            orig_connect_ex = socket.socket.connect_ex
            orig_getaddrinfo = socket.getaddrinfo
            orig_sendto = socket.socket.sendto

            def requests_request(session, method, url, *args, **kwargs):
                with self._admit_http(method, url):
                    return orig_session(session, method, url, *args, **kwargs)

            def httpx_request(client, method, url, *args, **kwargs):
                address = str(url)
                if not urlsplit(address).scheme:
                    address = str(client.base_url.join(address))
                with self._admit_http(method, address):
                    return orig_httpx(client, method, url, *args, **kwargs)

            async def httpx_async_request(client, method, url, *args, **kwargs):
                address = str(url)
                if not urlsplit(address).scheme:
                    address = str(client.base_url.join(address))
                with self._admit_http(method, address):
                    return await orig_async(client, method, url, *args, **kwargs)

            def http_request(connection, method, url, *args, **kwargs):
                # Direct http.client is used by LocalOllama. Its _request method
                # is also wrapped because it explicitly calls connect() first.
                address = str(url)
                if not urlsplit(address).scheme:
                    address = f"http://{connection.host}:{connection.port}{address}"
                with self._admit_http(method, address):
                    return orig_http_request(connection, method, url, *args, **kwargs)

            def urlopen(url, data=None, *args, **kwargs):
                if isinstance(url, urllib_request.Request):
                    method, address = url.get_method(), url.full_url
                else:
                    method, address = ("POST" if data is not None else "GET"), str(url)
                with self._admit_http(method, address):
                    return orig_urlopen(url, data, *args, **kwargs)

            def opener_open(opener, fullurl, data=None, *args, **kwargs):
                if isinstance(fullurl, urllib_request.Request):
                    method, address = fullurl.get_method(), fullurl.full_url
                else:
                    method, address = ("POST" if data is not None else "GET"), str(fullurl)
                with self._admit_http(method, address):
                    return orig_opener(opener, fullurl, data, *args, **kwargs)

            def local_ollama_request(model, method, path, *args, **kwargs):
                # Critical: LocalOllama._request connects BEFORE http.client.request.
                # This wrapper captures method/path before that connect can occur.
                address = f"http://127.0.0.1:{model.port}{path}"
                with self._admit_http(method, address):
                    return orig_local_ollama(model, method, path, *args, **kwargs)

            def guarded_connect(sock, destination):
                if sock.family not in {socket.AF_INET, socket.AF_INET6}:
                    return orig_connect(sock, destination)  # local IPC, not TCP/UDP
                if not self._is_authorized_connect(destination):
                    self._record(reason="unclassified_socket_connect")
                    raise ProbeBlocked("contained guard rejected unknown socket connect")
                return orig_connect(sock, destination)

            def guarded_connect_ex(sock, destination):
                if sock.family not in {socket.AF_INET, socket.AF_INET6}:
                    return orig_connect_ex(sock, destination)
                if not self._is_authorized_connect(destination):
                    self._record(reason="unclassified_socket_connect")
                    raise ProbeBlocked("contained guard rejected unknown socket connect_ex")
                return orig_connect_ex(sock, destination)

            def guarded_getaddrinfo(host, port, *args, **kwargs):
                if host not in ("127.0.0.1", b"127.0.0.1"):
                    self._record(reason="non_loopback_dns")
                    raise ProbeBlocked("contained guard rejected DNS target")
                return orig_getaddrinfo(host, port, *args, **kwargs)

            def guarded_sendto(sock, data, *args, **kwargs):
                address = args[-1] if args and isinstance(args[-1], tuple) else kwargs.get("address")
                if sock.family in {socket.AF_INET, socket.AF_INET6} and not self._is_authorized_connect(address):
                    self._record(reason="unclassified_socket_sendto")
                    raise ProbeBlocked("contained guard rejected datagram sendto")
                return orig_sendto(sock, data, *args, **kwargs)

            self._patch(requests.sessions.Session, "request", requests_request)
            self._patch(httpx.Client, "request", httpx_request)
            self._patch(httpx.AsyncClient, "request", httpx_async_request)
            self._patch(http.client.HTTPConnection, "request", http_request)
            self._patch(urllib_request, "urlopen", urlopen)
            self._patch(urllib_request.OpenerDirector, "open", opener_open)
            self._patch(LocalOllama, "_request", local_ollama_request)
            self._patch(socket.socket, "connect", guarded_connect)
            self._patch(socket.socket, "connect_ex", guarded_connect_ex)
            self._patch(socket.socket, "sendto", guarded_sendto)
            self._patch(socket, "getaddrinfo", guarded_getaddrinfo)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, exc_type, exc, tb):
        for obj, name, original in reversed(self._patches):
            setattr(obj, name, original)
        self._patches.clear()
        self._active = False

    def receipt(self) -> dict:
        """Report only method/path classification, never destinations or secrets."""
        with self._lock:
            blocked = list(self.events)
            allowed = self.allowed_http_count
        return {
            "allowed_http_calls": allowed,
            "blocked_count": len(blocked),
            "unclassified_count": sum(
                x["reason"].startswith("unclassified") or x["reason"] == "non_loopback_dns"
                for x in blocked
            ),
            "attempts": blocked,
        }
