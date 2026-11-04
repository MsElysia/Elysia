"""Contract tests for proposal reads on the runtime API.

A fictional proposals directory is served by RuntimeAPIServer through Flask's
test client and through live Werkzeug HTTP. ProposalSystem runs with its
watcher off. No API keys, WebScout, or external services are loaded.

One metadata file is a JSON object. The others are invalid JSON, a JSON array,
and JSON null. A sentinel metadata file sits in the parent directory so a
proposal id of ``..`` would escape the proposals root if the API passed it to
ProposalSystem.get_proposal.
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
from elysia.shell import interactive_shell


UNREADABLE = ["fictional-array", "fictional-broken", "fictional-null"]


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


def _write_tree(tmp_path):
    root = tmp_path / "proposals"
    root.mkdir()
    sentinel = tmp_path / "metadata.json"
    sentinel.write_text(
        json.dumps(
            {
                "proposal_id": "..",
                "title": "SENTINEL-OUTSIDE",
                "status": "proposal",
            }
        ),
        encoding="utf-8",
    )
    readable = {
        "proposal_id": "fictional-readable",
        "title": "Readable",
        "status": "proposal",
        "created_by": "test",
        "created_at": "2026-01-01T00:00:00Z",
    }
    readable_dir = root / "fictional-readable"
    readable_dir.mkdir()
    readable_file = readable_dir / "metadata.json"
    readable_file.write_text(json.dumps(readable), encoding="utf-8")
    broken = root / "fictional-broken" / "metadata.json"
    broken.parent.mkdir()
    broken.write_text("{not-json", encoding="utf-8")
    array = root / "fictional-array" / "metadata.json"
    array.parent.mkdir()
    array.write_text("[1, 2]", encoding="utf-8")
    null_file = root / "fictional-null" / "metadata.json"
    null_file.parent.mkdir()
    null_file.write_text("null", encoding="utf-8")
    (root / "notes.txt").write_text("not a proposal", encoding="utf-8")
    return {
        "root": root,
        "sentinel": sentinel,
        "broken": broken,
        "array": array,
        "null_file": null_file,
        "readable_file": readable_file,
        "sentinel_bytes": sentinel.read_bytes(),
        "broken_bytes": broken.read_bytes(),
        "array_bytes": array.read_bytes(),
        "null_bytes": null_file.read_bytes(),
    }


def _system(tree):
    return ProposalSystem(
        proposals_root=tree["root"],
        event_bus=None,
        enable_watcher=False,
    )


def _server(tree, port=0):
    return RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=EventBus(),
        host="127.0.0.1",
        port=port,
        proposal_system=_system(tree),
    )


def _assert_contract(call, tree):
    listed = call("GET", "/api/proposals")
    assert listed["status"] == 200
    assert listed["content_type"].startswith("application/json")
    assert listed["body"]["count"] == 1
    assert [item["proposal_id"] for item in listed["body"]["proposals"]] == [
        "fictional-readable"
    ]
    assert listed["body"]["unreadable"] == UNREADABLE
    assert "SENTINEL-OUTSIDE" not in listed["text"]
    assert "<html" not in listed["text"].lower()

    filtered = call("GET", "/api/proposals?status=proposal")
    assert filtered["status"] == 200
    assert filtered["body"]["count"] == 1
    assert filtered["body"]["unreadable"] == UNREADABLE

    other = call("GET", "/api/proposals?status=implemented")
    assert other["status"] == 200
    assert other["body"]["proposals"] == []
    assert other["body"]["count"] == 0
    assert other["body"]["unreadable"] == UNREADABLE

    readable = call("GET", "/api/proposals/fictional-readable")
    assert readable["status"] == 200
    assert readable["body"]["title"] == "Readable"
    assert readable["body"]["status"] == "proposal"

    missing = call("GET", "/api/proposals/fictional-missing")
    assert missing["status"] == 404
    assert missing["body"] == {"error": "Proposal not found"}

    for proposal_id in UNREADABLE:
        broken = call("GET", f"/api/proposals/{proposal_id}")
        assert broken["status"] == 500
        assert broken["content_type"].startswith("application/json")
        assert broken["body"] == {
            "error": "Proposal metadata is unreadable",
            "proposal_id": proposal_id,
        }
        implementation = call("GET", f"/api/proposals/{proposal_id}/implementation")
        assert implementation["status"] == 500
        assert implementation["body"]["error"] == "Proposal metadata is unreadable"

    escaped = call("GET", "/api/proposals/..")
    assert escaped["status"] == 400
    assert escaped["body"]["error"] == "invalid proposal id"
    assert "SENTINEL-OUTSIDE" not in escaped["text"]

    implementation = call("GET", "/api/proposals/fictional-readable/implementation")
    assert implementation["status"] == 200
    assert implementation["body"]["implementation_status"] == "not_started"
    missing_impl = call("GET", "/api/proposals/fictional-missing/implementation")
    assert missing_impl["status"] == 404

    chat_ok = call(
        "POST",
        "/api/chat",
        {"message": "hello", "context": "proposal:fictional-readable"},
    )
    assert chat_ok["status"] == 200
    assert "Readable" in chat_ok["body"]["response"]

    chat_broken = call(
        "POST",
        "/api/chat",
        {"message": "hello", "context": "proposal:fictional-broken"},
    )
    assert chat_broken["status"] == 500
    assert chat_broken["body"]["error"] == "Proposal metadata is unreadable"

    chat_escape = call(
        "POST",
        "/api/chat",
        {"message": "hello", "context": "proposal:.."},
    )
    assert chat_escape["status"] == 400
    assert "SENTINEL-OUTSIDE" not in chat_escape["text"]

    for proposal_id, path in (
        ("fictional-broken", tree["broken"]),
        ("fictional-array", tree["array"]),
        ("fictional-null", tree["null_file"]),
    ):
        before = path.read_bytes()
        approved = call("POST", f"/api/proposals/{proposal_id}/approve", {})
        rejected = call(
            "POST",
            f"/api/proposals/{proposal_id}/reject",
            {"reason": "fictional-reason"},
        )
        transitioned = call(
            "POST",
            f"/api/proposals/{proposal_id}/status",
            {"status": "approved"},
        )
        implemented = call("POST", f"/api/proposals/{proposal_id}/implement", {})
        assert approved["status"] == 500
        assert rejected["status"] == 500
        assert transitioned["status"] == 500
        assert implemented["status"] == 500
        assert path.read_bytes() == before

    escaped_approve = call("POST", "/api/proposals/../approve", {})
    escaped_transition = call(
        "POST",
        "/api/proposals/../status",
        {"status": "approved"},
    )
    escaped_implement = call("POST", "/api/proposals/../implement", {"dry_run": True})
    assert escaped_approve["status"] == 400
    assert escaped_transition["status"] == 400
    assert escaped_implement["status"] == 400
    for result in (escaped_approve, escaped_transition, escaped_implement):
        assert "SENTINEL-OUTSIDE" not in result["text"]
    assert tree["sentinel"].read_bytes() == tree["sentinel_bytes"]

    approved = call(
        "POST",
        "/api/proposals/fictional-readable/approve",
        {"approver": "fictional-operator"},
    )
    assert approved["status"] == 200
    assert approved["body"]["status"] == "approved"
    stored = json.loads(tree["readable_file"].read_text(encoding="utf-8"))
    assert stored["status"] == "approved"


class TestRuntimeApiProposalReads:
    def test_read_contract_through_flask_app(self, tmp_path):
        tree = _write_tree(tmp_path)
        client = _server(tree)._app.test_client()

        def call(method, path, body=None):
            if method == "GET":
                response = client.get(path)
            else:
                response = client.post(path, json={} if body is None else body)
            return {
                "status": response.status_code,
                "body": response.get_json(),
                "content_type": response.content_type,
                "text": response.get_data(as_text=True),
            }

        _assert_contract(call, tree)

    def test_read_contract_through_live_http(self, tmp_path):
        tree = _write_tree(tmp_path)
        server = _server(tree, port=_free_port())
        server.start()
        try:
            _wait_until_listening(server)

            def call(method, path, body=None):
                data = None if method == "GET" else json.dumps({} if body is None else body).encode()
                request = urllib.request.Request(
                    f"http://{server.host}:{server.port}{path}",
                    data=data,
                    method=method,
                    headers={"Content-Type": "application/json"} if data else {},
                )
                try:
                    with urllib.request.urlopen(request, timeout=5) as response:
                        payload = response.read()
                        return {
                            "status": response.status,
                            "body": json.loads(payload.decode("utf-8")),
                            "content_type": response.headers.get("Content-Type", ""),
                            "text": payload.decode("utf-8"),
                        }
                except urllib.error.HTTPError as exc:
                    payload = exc.read()
                    return {
                        "status": exc.code,
                        "body": json.loads(payload.decode("utf-8")),
                        "content_type": exc.headers.get("Content-Type", ""),
                        "text": payload.decode("utf-8"),
                    }

            _assert_contract(call, tree)
        finally:
            server.stop()

    def test_shell_prints_unreadable_proposals(self, tmp_path, monkeypatch, capsys):
        tree = _write_tree(tmp_path)
        server = _server(tree, port=_free_port())
        server.start()
        answers = iter(["proposals"])

        def fake_input(_prompt):
            try:
                return next(answers)
            except StopIteration:
                raise EOFError

        monkeypatch.setattr("builtins.input", fake_input)
        try:
            _wait_until_listening(server)
            interactive_shell(server.host, server.port)
        finally:
            server.stop()

        printed = capsys.readouterr().out
        assert "fictional-readable: Readable [proposal]" in printed
        for proposal_id in UNREADABLE:
            assert f"{proposal_id}: metadata unreadable" in printed
        assert "SENTINEL-OUTSIDE" not in printed
        assert "notes.txt" not in printed

    def test_missing_proposal_system_is_json_503(self):
        server = RuntimeAPIServer(
            status_provider=lambda: {"running": True},
            event_bus=EventBus(),
            proposal_system=None,
        )
        response = server._app.test_client().get("/api/proposals")
        assert response.status_code == 503
        assert response.content_type.startswith("application/json")
        assert response.get_json()["error"] == "Proposal system not available"
