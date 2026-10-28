"""Contract tests for POST /api/proposals/<id>/implement.

Uses the real RuntimeAPIServer, ProposalSystem, and ImplementerAgent.
Fictional proposals live in a temporary directory. The live case binds the
Werkzeug server and posts over HTTP. No external service is called, and the
plans used here do not write into the repository.
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


def _write_proposal(root, proposal_id, status, plan=None):
    proposal_path = root / proposal_id
    (proposal_path / "design").mkdir(parents=True)
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional proposal",
        "description": "Temporary contract fixture",
        "status": status,
        "created_by": "contract-test",
        "created_at": "2026-10-28T00:00:00Z",
        "domain": "elysia_core",
        "history": [],
    }
    (proposal_path / "metadata.json").write_text(
        json.dumps(metadata), encoding="utf-8"
    )
    if plan is not None:
        (proposal_path / "design" / "implementation_plan.md").write_text(
            plan, encoding="utf-8"
        )
    return proposal_path


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


def _assert_contract(post, proposals):
    draft = post("/api/proposals/fictional-draft/implement", {})
    assert draft["status"] == 400
    assert draft["content_type"].startswith("application/json")
    assert draft["body"]["success"] is False
    assert "not in 'accepted' or 'approved' status" in draft["body"]["error"]
    assert proposals.get_proposal("fictional-draft")["status"] == "proposal"

    missing = post("/api/proposals/fictional-missing/implement", {})
    assert missing["status"] == 404
    assert missing["content_type"].startswith("application/json")
    assert missing["body"]["success"] is False
    assert missing["body"]["error"] == "Proposal fictional-missing not found"

    no_plan = post("/api/proposals/fictional-no-plan/implement", {})
    assert no_plan["status"] == 400
    assert no_plan["body"]["success"] is False
    assert no_plan["body"]["error"] == (
        "Implementation plan not found for fictional-no-plan"
    )

    bad_step = post("/api/proposals/fictional-bad-step/implement", {"dry_run": False})
    assert bad_step["status"] == 400
    assert bad_step["body"]["success"] is False
    assert "Could not extract file path" in bad_step["body"]["error"]
    assert bad_step["body"]["steps_completed"] == 0

    dry = post(
        "/api/proposals/fictional-dry-run/implement",
        {"dry_run": True},
    )
    assert dry["status"] == 200
    assert dry["content_type"].startswith("application/json")
    assert dry["body"]["success"] is True
    assert dry["body"]["steps_completed"] == 1
    assert dry["body"]["steps_total"] == 1
    assert dry["body"]["step_results"][0]["dry_run"] is True

    not_object = post("/api/proposals/fictional-draft/implement", ["not", "an", "object"])
    assert not_object["status"] == 400
    assert not_object["content_type"].startswith("application/json")
    assert not_object["body"] == {"error": "request body must be a JSON object"}
    assert proposals.get_proposal("fictional-draft")["status"] == "proposal"


class TestRuntimeApiImplement:
    def test_status_contract_through_flask_app(self, tmp_path):
        proposals = ProposalSystem(tmp_path / "proposals", event_bus=EventBus(), enable_watcher=False)
        _seed(proposals.proposals_root)
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

        _assert_contract(post, proposals)

    def test_status_contract_through_live_http(self, tmp_path):
        proposals = ProposalSystem(tmp_path / "proposals", event_bus=EventBus(), enable_watcher=False)
        _seed(proposals.proposals_root)
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
                url = f"http://{server.host}:{server.port}{path}"
                request = urllib.request.Request(
                    url,
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

            _assert_contract(post, proposals)
        finally:
            server.stop()

    def test_missing_proposal_system_is_unavailable(self):
        server = RuntimeAPIServer(
            status_provider=lambda: {"running": True},
            event_bus=EventBus(),
        )
        response = server._app.test_client().post(
            "/api/proposals/fictional-draft/implement",
            json={},
        )
        assert response.status_code == 503
        assert response.get_json() == {"error": "Proposal system not available"}
        assert response.headers.get("Content-Type", "").startswith("application/json")


def _seed(root):
    _write_proposal(root, "fictional-draft", "proposal")
    _write_proposal(root, "fictional-no-plan", "approved")
    _write_proposal(
        root,
        "fictional-bad-step",
        "approved",
        plan=(
            "## Step 1: Create file placeholder\n\n"
            "No filesystem path is given for this fictional step.\n"
        ),
    )
    _write_proposal(
        root,
        "fictional-dry-run",
        "approved",
        plan="## Step 1: Record the fictional review note\n\nLeave the repository unchanged.\n",
    )
