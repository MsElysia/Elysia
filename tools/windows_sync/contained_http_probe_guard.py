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
import socket
import sys
import threading
from typing import Iterable
from urllib.parse import urlsplit


class ProbeBlocked(OSError):
    """An attempted outbound operation was rejected before transport."""


class ContainedHttpProbeGuard:
    def __init__(self, app_port: int, *, allowed_routes: Iterable[tuple[str, str]],
                 _synthetic_only: bool = False):
        if not isinstance(app_port, int) or not 1 <= app_port <= 65535:
            raise ValueError("A concrete Elysia loopback listener port is required")
        self.app_port = app_port
        self._synthetic_only = _synthetic_only
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
        self.dashboard_probes: list[dict[str, str]] = []
        self._dashboard_panel_type = None
        self._dashboard_check_codes = {}
        self._lock = threading.Lock()
        self._patches: list[tuple[object, str, object]] = []
        self._authorized: ContextVar[int] = ContextVar("elysia_guard_authorized", default=0)
        # Windows asyncio creates its self-wakeup IPC via stdlib socketpair(),
        # which internally uses a temporary IPv4 loopback TCP connection.
        # Permit ONLY that immediate stdlib call, never arbitrary loopback.
        self._socketpair_ipc: ContextVar[int] = ContextVar("elysia_guard_socketpair", default=0)
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
            and (
                (port == self.app_port and self._authorized.get() > 0)
                or self._socketpair_ipc.get() > 0
            )
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
            # Patch raw sockets and DNS BEFORE importing third-party HTTP
            # clients or project code. An import-time network attempt must
            # fail closed and leave an unclassified STOP receipt.
            orig_connect = socket.socket.connect
            orig_connect_ex = socket.socket.connect_ex
            orig_getaddrinfo = socket.getaddrinfo
            orig_sendto = socket.socket.sendto
            orig_socketpair = socket.socketpair

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
                    # Recognize ONLY the two reviewed dashboard source methods,
                    # not arbitrary raw connect_ex in a loosely scoped context.
                    # Caller code and panel instance must match the real class.
                    operation = None
                    if (
                        sock.family == socket.AF_INET
                        and sock.type == socket.SOCK_STREAM
                        and isinstance(destination, tuple)
                        and len(destination) == 2
                        and destination[0] == "127.0.0.1"
                        and type(destination[1]) is int
                        and destination[1] == self.app_port
                    ):
                        caller = sys._getframe(1)
                        candidate = self._dashboard_check_codes.get(caller.f_code)
                        panel = caller.f_locals.get("self")
                        if type(panel) is self._dashboard_panel_type:
                            if (
                                candidate == "port_availability"
                                and caller.f_locals.get("host") == "127.0.0.1"
                                and caller.f_locals.get("port") == self.app_port
                                and panel.host == "127.0.0.1"
                                and panel.port == self.app_port
                            ):
                                operation = candidate
                            elif (
                                candidate == "server_readiness"
                                and panel.host == "127.0.0.1"
                                and (panel._actual_port or panel.port) == self.app_port
                            ):
                                operation = candidate
                    if operation is None:
                        self._record(reason="unclassified_socket_connect")
                        raise ProbeBlocked("contained guard rejected unknown socket connect_ex")
                    with self._lock:
                        self.dashboard_probes.append({"operation": operation})
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

            def guarded_socketpair(*args, **kwargs):
                # Windows implementation creates a one-off local TCP pair.
                # Keep permission scoped to this stdlib operation and restore
                # it before any caller can use the returned socket handles.
                token = self._socketpair_ipc.set(self._socketpair_ipc.get() + 1)
                try:
                    return orig_socketpair(*args, **kwargs)
                finally:
                    self._socketpair_ipc.reset(token)

            self._patch(socket.socket, "connect", guarded_connect)
            self._patch(socket.socket, "connect_ex", guarded_connect_ex)
            self._patch(socket.socket, "sendto", guarded_sendto)
            self._patch(socket, "getaddrinfo", guarded_getaddrinfo)
            self._patch(socket, "socketpair", guarded_socketpair)

            import http.client
            from urllib import request as urllib_request
            import requests
            import httpx
            # Ordinary guard users retain the existing project-specific hooks.
            # The disposable synthetic CLI does NOT import or start Guardian,
            # so it has no business loading project/native voice components.
            if not self._synthetic_only:
                from project_guardian.local_memory_chat import LocalOllama
                from project_guardian.ui_control_panel import UIControlPanel

                self._dashboard_panel_type = UIControlPanel
                self._dashboard_check_codes = {
                    UIControlPanel._check_port_available.__code__: "port_availability",
                    UIControlPanel._wait_for_server_ready.__code__: "server_readiness",
                }

            orig_session = requests.sessions.Session.request
            orig_session_send = requests.sessions.Session.send
            orig_httpx = httpx.Client.request
            orig_async = httpx.AsyncClient.request
            orig_httpx_hop = httpx.Client._send_single_request
            orig_async_hop = httpx.AsyncClient._send_single_request
            orig_http_request = http.client.HTTPConnection.request
            orig_urlopen = urllib_request.urlopen
            orig_opener = urllib_request.OpenerDirector.open
            if not self._synthetic_only:
                orig_local_ollama = LocalOllama._request
            def requests_request(session, method, url, *args, **kwargs):
                with self._admit_http(method, url):
                    return orig_session(session, method, url, *args, **kwargs)

            def requests_send(session, request, *args, **kwargs):
                # Requests redirects call Session.send, bypassing Session.request.
                # Inspect every prepared request before transport can run.
                with self._admit_http(request.method, request.url):
                    return orig_session_send(session, request, *args, **kwargs)

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

            def httpx_send_hop(client, request, *args, **kwargs):
                # HTTPX redirects call _send_single_request for every hop,
                # without reentering Client.request or Client.send.
                with self._admit_http(request.method, str(request.url)):
                    return orig_httpx_hop(client, request, *args, **kwargs)

            async def httpx_async_send_hop(client, request, *args, **kwargs):
                with self._admit_http(request.method, str(request.url)):
                    return await orig_async_hop(client, request, *args, **kwargs)

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

            self._patch(requests.sessions.Session, "request", requests_request)
            self._patch(requests.sessions.Session, "send", requests_send)
            self._patch(httpx.Client, "request", httpx_request)
            self._patch(httpx.AsyncClient, "request", httpx_async_request)
            self._patch(httpx.Client, "_send_single_request", httpx_send_hop)
            self._patch(httpx.AsyncClient, "_send_single_request", httpx_async_send_hop)
            self._patch(http.client.HTTPConnection, "request", http_request)
            self._patch(urllib_request, "urlopen", urlopen)
            self._patch(urllib_request.OpenerDirector, "open", opener_open)
            if not self._synthetic_only:
                self._patch(LocalOllama, "_request", local_ollama_request)
            return self
        except BaseException:
            # A disposable supported CLI never resumes normal execution on
            # setup failure; retain any installed hooks through process exit.
            # Ordinary context-manager use must remain fully reversible.
            if not self._synthetic_only:
                self.__exit__(None, None, None)
            raise

    def __exit__(self, exc_type, exc, tb):
        for obj, name, original in reversed(self._patches):
            setattr(obj, name, original)
        self._patches.clear()
        self._dashboard_check_codes.clear()
        self._dashboard_panel_type = None
        self._active = False

    def receipt(self) -> dict:
        """Report only method/path classification, never destinations or secrets."""
        with self._lock:
            blocked = list(self.events)
            allowed = self.allowed_http_count
            local_probes = list(self.dashboard_probes)
        return {
            "allowed_http_calls": allowed,
            "dashboard_probe_count": len(local_probes),
            "dashboard_probes": local_probes,
            "blocked_count": len(blocked),
            "unclassified_count": sum(
                x["reason"].startswith("unclassified") or x["reason"] == "non_loopback_dns"
                for x in blocked
            ),
            "attempts": blocked,
        }


