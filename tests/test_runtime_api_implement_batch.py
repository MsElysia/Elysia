"""Contract tests for POST /api/proposals/implement-batch.

Uses the real RuntimeAPIServer, ProposalSystem, and ImplementerAgent.
Fictional proposals live in a temporary directory. The live case binds the
Werkzeug server and calls it over HTTP. No external service is called, and
the plans used here do not write into the repository.
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

_PLAN = "## Step 1: Record the fictional review note\n\nLeave the repository unchanged.\n"


def _write_proposal(root, proposal_id, status, created_at, plan=None, extra=None):
    proposal_path = root / proposal_id
    proposal_path.mkdir(parents=True)
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional proposal",
        "description": "Temporary contract fixture",
        "status": status,
        "created_by": "fictional-operator",
        "created_at": created_at,
        "domain": "elysia_core",
        "history": [],
    }
    if extra:
        metadata.update(extra)
    (proposal_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    if plan is not None:
        design = proposal_path / "design"
        design.mkdir()
        (design / "implementation_plan.md").write_text(plan, encoding="utf-8")
    return proposal_path


def _seed(root):
    _write_proposal(root, "fictional-no-plan", "approved", "2026-11-02T00:00:01Z")
    _write_proposal(
        root,
        "fictional-accepted",
        "accepted",
        "2026-11-02T00:00:02Z",
        plan=_PLAN,
    )
    _write_proposal(
        root,
        "fictional-approved",
        "approved",
        "2026-11-02T00:00:03Z",
        plan=_PLAN,
    )
    _write_proposal(
        root,
        "fictional-draft",
        "proposal",
        "2026-11-02T00:00:04Z",
        plan=_PLAN,
    )
    _write_proposal(
        root,
        "fictional-done",
        "approved",
        "2026-11-02T00:00:05Z",
        plan=_PLAN,
        extra={"implementation_status": "completed"},
    )


def _read_proposal(root, proposal_id):
    return json.loads((root / proposal_id / "metadata.json").read_text(encoding="utf-8"))


def _ids(body):
    return [item["proposal_id"] for item in body["results"]]


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


def _assert_batch_contract(post, root):
    before_approved = (root / "fictional-approved" / "metadata.json").read_text(encoding="utf-8")

    not_object = post("/api/proposals/implement-batch", ["not", "an", "object"])
    assert not_object["status"] == 400
    assert not_object["content_type"].startswith("application/json")
    assert not_object["body"] == {"error": "request body must be a JSON object"}

    bad_flag = post("/api/proposals/implement-batch", {"dry_run": "false"})
    assert bad_flag["status"] == 400
    assert bad_flag["content_type"].startswith("application/json")
    assert bad_flag["body"] == {"error": "dry_run must be a boolean"}
    assert (root / "fictional-approved" / "metadata.json").read_text(encoding="utf-8") == before_approved

    partial = post("/api/proposals/implement-batch", {"dry_run": True})
    assert partial["status"] == 400
    assert partial["content_type"].startswith("application/json")
    body = partial["body"]
    assert body["status"] == "partial"
    assert body["dry_run"] is True
    assert body["total"] == 3
    assert body["successful"] == 2
    assert body["failed"] == 1
    assert body["statuses"] == ["accepted", "approved"]
    assert _ids(body) == ["fictional-approved", "fictional-accepted", "fictional-no-plan"]
    assert "fictional-draft" not in _ids(body)
    assert "fictional-done" not in _ids(body)
    failed = next(item for item in body["results"] if item["proposal_id"] == "fictional-no-plan")
    assert failed["success"] is False
    assert "Implementation plan not found" in failed["error"]
    for proposal_id in ("fictional-approved", "fictional-accepted"):
        item = next(row for row in body["results"] if row["proposal_id"] == proposal_id)
        assert item["success"] is True
        assert item["steps_completed"] == 1
        assert item["steps_total"] == 1

    approved = _read_proposal(root, "fictional-approved")
    assert approved["status"] == "implemented"
    assert approved["implementation_status"] == "completed"
    accepted = _read_proposal(root, "fictional-accepted")
    assert accepted["status"] == "accepted"
    assert accepted["implementation_status"] == "completed"
    assert _read_proposal(root, "fictional-no-plan")["status"] == "approved"
    assert "implementation_status" not in _read_proposal(root, "fictional-no-plan")
    assert _read_proposal(root, "fictional-draft")["status"] == "proposal"
    assert _read_proposal(root, "fictional-done")["implementation_status"] == "completed"
    names = sorted(path.name for path in (root / "fictional-approved").iterdir())
    assert names == ["design", "metadata.json"]

    retry = post("/api/proposals/implement-batch", {"dry_run": True})
    assert retry["status"] == 400
    assert retry["body"]["status"] == "partial"
    assert retry["body"]["total"] == 1
    assert retry["body"]["failed"] == 1
    assert _ids(retry["body"]) == ["fictional-no-plan"]


def _server(root):
    proposals = ProposalSystem(root, event_bus=EventBus(), enable_watcher=False)
    return RuntimeAPIServer(
        status_provider=lambda: {"running": True},
        event_bus=proposals.event_bus,
        proposal_system=proposals,
    )


class TestRuntimeApiImplementBatch:
    def test_batch_contract_through_flask_app(self, tmp_path):
        root = tmp_path / "proposals"
        _seed(root)
        server = _server(root)
        client = server._app.test_client()

        def post(path, payload):
            response = client.post(path, json=payload)
            return {
                "status": response.status_code,
                "content_type": response.content_type,
                "body": response.get_json(),
            }

        _assert_batch_contract(post, root)

        empty_root = tmp_path / "empty-proposals"
        _write_proposal(
            empty_root,
            "fictional-draft-only",
            "proposal",
            "2026-11-02T00:00:06Z",
            plan=_PLAN,
        )
        empty_server = _server(empty_root)
        empty = empty_server._app.test_client().post(
            "/api/proposals/implement-batch",
            json={"dry_run": True},
        )
        assert empty.status_code == 200
        assert empty.content_type.startswith("application/json")
        assert empty.get_json()["status"] == "empty"
        assert empty.get_json()["total"] == 0
        assert empty.get_json()["results"] == []
        assert _read_proposal(empty_root, "fictional-draft-only")["status"] == "proposal"

        unavailable = RuntimeAPIServer(
            status_provider=lambda: {"running": True},
            event_bus=EventBus(),
            proposal_system=None,
        )
        missing = unavailable._app.test_client().post(
            "/api/proposals/implement-batch",
            json={"dry_run": True},
        )
        assert missing.status_code == 503
        assert missing.content_type.startswith("application/json")
        assert missing.get_json() == {"error": "Proposal system not available"}

    def test_batch_contract_through_live_http(self, tmp_path):
        root = tmp_path / "proposals"
        _seed(root)
        server = _server(root)
        server.port = _free_port()
        server.start()
        _wait_until_listening(server)

        def post(path, payload):
            request = urllib.request.Request(
                f"http://{server.host}:{server.port}{path}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    raw = response.read()
                    return {
                        "status": response.status,
                        "content_type": response.headers.get("Content-Type", ""),
                        "body": json.loads(raw.decode("utf-8")),
                    }
            except urllib.error.HTTPError as exc:
                raw = exc.read()
                return {
                    "status": exc.code,
                    "content_type": exc.headers.get("Content-Type", ""),
                    "body": json.loads(raw.decode("utf-8")),
                }

        try:
            _assert_batch_contract(post, root)
        finally:
            server.stop()

    def test_shell_prints_batch_summary(self, tmp_path, capsys, monkeypatch):
        root = tmp_path / "proposals"
        _write_proposal(
            root,
            "fictional-shell",
            "approved",
            "2026-11-02T00:00:07Z",
            plan=_PLAN,
        )
        server = _server(root)
        server.port = _free_port()
        server.start()
        _wait_until_listening(server)
        lines = iter(["help", "implement-batch", "implement-batch dry-run", "exit"])
        monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
        try:
            interactive_shell(server.host, server.port)
        finally:
            server.stop()

        captured = capsys.readouterr()
        assert "implement-batch dry-run|live" in captured.out
        assert "usage: implement-batch dry-run|live" in captured.out
        assert '"status": "completed"' in captured.out
        assert '"dry_run": true' in captured.out
        assert "fictional-shell" in captured.out
        stored = _read_proposal(root, "fictional-shell")
        assert stored["status"] == "implemented"
        assert stored["implementation_status"] == "completed"
        assert captured.err == ""
