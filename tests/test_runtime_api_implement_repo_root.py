"""Implement writes beside the proposal store, or into an attached repo.

Uses the real RuntimeAPIServer, ProposalSystem, and ImplementerAgent.
Fictional proposals live in a temporary directory. The live case binds the
Werkzeug server and posts over HTTP. No external service is called.
"""

import json
import socket
import time
import urllib.request
from pathlib import Path

import pytest

from elysia.agents.implementer import ImplementerAgent
from elysia.api.server import RuntimeAPIServer
from elysia.core.proposal_system import ProposalSystem
from elysia.events import EventBus


def _write_proposal(root, proposal_id, filename):
    proposal_path = root / proposal_id
    (proposal_path / "design").mkdir(parents=True)
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional proposal",
        "description": "Temporary contract fixture",
        "status": "approved",
        "created_by": "contract-test",
        "created_at": "2026-11-10T00:00:00Z",
        "domain": "elysia_core",
        "history": [],
    }
    (proposal_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    plan = (
        f"## Step 1: Create file {filename}\n\n"
        f"Create {filename}\n\n"
        "```\n"
        "fictional-bytes\n"
        "```\n"
    )
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


def _layout(tmp_path):
    repo = tmp_path / "repo"
    elsewhere = tmp_path / "elsewhere"
    explicit = tmp_path / "explicit-root"
    repo.mkdir()
    elsewhere.mkdir()
    explicit.mkdir()
    return repo, elsewhere, explicit


def _proposals(repo):
    return ProposalSystem(
        repo / "proposals",
        event_bus=EventBus(),
        enable_watcher=False,
    )


def _seed(proposals):
    root = proposals.proposals_root
    _write_proposal(root, "fictional-beside", "fictional-beside.txt")
    _write_proposal(root, "fictional-explicit", "fictional-explicit.txt")
    _write_proposal(root, "fictional-dry", "fictional-dry.txt")
    _write_proposal(root, "fictional-override", "fictional-override.txt")


def _assert_written(post, proposals, proposal_id, filename, directory, absent_dirs):
    result = post(f"/api/proposals/{proposal_id}/implement", {})
    assert result["status"] == 200
    assert result["content_type"].startswith("application/json")
    assert result["body"]["success"] is True
    written = directory / filename
    assert written.is_file()
    assert written.resolve().parent == directory.resolve()
    assert written.read_text(encoding="utf-8") == "fictional-bytes\n"
    for other in absent_dirs:
        assert (other / filename).exists() is False
    stored = _stored(proposals, proposal_id)
    assert stored["status"] == "implemented"
    assert stored["implementation_status"] == "completed"


def _exercise(bind, repo, elsewhere, explicit):
    beside = _proposals(repo)
    _seed(beside)
    beside_server = bind(beside, implementer=None)

    def post_beside(path, payload):
        return beside_server(path, payload)

    try:
        _assert_written(
            post_beside,
            beside,
            "fictional-beside",
            "fictional-beside.txt",
            repo,
            [elsewhere, explicit],
        )
    finally:
        beside_server.close()

    explicit_bus = EventBus()
    explicit_proposals = ProposalSystem(
        repo / "proposals",
        event_bus=explicit_bus,
        enable_watcher=False,
    )
    explicit_agent = ImplementerAgent(
        repo_root=explicit,
        proposal_system=explicit_proposals,
        event_bus=explicit_bus,
        dry_run=False,
    )
    explicit_server = bind(explicit_proposals, implementer=explicit_agent)
    try:
        _assert_written(
            explicit_server,
            explicit_proposals,
            "fictional-explicit",
            "fictional-explicit.txt",
            explicit,
            [elsewhere, repo],
        )
    finally:
        explicit_server.close()

    dry_bus = EventBus()
    dry_proposals = ProposalSystem(
        repo / "proposals",
        event_bus=dry_bus,
        enable_watcher=False,
    )
    dry_agent = ImplementerAgent(
        repo_root=explicit,
        proposal_system=dry_proposals,
        event_bus=dry_bus,
        dry_run=True,
    )
    dry_server = bind(dry_proposals, implementer=dry_agent)
    try:
        dry = dry_server("/api/proposals/fictional-dry/implement", {})
        assert dry["status"] == 200
        assert dry["body"]["success"] is True
        assert dry["body"]["step_results"][0]["dry_run"] is True
        for directory in (elsewhere, repo, explicit):
            assert (directory / "fictional-dry.txt").exists() is False

        override = dry_server(
            "/api/proposals/fictional-override/implement",
            {"dry_run": False},
        )
        assert override["status"] == 200
        assert override["body"]["success"] is True
        written = explicit / "fictional-override.txt"
        assert written.is_file()
        assert written.read_text(encoding="utf-8") == "fictional-bytes\n"
        assert (elsewhere / "fictional-override.txt").exists() is False
        assert (repo / "fictional-override.txt").exists() is False
        stored = _stored(dry_proposals, "fictional-override")
        assert stored["status"] == "implemented"
    finally:
        dry_server.close()


class TestRuntimeApiImplementRepoRoot:
    def test_repo_root_through_flask_app(self, tmp_path, monkeypatch):
        repo, elsewhere, explicit = _layout(tmp_path)
        monkeypatch.chdir(elsewhere)

        def bind(proposals, implementer):
            server = RuntimeAPIServer(
                status_provider=lambda: {"running": True},
                event_bus=proposals.event_bus,
                proposal_system=proposals,
                implementer=implementer,
            )
            client = server._app.test_client()

            def post(path, payload):
                response = client.post(path, json=payload)
                return {
                    "status": response.status_code,
                    "body": response.get_json(),
                    "content_type": response.headers.get("Content-Type", ""),
                }

            post.close = lambda: None
            return post

        _exercise(bind, repo, elsewhere, explicit)

    def test_repo_root_through_live_http(self, tmp_path, monkeypatch):
        repo, elsewhere, explicit = _layout(tmp_path)
        monkeypatch.chdir(elsewhere)

        def bind(proposals, implementer):
            server = RuntimeAPIServer(
                status_provider=lambda: {"running": True},
                event_bus=proposals.event_bus,
                host="127.0.0.1",
                port=_free_port(),
                proposal_system=proposals,
                implementer=implementer,
            )
            server.start()
            _wait_until_listening(server)

            def post(path, payload):
                request = urllib.request.Request(
                    f"http://{server.host}:{server.port}{path}",
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    return {
                        "status": response.status,
                        "body": json.loads(response.read().decode("utf-8")),
                        "content_type": response.headers.get("Content-Type", ""),
                    }

            def close():
                server.stop()

            post.close = close
            return post

        _exercise(bind, repo, elsewhere, explicit)