# Supported CLI: trusted, single-threaded synthetic fixtures only. This
# is not a general Python sandbox or an actual Guardian startup launcher.
_GUARDED_ROOT_MARKER = ".elysia-guarded-synthetic-root"
_GUARDED_ROOT_CONTENT = "ELYSIA_SYNTHETIC_ACCEPTANCE_V1\n"
_CHILD_SCRUB_NAMES = (
    "ELYSIA_LOCAL_MODEL", "ELYSIA_THUMB_DRIVE", "ELYSIA_THUMB_DRIVE_SECONDARY",
    "OPENAI_API_KEY", "OPENROUTER_API_KEY", "COHERE_API_KEY",
    "HUGGINGFACE_API_KEY", "REPLICATE_API_KEY", "ALPHA_VANTAGE_API_KEY",
    "BRAVE_SEARCH_API_KEY", "GUMROAD_ACCESS_TOKEN", "STRIPE_SECRET_KEY",
    "STRIPE_PUBLISHABLE_KEY", "ANTHROPIC_API_KEY", "SMTP_PASSWORD",
    "ELYSIA_SMTP_PASSWORD",
)
_RECEIPT_NAME = "guarded-child-receipt.json"
_COMPLETE = "COMPLETE_TEST_HARNESS_ONLY"
_SCOPE = "synthetic_child_only_not_os_containment"
_LIFECYCLE = "managed_atexit_single_thread"
_CHILD_STATUSES = {
    _COMPLETE, "STOP_EXCEPTION", "STOP_CHILD", "STOP_PROHIBITED_NETWORK",
    "STOP_UNSUPPORTED_LIFECYCLE",
}


