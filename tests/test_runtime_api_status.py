"""Contract tests for GET /api/status on the runtime API server.

Uses RuntimeAPIServer over Flask and live Werkzeug HTTP. The healthy runtime
case calls ElysiaRuntime.get_status without init(), so no API keys, WebScout,
or external services are loaded. Proposal counting uses ProposalSystem with
its watcher off and a fictional proposal directory. Failure cases use fictional
providers.
"""

import json
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import pytest

from elysia.api.server import RuntimeAPIServer
from elysia.core.proposal_system import ProposalSystem
from elysia.events import EventBus
from elysia.runtime import ElysiaRuntime
from elysia.config import RuntimeConfig
from elysia.shell import show_status
from elysia.status import print_status


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _server(provider, port=0):
    return RuntimeAPIServer(
        status_provider=provider,
        event_bus=EventBus(),
        host="127.0.0.1",
        port=port,
    )


def _healthy():
    return {"running": True, "mode": "core", "env": "dev", "proposal_count": 0}


def _raise_fictional():
    raise RuntimeError("fictional-status-failure")


def _assert_contract(get):
    healthy = get(_healthy)
    assert healthy["status"] == 200
    assert healthy["body"] == {
        "running": True,
        "mode": "core",
        "env": "dev",
        "proposal_count": 0,
    }
    assert healthy["content_type"].startswith("application/json")

    invalid = get(lambda: ["not-a-status"])
    assert invalid["status"] == 500
    assert invalid["content_type"].startswith("application/json")
    assert invalid["body"]["error"] == "Invalid status format"
    assert invalid["body"]["running"] is False
    assert invalid["body"]["status_available"] is False
    assert invalid["body"]["components"] == {"api_server": True}

    failed = get(_raise_fictional)
    assert failed["status"] == 500
    assert failed["content_type"].startswith("application/json")
    assert failed["body"]["error"] == "fictional-status-failure"
    assert failed["body"]["running"] is False
    assert failed["body"]["status_available"] is False
    assert failed["body"]["components"] == {"api_server": True}


def _request(server):
    url = f"http://{server.host}:{server.port}/api/status"
    request = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = response.read()
            return {
                "status": response.status,
                "body": json.loads(payload.decode("utf-8")),
                "content_type": response.headers.get("Content-Type", ""),
            }
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        return {
            "status": exc.code,
            "body": json.loads(payload.decode("utf-8")),
            "content_type": exc.headers.get("Content-Type", ""),
        }


def _wait_until_listening(server):
    last_error = None
    for _ in range(40):
        try:
            with socket.create_connection((server.host, server.port), timeout=0.1):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.05)
    pytest.fail(f"API server did not accept connections: {last_error}")


class TestRuntimeApiStatus:
    def test_status_contract_through_flask_app(self):
        def get(provider):
            server = _server(provider)
            response = server._app.test_client().get("/api/status")
            return {
                "status": response.status_code,
                "body": response.get_json(),
                "content_type": response.headers.get("Content-Type", ""),
            }

        _assert_contract(get)

    def test_status_contract_through_live_http(self):
        started = []

        def get(provider):
            server = _server(provider, port=_free_port())
            server.start()
            started.append(server)
            _wait_until_listening(server)
            return _request(server)

        try:
            _assert_contract(get)
        finally:
            for server in started:
                server.stop()

    def test_real_runtime_status_over_live_http(self, tmp_path):
        proposal_root = tmp_path / "proposals"
        proposal_dir = proposal_root / "fictional-status"
        proposal_dir.mkdir(parents=True)
        (proposal_dir / "metadata.json").write_text(
            json.dumps({"proposal_id": "fictional-status", "title": "Fictional"}),
            encoding="utf-8",
        )
        (proposal_root / "not-a-proposal.txt").write_text("skip", encoding="utf-8")

        runtime = ElysiaRuntime(
            RuntimeConfig(
                mode="core",
                env="dev",
                proposals_root=proposal_root,
                enable_api=False,
                enable_webscout=False,
                require_api_keys=False,
            )
        )
        runtime._running = True
        runtime._start_time = datetime.now(timezone.utc)
        runtime.proposal_system = ProposalSystem(
            proposals_root=proposal_root,
            event_bus=None,
            enable_watcher=False,
        )
        server = _server(runtime.get_status, port=_free_port())
        runtime.api_server = server
        server.start()
        try:
            _wait_until_listening(server)
            body = _request(server)
        finally:
            server.stop()

        assert body["status"] == 200
        assert body["body"]["running"] is True
        assert body["body"]["mode"] == "core"
        assert body["body"]["env"] == "dev"
        assert body["body"]["proposal_count"] == 1
        assert body["body"]["components"]["api_server"] is True
        assert body["body"]["components"]["proposal_system"] is True
        assert body["body"]["components"]["webscout"] is False
        assert body["body"]["uptime_seconds"] >= 0
        assert "status_available" not in body["body"]

    def test_status_clients_print_error_not_running(self, capsys):
        failed = _server(_raise_fictional, port=_free_port())
        healthy = _server(_healthy, port=_free_port())
        failed.start()
        healthy.start()
        try:
            _wait_until_listening(failed)
            _wait_until_listening(healthy)

            assert show_status(failed.host, failed.port) == 500
            error_out = capsys.readouterr()
            assert error_out.out == ""
            assert "HTTP 500: fictional-status-failure" in error_out.err
            assert "running" not in error_out.err
            assert "{}" not in error_out.out

            with pytest.raises(SystemExit) as printed:
                print_status(failed.host, failed.port)
            assert printed.value.code == 1
            cli_out = capsys.readouterr()
            assert cli_out.out == ""
            assert "HTTP 500: fictional-status-failure" in cli_out.err
            assert "Runtime not reachable." not in cli_out.err

            assert show_status(healthy.host, healthy.port) == 200
            healthy_out = capsys.readouterr()
            printed_status = json.loads(healthy_out.out)
            assert printed_status["running"] is True
            assert healthy_out.err == ""

            closed = _free_port()
            with pytest.raises(SystemExit) as unreachable:
                print_status("127.0.0.1", closed)
            assert unreachable.value.code == 1
            missed = capsys.readouterr()
            assert missed.out == ""
            assert "Runtime not reachable." in missed.err
        finally:
            failed.stop()
            healthy.stop()
