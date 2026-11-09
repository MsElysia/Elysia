"""A live implement call must not create a file outside the repository.

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
from pathlib import Path

import pytest

from elysia.api.server import RuntimeAPIServer
from elysia.core.proposal_system import ProposalSystem
from elysia.events import EventBus

OUTSIDE_ERROR = "Step 1 failed: File path is outside the repository"
ROOT_ESCAPE = Path("/fictional-elysia-escape.txt")


def _write_proposal(root, proposal_id, plan):
    proposal_path = root / proposal_id
    (proposal_path / "design").mkdir(parents=True)
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional proposal",
        "description": "Temporary contract fixture",
        "status": "approved",
        "created_by": "contract-test",
        "created_at": "2026-11-09T00:00:00Z",
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


def _seed(root, cwd, outside):
    _write_proposal(
        root,
        "fictional-outside-file",
        f"## Step 1: Create file {outside}\n\n"
        f"Create {outside}\n\n```\nshould-not-write\n```\n",
    )
    _write_proposal(
        root,
        "fictional-outside-test",
        f"## Step 1: Add tests for {outside}\n\n"
        f"Add {outside}\n\n```\nshould-not-write\n```\n",
    )
    _write_proposal(
        root,
        "fictional-link-escape",
        "## Step 1: Create file escape-link/fictional-link-escape.txt\n\n"
        "Create escape-link/fictional-link-escape.txt\n\n```\nshould-not-write\n```\n",
    )
    _write_proposal(
        root,
        "fictional-dotdot-escape",
        "## Step 1: Create file ../fictional-elysia-escape.txt\n\n"
        "Create ../fictional-elysia-escape.txt\n\n```\nshould-not-write\n```\n",
    )
    _write_proposal(
        root,
        "fictional-new-file",
        "## Step 1: Create file fictional-new-sentinel.txt\n\n"
        "Create fictional-new-sentinel.txt\n\n```\ncreated-bytes\n```\n",
    )
    link = cwd / "escape-link"
    link.symlink_to(outside.parent, target_is_directory=True)


def _stored(proposals, proposal_id):
    return json.loads(
        (proposals.proposals_root / proposal_id / "metadata.json").read_text(encoding="utf-8")
    )


def _assert_failed(post, proposals, proposal_id, outside_file):
    result = post(f"/api/proposals/{proposal_id}/implement", {"dry_run": False})
    assert result["status"] == 200
    assert result["content_type"].startswith("application/json")
    assert result["body"]["success"] is False
    assert result["body"]["error"] == OUTSIDE_ERROR
    assert result["body"]["steps_completed"] == 0
    assert result["body"]["step_results"][0]["created"] is False
    assert result["body"]["step_results"][0]["error"] == "File path is outside the repository"
    assert outside_file.exists() is False
    stored = _stored(proposals, proposal_id)
    assert stored["status"] == "implementation_failed"
    assert stored["implementation_status"] == "failed"
    summaries = " ".join(entry.get("change_summary", "") for entry in stored["history"])
    assert "Implementation completed" not in summaries
    assert "File path is outside the repository" in summaries


def _assert_contract(post, proposals, cwd, outside):
    _assert_failed(post, proposals, "fictional-outside-file", outside)
    _assert_failed(post, proposals, "fictional-outside-test", outside)
    _assert_failed(
        post,
        proposals,
        "fictional-link-escape",
        outside.parent / "fictional-link-escape.txt",
    )
    _assert_failed(post, proposals, "fictional-dotdot-escape", ROOT_ESCAPE)

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


class TestRuntimeApiImplementOutsidePath:
    def test_outside_create_fails_through_flask_app(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        outside_dir = tmp_path / "outside"
        cwd.mkdir()
        outside_dir.mkdir()
        outside = outside_dir / "fictional-escape.txt"
        monkeypatch.chdir(cwd)
        proposals = ProposalSystem(
            tmp_path / "proposals",
            event_bus=EventBus(),
            enable_watcher=False,
        )
        _seed(proposals.proposals_root, cwd, outside)
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

        try:
            _assert_contract(post, proposals, cwd, outside)
        finally:
            if ROOT_ESCAPE.exists():
                ROOT_ESCAPE.unlink()

    def test_outside_create_fails_through_live_http(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        outside_dir = tmp_path / "outside"
        cwd.mkdir()
        outside_dir.mkdir()
        outside = outside_dir / "fictional-escape.txt"
        monkeypatch.chdir(cwd)
        proposals = ProposalSystem(
            tmp_path / "proposals",
            event_bus=EventBus(),
            enable_watcher=False,
        )
        _seed(proposals.proposals_root, cwd, outside)
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

            _assert_contract(post, proposals, cwd, outside)
        finally:
            server.stop()
            if ROOT_ESCAPE.exists():
                ROOT_ESCAPE.unlink()


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
