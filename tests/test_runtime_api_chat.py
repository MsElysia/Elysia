"""Contract tests for POST /api/chat.

General chat is not wired to a runtime. These tests use the real RuntimeAPIServer
and, for proposal context, the real ProposalSystem with a fictional proposal.
The live case binds the Werkzeug server and posts over HTTP. No external service
is called. An attached architect object is not asked to answer.
"""

import json
import socket
import time
import urllib.error
import urllib.request

import pytest

from elysia.api.server import RuntimeAPIServer
from elysia.core.proposal_system import ProposalSystem
from elysia.events import EventBus
from elysia.shell import send_chat


FICTIONAL_MESSAGE = "fictional-ping"
FICTIONAL_PROPOSAL = "fictional-chat-proposal"


class RecordingArchitect:
    """Stand-in for an attached architect. The route must not call it."""

    def __init__(self):
        self.calls = []

    def chat(self, *args, **kwargs):
        self.calls.append(("chat", args, kwargs))
        return "should-not-run"

    def route_command(self, *args, **kwargs):
        self.calls.append(("route_command", args, kwargs))
        return {"status": "should-not-run"}


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


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


def _write_proposal(root):
    proposal = root / FICTIONAL_PROPOSAL
    proposal.mkdir()
    metadata = {
        "proposal_id": FICTIONAL_PROPOSAL,
        "title": "Fictional lattice note",
        "status": "proposal",
        "created_by": "fictional-operator",
        "created_at": "2026-10-30T00:00:00+00:00",
    }
    (proposal / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")


def _server(tmp_path, port=None, architect=None, with_proposal=True):
    root = tmp_path / "proposals"
    root.mkdir()
    if with_proposal:
        _write_proposal(root)
    bus = EventBus()
    proposals = ProposalSystem(root, event_bus=bus, enable_watcher=False)
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=bus,
        host="127.0.0.1",
        port=port or 8123,
        proposal_system=proposals,
        architect=architect,
    )
    return server, bus, architect


def _assert_chat_contract(post, bus, architect):
    general = post({"message": FICTIONAL_MESSAGE})
    assert general["status"] == 501
    assert general["content_type"].startswith("application/json")
    assert general["body"] == {
        "error": "Chat is not connected to a runtime",
        "answered": False,
        "status": "not_answered",
    }
    assert "Echo" not in json.dumps(general["body"])
    assert architect.calls == []
    assert [event for event in bus.get_recent_events() if event["type"] == "chat"] == []

    attached = post({"message": FICTIONAL_MESSAGE, "context": "general"})
    assert attached["status"] == 501
    assert attached["body"]["answered"] is False
    assert architect.calls == []

    missing = post({})
    assert missing["status"] == 400
    assert missing["body"] == {"error": "message is required", "answered": False}

    blank = post({"message": "   "})
    assert blank["status"] == 400
    assert blank["body"]["error"] == "message is required"

    not_text = post({"message": 12})
    assert not_text["status"] == 400
    assert not_text["body"]["error"] == "message is required"

    not_object = post(["fictional-ping"])
    assert not_object["status"] == 400
    assert not_object["body"] == {
        "error": "request body must be a JSON object",
        "answered": False,
    }

    bad_context = post({"message": FICTIONAL_MESSAGE, "context": 3})
    assert bad_context["status"] == 400
    assert bad_context["body"]["error"] == "context must be a string"

    empty_proposal = post({"message": FICTIONAL_MESSAGE, "context": "proposal:"})
    assert empty_proposal["status"] == 400
    assert empty_proposal["body"]["error"] == "proposal id is required"

    unknown = post(
        {"message": FICTIONAL_MESSAGE, "context": "proposal:missing-fictional"}
    )
    assert unknown["status"] == 404
    assert unknown["body"]["error"] == "Proposal not found"
    assert unknown["body"]["answered"] is False

    answered = post(
        {
            "message": "what is the status?",
            "context": f"proposal:{FICTIONAL_PROPOSAL}",
        }
    )
    assert answered["status"] == 200
    assert answered["body"]["answered"] is True
    assert answered["body"]["status"] == "answered"
    assert answered["body"]["response"] == (
        "Proposal 'Fictional lattice note' status: proposal"
    )
    events = [event for event in bus.get_recent_events() if event["type"] == "chat"]
    assert len(events) == 1
    assert events[0]["source"] == "api"
    assert events[0]["type"] == "chat"
    assert events[0]["payload"]["answered"] is True
    assert architect.calls == []


class TestRuntimeApiChat:
    def test_status_contract_through_flask_app(self, tmp_path):
        architect = RecordingArchitect()
        server, bus, architect = _server(tmp_path, architect=architect)
        client = server._app.test_client()

        def post(payload):
            response = client.post("/api/chat", json=payload)
            return {
                "status": response.status_code,
                "body": response.get_json(),
                "content_type": response.headers.get("Content-Type", ""),
            }

        _assert_chat_contract(post, bus, architect)

    def test_status_contract_through_live_http(self, tmp_path):
        architect = RecordingArchitect()
        server, bus, architect = _server(
            tmp_path, port=_free_port(), architect=architect
        )
        server.start()
        try:
            _wait_until_listening(server)

            def post(payload):
                request = urllib.request.Request(
                    f"http://{server.host}:{server.port}/api/chat",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(request, timeout=5) as response:
                        raw = response.read()
                        return {
                            "status": response.status,
                            "body": json.loads(raw.decode("utf-8")),
                            "content_type": response.headers.get("Content-Type", ""),
                        }
                except urllib.error.HTTPError as exc:
                    raw = exc.read()
                    return {
                        "status": exc.code,
                        "body": json.loads(raw.decode("utf-8")),
                        "content_type": exc.headers.get("Content-Type", ""),
                    }

            _assert_chat_contract(post, bus, architect)
        finally:
            server.stop()

    def test_missing_proposal_system_is_unavailable(self):
        server = RuntimeAPIServer(
            status_provider=lambda: {"running": True},
            event_bus=EventBus(),
        )
        response = server._app.test_client().post(
            "/api/chat",
            json={"message": FICTIONAL_MESSAGE, "context": "proposal:fictional"},
        )
        assert response.status_code == 503
        assert response.get_json() == {
            "error": "Proposal system not available",
            "answered": False,
        }

    def test_shell_prints_live_unanswered_error(self, tmp_path, capsys):
        architect = RecordingArchitect()
        server, _bus, architect = _server(
            tmp_path, port=_free_port(), architect=architect
        )
        server.start()
        try:
            _wait_until_listening(server)
            status = send_chat(server.host, server.port, FICTIONAL_MESSAGE)
        finally:
            server.stop()

        captured = capsys.readouterr()
        assert status == 501
        assert captured.out == ""
        assert captured.err == (
            "[error] HTTP 501: Chat is not connected to a runtime\n"
        )
        assert architect.calls == []

    def test_shell_prints_live_proposal_answer(self, tmp_path, capsys):
        server, _bus, _architect = _server(tmp_path, port=_free_port())
        server.start()
        try:
            _wait_until_listening(server)
            status = send_chat(
                server.host,
                server.port,
                "what is the status?",
                context=f"proposal:{FICTIONAL_PROPOSAL}",
            )
        finally:
            server.stop()

        captured = capsys.readouterr()
        assert status == 200
        assert (
            captured.out
            == "Proposal 'Fictional lattice note' status: proposal\n"
        )
        assert captured.err == ""
