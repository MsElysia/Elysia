"""Contract tests for proposal list filters and decision routes.

Uses the real RuntimeAPIServer and ProposalSystem. Fictional proposals live
in a temporary directory. The live case binds the Werkzeug server and talks
HTTP on 127.0.0.1. No external service is called.

Approval and rejection metadata are reported from the stored proposal. This
checkout's lifecycle manager changes status without saving those fields; the
API must say so instead of echoing an unsaved reason.
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


DECISION = "fictional-decision"
RESEARCH = "fictional-research"
REJECT = "fictional-reject"


def _metadata(proposal_id, status, title):
    return {
        "proposal_id": proposal_id,
        "title": title,
        "status": status,
        "created_by": "fictional-operator",
        "created_at": "2026-10-31T00:00:00+00:00",
    }


def _write_proposal(root, proposal_id, status, title):
    proposal = root / proposal_id
    proposal.mkdir()
    (proposal / "metadata.json").write_text(
        json.dumps(_metadata(proposal_id, status, title)),
        encoding="utf-8",
    )


def _read_proposal(root, proposal_id):
    return json.loads((root / proposal_id / "metadata.json").read_text(encoding="utf-8"))


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


def _seed(root):
    root.mkdir()
    _write_proposal(root, DECISION, "proposal", "Fictional lattice note")
    _write_proposal(root, RESEARCH, "research", "Fictional research")
    _write_proposal(root, REJECT, "proposal", "Fictional rejection")


def _server(root, port=None):
    bus = EventBus()
    proposals = ProposalSystem(root, event_bus=bus, enable_watcher=False)
    server = RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=bus,
        host="127.0.0.1",
        port=port or 8123,
        proposal_system=proposals,
    )
    return server, proposals


def _assert_contract(call, root):
    unknown = call("GET", "/api/proposals?status=not-a-status")
    assert unknown["status"] == 400
    assert unknown["content_type"].startswith("application/json")
    assert unknown["body"]["error"] == "status filter must be a proposal lifecycle status"
    assert unknown["body"]["status"] == "not-a-status"
    assert "proposals" not in unknown["body"]

    blank = call("GET", "/api/proposals?status=")
    assert blank["status"] == 400
    assert blank["body"]["status"] == ""

    listed = call("GET", "/api/proposals?status=proposal")
    assert listed["status"] == 200
    assert listed["body"]["status"] == "proposal"
    assert listed["body"]["count"] == 2
    assert {item["proposal_id"] for item in listed["body"]["proposals"]} == {DECISION, REJECT}

    everything = call("GET", "/api/proposals")
    assert everything["status"] == 200
    assert everything["body"]["count"] == 3
    assert "status" not in everything["body"]

    for path in (
        "/api/proposals/missing-fictional/approve",
        "/api/proposals/missing-fictional/reject",
        "/api/proposals/missing-fictional/status",
    ):
        missing = call("POST", path, {"approver": "fictional-operator", "status": "approved"})
        assert missing["status"] == 404
        assert missing["content_type"].startswith("application/json")
        assert missing["body"] == {"error": "Proposal not found"}

    array_body = call("POST", f"/api/proposals/{DECISION}/approve", raw=b"[1,2,3]")
    assert array_body["status"] == 400
    assert array_body["content_type"].startswith("application/json")
    assert array_body["body"] == {"error": "request body must be a JSON object"}
    assert _read_proposal(root, DECISION)["status"] == "proposal"

    broken = call("POST", f"/api/proposals/{DECISION}/approve", raw=b"{")
    assert broken["status"] == 400
    assert broken["body"]["error"] == "request body must be a JSON object"

    bad_actor = call("POST", f"/api/proposals/{DECISION}/approve", {"approver": 12})
    assert bad_actor["status"] == 400
    assert bad_actor["body"] == {"error": "approver must be a non-empty string"}
    assert _read_proposal(root, DECISION)["status"] == "proposal"

    blocked = call(
        "POST",
        f"/api/proposals/{RESEARCH}/approve",
        {"approver": "fictional-operator"},
    )
    assert blocked["status"] == 400
    assert blocked["body"]["error"] == "Invalid transition from research to approved"
    assert _read_proposal(root, RESEARCH)["status"] == "research"

    approved = call(
        "POST",
        f"/api/proposals/{DECISION}/approve",
        {"approver": "fictional-operator"},
    )
    stored = _read_proposal(root, DECISION)
    assert approved["status"] == 200
    assert stored["status"] == "approved"
    assert approved["body"]["proposal_id"] == DECISION
    assert approved["body"]["stored_status"] == "approved"
    assert approved["body"]["status"] == "approved"
    assert approved["body"]["approved_by"] == stored.get("approved_by")
    assert approved["body"]["approval_recorded"] is (stored.get("approval_status") == "approved")
    if approved["body"]["approval_recorded"]:
        assert "warning" not in approved["body"]
    else:
        assert approved["body"]["warning"] == "Approval metadata was not stored"
        assert approved["body"]["approved_by"] is None

    again = call(
        "POST",
        f"/api/proposals/{DECISION}/approve",
        {"approver": "fictional-operator"},
    )
    assert again["status"] == 200
    assert again["body"]["status"] == "unchanged"
    assert again["body"]["stored_status"] == "approved"
    assert _read_proposal(root, DECISION)["status"] == "approved"

    rejected = call(
        "POST",
        f"/api/proposals/{REJECT}/reject",
        {"rejector": "fictional-operator", "reason": "fictional-reason"},
    )
    stored_reject = _read_proposal(root, REJECT)
    assert rejected["status"] == 200
    assert stored_reject["status"] == "rejected"
    assert rejected["body"]["status"] == "rejected"
    assert rejected["body"]["stored_status"] == "rejected"
    assert rejected["body"]["rejection_reason"] == stored_reject.get("rejection_reason")
    assert rejected["body"]["reason_recorded"] is (
        stored_reject.get("rejection_reason") == "fictional-reason"
    )
    if rejected["body"]["reason_recorded"]:
        assert "warning" not in rejected["body"]
    else:
        assert rejected["body"]["warning"] == "Rejection reason was not stored"
        assert "fictional-reason" not in json.dumps(rejected["body"])

    same = call(
        "POST",
        f"/api/proposals/{REJECT}/status",
        {"status": "rejected", "actor": "fictional-operator"},
    )
    assert same["status"] == 200
    assert same["body"] == {
        "status": "unchanged",
        "proposal_id": REJECT,
        "stored_status": "rejected",
    }

    moved = call(
        "POST",
        f"/api/proposals/{RESEARCH}/status",
        {"status": "design", "actor": "fictional-operator"},
    )
    assert moved["status"] == 200
    assert moved["body"]["status"] == "updated"
    assert moved["body"]["new_status"] == "design"
    assert moved["body"]["stored_status"] == "design"
    assert _read_proposal(root, RESEARCH)["status"] == "design"

    illegal = call(
        "POST",
        f"/api/proposals/{RESEARCH}/status",
        {"status": "approved", "actor": "fictional-operator"},
    )
    assert illegal["status"] == 400
    assert "Invalid transition" in illegal["body"]["error"]
    assert _read_proposal(root, RESEARCH)["status"] == "design"

    missing_status = call("POST", f"/api/proposals/{RESEARCH}/status", {})
    assert missing_status["status"] == 400
    assert missing_status["body"] == {"error": "status is required"}

    bad_reason = call(
        "POST",
        f"/api/proposals/{DECISION}/reject",
        {"reason": ["fictional-reason"]},
    )
    assert bad_reason["status"] == 400
    assert bad_reason["body"] == {"error": "reason must be a string"}
    assert _read_proposal(root, DECISION)["status"] == "approved"


class TestProposalDecisions:
    def test_decision_contract_through_flask_app(self, tmp_path):
        root = tmp_path / "proposals"
        _seed(root)
        server, proposals = _server(root)

        def call(method, path, payload=None, raw=None):
            client = server._app.test_client()
            if method == "GET":
                response = client.get(path)
            elif raw is not None:
                response = client.post(path, data=raw, content_type="application/json")
            else:
                response = client.post(path, json=payload)
            content_type = response.content_type or ""
            body = response.get_json(silent=True)
            return {"status": response.status_code, "content_type": content_type, "body": body}

        try:
            _assert_contract(call, root)
        finally:
            proposals.shutdown()

    def test_decision_contract_through_live_http(self, tmp_path):
        root = tmp_path / "proposals"
        _seed(root)
        server, proposals = _server(root, port=_free_port())
        server.start()
        _wait_until_listening(server)

        def call(method, path, payload=None, raw=None):
            data = raw if raw is not None else (None if payload is None else json.dumps(payload).encode())
            headers = {"Content-Type": "application/json"} if data is not None else {}
            req = urllib.request.Request(
                f"http://127.0.0.1:{server.port}{path}",
                data=data,
                headers=headers,
                method=method,
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    raw_body = resp.read().decode("utf-8")
                    status = resp.status
                    content_type = resp.headers.get("Content-Type", "")
            except urllib.error.HTTPError as exc:
                raw_body = exc.read().decode("utf-8", errors="replace")
                status = exc.code
                content_type = exc.headers.get("Content-Type", "")
            body = json.loads(raw_body) if raw_body else None
            return {"status": status, "content_type": content_type, "body": body}

        try:
            _assert_contract(call, root)
        finally:
            server.stop()
            proposals.shutdown()

    def test_missing_proposal_system_is_unavailable(self):
        server = RuntimeAPIServer(
            status_provider=lambda: {"running": True},
            event_bus=EventBus(),
            proposal_system=None,
        )
        client = server._app.test_client()
        listed = client.get("/api/proposals")
        assert listed.status_code == 503
        assert listed.get_json() == {"error": "Proposal system not available"}
        approved = client.post("/api/proposals/fictional-decision/approve", json={})
        assert approved.status_code == 503
        assert approved.get_json() == {"error": "Proposal system not available"}

    def test_shell_prints_stored_decision_and_api_error(self, tmp_path, monkeypatch, capsys):
        root = tmp_path / "proposals"
        _seed(root)
        server, proposals = _server(root, port=_free_port())
        server.start()
        _wait_until_listening(server)
        commands = iter(
            [
                "approve missing-fictional",
                f"approve {DECISION}",
                "exit",
            ]
        )
        monkeypatch.setattr("builtins.input", lambda _prompt="": next(commands))
        try:
            interactive_shell("127.0.0.1", server.port)
        finally:
            server.stop()
            proposals.shutdown()

        captured = capsys.readouterr()
        assert "HTTP 404: Proposal not found" in captured.err
        assert "Approval metadata was not stored" in captured.err or "approval_recorded" in captured.out
        payload = json.loads(captured.out[captured.out.find("{") : captured.out.rfind("}") + 1])
        stored = _read_proposal(root, DECISION)
        assert stored["status"] == "approved"
        assert payload["stored_status"] == "approved"
        assert payload["approval_recorded"] is (stored.get("approval_status") == "approved")