def _plain_path(path, *, directory=False):
    """Local identity checks, not protection against concurrent replacement."""
    import os
    import stat
    info = os.lstat(path)
    if (stat.S_ISLNK(info.st_mode) or
            getattr(info, "st_file_attributes", 0) &
            getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
        raise ValueError("aliased acceptance path")
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("not a directory")
    elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("not an independent regular file")
    return info


def _guarded_root(raw):
    """Require a fresh root below the interpreter's trusted temp anchor."""
    import tempfile
    from pathlib import Path
    candidate = Path(raw)
    temp = Path(tempfile.gettempdir()).resolve(strict=True)
    if (not candidate.is_absolute() or ".." in candidate.parts or
            temp not in candidate.parents):
        raise ValueError("unsafe disposable root")
    current = candidate
    while current != temp:
        _plain_path(current, directory=True)
        current = current.parent
    if candidate.resolve(strict=True) != candidate:
        raise ValueError("aliased disposable root")
    marker = candidate / _GUARDED_ROOT_MARKER
    if _plain_path(marker).st_size > 128:
        raise ValueError("invalid marker")
    if marker.read_text(encoding="utf-8") != _GUARDED_ROOT_CONTENT:
        raise ValueError("synthetic root marker invalid")
    _plain_path(candidate / "synthetic_fixture.py")
    if {item.name for item in candidate.iterdir()} != {
        _GUARDED_ROOT_MARKER, "synthetic_fixture.py",
    }:
        raise ValueError("synthetic root must be fresh")
    return candidate


def _synthetic_child_launch(root, app_port):
    """Build the only supported child invocation and an allowlisted env."""
    import os
    from pathlib import Path
    import sysconfig
    # No wholesale parent environment copy, no credential values read.
    env = {
        name: os.environ[name]
        for name in ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "TMPDIR",
                     "LANG", "LC_ALL")
        if name in os.environ
    }
    # -I -S disables environment/site startup hooks. Add only this trusted
    # test interpreter's installed package directories, not .pth processing.
    dirs = sorted({
        str(Path(sysconfig.get_path(kind)).resolve(strict=True))
        for kind in ("purelib", "platlib")
    })
    cmd = [
        sys.executable, "-I", "-S", "-B", str(Path(__file__).resolve()),
        "--isolated-worker", "--mode", "synthetic",
        "--disposable-root", str(root), "--app-port", str(app_port),
        "--route", "GET:/api/status",
    ]
    for directory in dirs:
        cmd.extend(("--dependency-dir", directory))
    return cmd, env


def _valid_final_receipt(report):
    """A green exit alone or an incomplete/provisional receipt is never PASS."""
    if not isinstance(report, dict) or set(report) != {
        "status", "scope", "mode", "lifecycle", "finalized",
        "workers_quiescent", "callbacks_completed", "cleanup_errors",
        "allowed_http_calls", "dashboard_probe_count", "dashboard_probes",
        "blocked_count", "unclassified_count", "attempts",
    }:
        return False
    if (report["status"] not in _CHILD_STATUSES or
            report["scope"] != _SCOPE or report["mode"] != "synthetic" or
            report["lifecycle"] != _LIFECYCLE or report["finalized"] is not True or
            type(report["workers_quiescent"]) is not bool):
        return False
    counts = ("callbacks_completed", "cleanup_errors", "allowed_http_calls",
              "dashboard_probe_count", "blocked_count", "unclassified_count")
    if any(type(report[k]) is not int or report[k] < 0 for k in counts):
        return False
    if (not isinstance(report["attempts"], list) or
            not isinstance(report["dashboard_probes"], list) or
            len(report["attempts"]) != report["blocked_count"] or
            len(report["dashboard_probes"]) != report["dashboard_probe_count"] or
            report["unclassified_count"] > report["blocked_count"]):
        return False
    if report["status"] == _COMPLETE and (
            report["blocked_count"] or report["unclassified_count"] or
            report["cleanup_errors"] or not report["workers_quiescent"]):
        return False
    return True


