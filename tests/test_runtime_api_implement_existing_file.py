"""A live implement call must not store a proposal as implemented when creation was skipped.

Uses the real RuntimeAPIServer, ProposalSystem, and ImplementerAgent.
Fictional proposals live in a temporary directory. The live case binds the
Werkzeug server and posts over HTTP. File writes stay in a temporary working
directory because this route still builds the implementer with repo_root=Path(".").
No external service is called.
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


def _write_proposal(root, proposal_id, plan):
    proposal_path = root / proposal_id
    (proposal_path / "design").mkdir(parents=True)
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional proposal",
        "description": "Temporary contract fixture",
        "status": "approved",
        "created_by": "contract-test",
        "created_at": "2026-11-08T00:00:00Z",
        "domain": "elysia_core",
        "history": [],
    }
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


def _seed(root, cwd):
    _write_proposal(
        root,
        "fictional-existing-file",
        "## Step 1: Create file fictional-existing-sentinel.txt\n\n"
        "Create fictional-existing-sentinel.txt\n\n```\nshould-not-replace\n```\n",
    )
    _write_proposal(
        root,
        "fictional-existing-test",
        "## Step 1: Add tests for fictional-add-sentinel.txt\n\n"
        "Add fictional-add-sentinel.txt\n\n```\nshould-not-replace\n```\n",
    )
    _write_proposal(
        root,
        "fictional-new-file",
        "## Step 1: Create file fictional-new-sentinel.txt\n\n"
        "Create fictional-new-sentinel.txt\n\n```\ncreated-bytes\n```\n",
    )
    (cwd / "fictional-existing-sentinel.txt").write_text("original-bytes", encoding="utf-8")
    (cwd / "fictional-add-sentinel.txt").write_text("original-add", encoding="utf-8")


def _stored(proposals, proposal_id):
    return json.loads(
        (proposals.proposals_root / proposal_id / "metadata.json").read_text(encoding="utf-8")
    )


def _assert_contract(post, proposals, cwd):
    existing = post("/api/proposals/fictional-existing-file/implement", {"dry_run": False})
    assert existing["status"] == 200
    assert existing["content_type"].startswith("application/json")
    assert existing["body"]["success"] is False
    assert existing["body"]["error"] == "Step 1 failed: File already exists and was not created"
    assert existing["body"]["steps_completed"] == 0
    assert existing["body"]["step_results"][0]["created"] is False
    assert existing["body"]["step_results"][0]["step_type"] == "create_file"
    assert (cwd / "fictional-existing-sentinel.txt").read_text(encoding="utf-8") == "original-bytes"
    existing_stored = _stored(proposals, "fictional-existing-file")
    assert existing_stored["status"] == "implementation_failed"
    assert existing_stored["implementation_status"] == "failed"
    summaries = " ".join(entry.get("change_summary", "") for entry in existing_stored["history"])
    assert "Implementation completed" not in summaries
    assert "File already exists and was not created" in summaries

    added = post("/api/proposals/fictional-existing-test/implement", {"dry_run": False})
    assert added["status"] == 200
    assert added["body"]["success"] is False
    assert added["body"]["error"] == "Step 1 failed: File already exists and was not created"
    assert added["body"]["step_results"][0]["created"] is False
    assert (cwd / "fictional-add-sentinel.txt").read_text(encoding="utf-8") == "original-add"
    added_stored = _stored(proposals, "fictional-existing-test")
    assert added_stored["status"] == "implementation_failed"
    assert added_stored["implementation_status"] == "failed"

    created = post("/api/proposals/fictional-new-file/implement", {"dry_run": False})
    assert created["status"] == 200
    assert created["body"]["success"] is True
    sentinel = cwd / "fictional-new-sentinel.txt"
    assert sentinel.is_file()
    assert sentinel.resolve().parent == cwd.resolve()
    assert sentinel.read_text(encoding="utf-8") == "created-bytes\n"
    created_stored = _stored(proposals, "fictional-new-file")
    assert created_stored["status"] == "implemented"
    assert created_stored["implementation_status"] == "completed"


class TestRuntimeApiImplementExistingFile:
    def test_existing_create_fails_through_flask_app(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        proposals = ProposalSystem(
            tmp_path / "proposals",
            event_bus=EventBus(),
            enable_watcher=False,
        )
        _seed(proposals.proposals_root, cwd)
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

    def test_existing_create_fails_through_live_http(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        proposals = ProposalSystem(
            tmp_path / "proposals",
            event_bus=EventBus(),
            enable_watcher=False,
        )
        _seed(proposals.proposals_root, cwd)
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
