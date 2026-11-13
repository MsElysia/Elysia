"""A real implement call must not report success when the lifecycle stays put.

Uses the real RuntimeAPIServer, ProposalSystem, and ImplementerAgent.
Fictional proposals live in a temporary directory. The live case binds the
Werkzeug server and posts over HTTP. File writes stay in a temporary working
directory because this route still builds the implementer with repo_root=Path(".").
No external service is called.
"""

import json
import socket
import time
import urllib.request

import pytest

from elysia.api.server import RuntimeAPIServer
from elysia.core.proposal_system import ProposalSystem
from elysia.events import EventBus


def _write_proposal(root, proposal_id, status):
    proposal_path = root / proposal_id
    (proposal_path / "design").mkdir(parents=True)
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional proposal",
        "description": "Temporary contract fixture",
        "status": status,
        "created_by": "contract-test",
        "created_at": "2026-11-13T00:00:00Z",
        "domain": "elysia_core",
        "history": [],
    }
    plan = (
        "## Step 1: Create file\n\n"
        f"Create {proposal_id}.py\n\n"
        "```python\n"
        f"print('{proposal_id}')\n"
        "```\n"
    )
    (proposal_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (proposal_path / "design" / "implementation_plan.md").write_text(plan, encoding="utf-8")


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


def _stored(proposals, proposal_id):
    return json.loads(
        (proposals.proposals_root / proposal_id / "metadata.json").read_text(encoding="utf-8")
    )


def _assert_contract(post, proposals, cwd):
    blocked = post("/api/proposals/fictional-accepted/implement", {"dry_run": False})
    assert blocked["status"] == 200
    assert blocked["content_type"].startswith("application/json")
    body = blocked["body"]
    assert body["success"] is False
    assert body["error"] == "Invalid transition from accepted to in_implementation"
    assert body["steps_completed"] == 0
    assert body["steps_total"] == 1
    assert body["step_results"] == []
    accepted_file = cwd / "fictional-accepted.py"
    assert not accepted_file.exists()
    stored = _stored(proposals, "fictional-accepted")
    assert stored["status"] == "accepted"
    assert stored["implementation_status"] == "failed"
    assert stored["last_implementation_result"] == body["error"]
    summaries = " ".join(entry.get("change_summary", "") for entry in stored["history"])
    assert "Implementation completed" not in summaries
    assert body["error"] in summaries

    approved = post("/api/proposals/fictional-approved/implement", {"dry_run": False})
    assert approved["status"] == 200
    assert approved["body"]["success"] is True
    assert approved["body"]["steps_completed"] == 1
    approved_file = cwd / "fictional-approved.py"
    assert approved_file.is_file()
    assert approved_file.resolve().parent == cwd.resolve()
    assert approved_file.read_text(encoding="utf-8") == "print('fictional-approved')\n"
    approved_stored = _stored(proposals, "fictional-approved")
    assert approved_stored["status"] == "implemented"
    assert approved_stored["implementation_status"] == "completed"


class TestRuntimeApiImplementLifecycle:
    def test_accepted_status_fails_through_flask_app(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        proposals = ProposalSystem(
            tmp_path / "proposals",
            event_bus=EventBus(),
            enable_watcher=False,
        )
        _write_proposal(proposals.proposals_root, "fictional-accepted", "accepted")
        _write_proposal(proposals.proposals_root, "fictional-approved", "approved")
        server = RuntimeAPIServer(
            status_provider=lambda: {"running": True},
            event_bus=proposals.event_bus,
            proposal_system=proposals,
        )
        client = server._app.test_client()

        def post(path, payload):
            response = client.post(path, json=payload)
            return {
                "status": response.status_code,
                "body": response.get_json(),
                "content_type": response.headers.get("Content-Type", ""),
            }

        _assert_contract(post, proposals, cwd)

    def test_accepted_status_fails_through_live_http(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        proposals = ProposalSystem(
            tmp_path / "proposals",
            event_bus=EventBus(),
            enable_watcher=False,
        )
        _write_proposal(proposals.proposals_root, "fictional-accepted", "accepted")
        _write_proposal(proposals.proposals_root, "fictional-approved", "approved")
        server = RuntimeAPIServer(
            status_provider=lambda: {"running": True},
            event_bus=proposals.event_bus,
            host="127.0.0.1",
            port=_free_port(),
            proposal_system=proposals,
        )
        server.start()
        try:
            _wait_until_listening(server)

            def post(path, payload):
                return _http(server, path, payload)

            _assert_contract(post, proposals, cwd)
        finally:
            server.stop()


def _http(server, path, payload):
    url = f"http://{server.host}:{server.port}{path}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        raw = response.read()
        return {
            "status": response.status,
            "body": json.loads(raw.decode("utf-8")),
            "content_type": response.headers.get("Content-Type", ""),
        }