def run_guarded_synthetic_child(root, app_port):
    """Supervise one trusted synthetic subprocess; never run Guardian."""
    import json
    import subprocess
    result = {"returncode": 2, "child_returncode": None, "status": "STOP_PREFLIGHT"}
    try:
        root = _guarded_root(root)
        cmd, env = _synthetic_child_launch(root, app_port)
    except (OSError, ValueError, TypeError):
        return result
    try:
        # Child output is not a trusted receipt. Do not forward it or secrets.
        child = subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=40)
    except (OSError, subprocess.TimeoutExpired):
        result["status"] = "STOP_CHILD_PROCESS"
        return result
    result["child_returncode"] = child.returncode
    result["status"] = "STOP_RECEIPT_OR_EXIT"
    try:
        path = root / _RECEIPT_NAME
        if _plain_path(path).st_size > 262144:
            return result
        report = json.loads(path.read_text(encoding="utf-8"))
        if not _valid_final_receipt(report):
            return result
    except (OSError, UnicodeError, ValueError, TypeError):
        return result
    if child.returncode == 0 and report["status"] == _COMPLETE:
        result.update(returncode=0, status=_COMPLETE)
    elif child.returncode != 0 and report["status"] != _COMPLETE:
        result.update(returncode=1, status=report["status"])
    # A finalizer failure after a nominal return, or any exit/receipt
    # disagreement, is STOP as well. Only the supervisor declares completion.
    return result


def _guarded_child_main(argv=None):
    import argparse
    import atexit
    import _thread
    import json
    import os
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Isolated synthetic child only")
    parser.add_argument("--isolated-worker", action="store_true")
    parser.add_argument("--mode", choices=("synthetic", "contained"), required=True)
    parser.add_argument("--disposable-root", required=True)
    parser.add_argument("--app-port", required=True, type=int)
    parser.add_argument("--route", required=True, action="append")
    parser.add_argument("--dependency-dir", action="append", default=[])
    parser.add_argument("--allow-contained-start", action="store_true")
    args = parser.parse_args(argv)
    try:
        if (not args.isolated_worker or not sys.flags.isolated or
                not sys.flags.no_site or not sys.flags.dont_write_bytecode or
                "site" in sys.modules or args.mode != "synthetic" or
                args.allow_contained_start):
            raise ValueError("unsupported bootstrap or runtime mode")
        if any(name in os.environ for name in _CHILD_SCRUB_NAMES):
            raise ValueError("unscrubbed bootstrap environment")
        if any(name == prefix or name.startswith(prefix + ".")
               for name in sys.modules
               for prefix in ("requests", "httpx", "http.client", "urllib.request",
                              "project_guardian", "elysia_sub_guardian")):
            raise ValueError("HTTP or project modules already loaded")
        root = _guarded_root(args.disposable_root)
        if not (1 <= args.app_port <= 65535) or args.route != ["GET:/api/status"]:
            raise ValueError("unreviewed port or route")
        if not args.dependency_dir:
            raise ValueError("missing isolated dependency search path")
        for directory in args.dependency_dir:
            path = Path(directory)
            if not path.is_absolute() or not path.is_dir():
                raise ValueError("invalid dependency directory")
            if str(path) not in sys.path:
                sys.path.append(str(path))
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as check:
            check.bind(("127.0.0.1", args.app_port))
    except (OSError, ValueError, TypeError):
        return 2

    os.environ["ELYSIA_DISPOSABLE_ROOT"] = str(root)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    guard = ContainedHttpProbeGuard(
        args.app_port, allowed_routes={("GET", "/api/status")}, _synthetic_only=True,
    )
    status = "STOP_EXCEPTION"
    out = None
    pending = root / ".guarded-child-receipt.pending"
    final_path = root / _RECEIPT_NAME
    callbacks = []
    callbacks_completed = cleanup_errors = 0
    draining = unsupported = False
    ready = False
    saved_register = atexit.register

    def quiescent():
        return (not unsupported and
                threading.enumerate() == [threading.main_thread()])

    def final_status():
        if guard.receipt()["blocked_count"]:
            return "STOP_PROHIBITED_NETWORK"
        if not quiescent():
            return "STOP_UNSUPPORTED_LIFECYCLE"
        if cleanup_errors:
            return "STOP_EXCEPTION"
        return status

    def finalize():
        # Native interpreter atexit callback, registered before loading any
        # dependency or fixture. Managed callbacks already ran under the
        # guards; instrumentation is still installed during interpreter exit.
        if out is None:
            return
        try:
            report = guard.receipt()
            report.update(
                status=final_status(), scope=_SCOPE, mode="synthetic",
                lifecycle=_LIFECYCLE, finalized=True,
                workers_quiescent=quiescent(),
                callbacks_completed=callbacks_completed,
                cleanup_errors=cleanup_errors,
            )
            json.dump(report, out, sort_keys=True)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
            out.close()
            # Publish only AFTER a complete successful write/close. Link is
            # exclusive (cannot overwrite an existing receipt). The supervisor
            # also rejects any final file whose link count is not exactly one.
            os.link(pending, final_path)
            pending.unlink()
        except BaseException:
            # No plaintext exception details, no provisional success file.
            # A missing/invalid receipt or exit disagreement is STOP.
            try:
                out.close()
            except BaseException:
                pass

    def reject_lifecycle():
        nonlocal unsupported
        unsupported = True
        raise RuntimeError("unsupported synthetic lifecycle")

    def register(callback, *a, **kw):
        if draining or len(callbacks) >= 128:
            reject_lifecycle()
        if not callable(callback):
            raise TypeError("callback must be callable")
        callbacks.append((callback, a, kw))
        return callback

    def unregister(callback):
        if draining:
            reject_lifecycle()
        callbacks[:] = [item for item in callbacks if item[0] != callback]

    def deny_worker(*a, **kw):
        reject_lifecycle()

    def audit_lifecycle(event, _args):
        # A tracked Python process-creation attempt is an unsupported
        # lifecycle even if the fixture catches the exception. This is not
        # native/OS subprocess containment or a general security sandbox.
        if event in {"subprocess.Popen", "os.system", "os.spawn", "os.exec",
                     "os.fork", "os.forkpty", "os.posix_spawn", "os.startfile",
                     "os.startfile/2"}:
            reject_lifecycle()

    # Use public registration, not private interpreter exit-function APIs.
    # The supported single-thread fixture uses ordinary atexit.register /
    # unregister, with LIFO callbacks executed exactly once as controlled
    # teardown before main returns its final exit code. Native/destructor,
    # child-process, arbitrary threading, and untrusted code are NOT covered.
    saved_register(finalize)
    atexit.register = register
    atexit.unregister = unregister
    threading.Thread.start = deny_worker
    _thread.start_new_thread = deny_worker
    sys.addaudithook(audit_lifecycle)
    try:
        guard.__enter__()  # Intentionally lifetime-scoped in this child ONLY.
        ready = True
        import runpy
        fixture = runpy.run_path(str(root / "synthetic_fixture.py"),
                                 run_name="__guarded_synthetic_fixture__")
        main = fixture.get("main")
        if not callable(main):
            raise ValueError("missing synthetic callable")
        result = main()
        status = _COMPLETE if type(result) is int and result == 0 else "STOP_CHILD"
    except BaseException:
        status = "STOP_EXCEPTION"
    finally:
        if ready:
            draining = True
            for callback, a, kw in reversed(callbacks):
                try:
                    callback(*a, **kw)
                except BaseException:
                    cleanup_errors += 1
                finally:
                    callbacks_completed += 1
            callbacks.clear()
        elif callbacks:
            # Failed guard initialization: running callbacks without the
            # complete guard is unsupported and cannot be a success.
            unsupported = True
        if (atexit.register is not register or atexit.unregister is not unregister
                or threading.Thread.start is not deny_worker
                or _thread.start_new_thread is not deny_worker):
            unsupported = True
        # Reserve exclusively after controlled cleanup. No provisional
        # green receipt: the real interpreter-exit finalizer writes it.
        try:
            if os.path.lexists(final_path):
                return 2
            out = pending.open("x", encoding="utf-8")
        except OSError:
            return 2

    # Normal Python interpreter exit, no forced exit and no restoration
    # before cleanup. Non-CLI guard context managers still restore patches.
    return 0 if final_status() == _COMPLETE else 1


if __name__ == "__main__":
    raise SystemExit(_guarded_child_main())
