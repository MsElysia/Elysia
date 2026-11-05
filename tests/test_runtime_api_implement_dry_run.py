"""Contract tests for dry_run on POST /api/proposals/<id>/implement.

Uses the real RuntimeAPIServer, ProposalSystem, and ImplementerAgent.
Fictional proposals live in a temporary directory. The live case binds the
Werkzeug server and posts over HTTP. File creation is confined to a temporary
working directory because this route still builds the implementer with
repo_root=Path("."). No external service is called.
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


def _write_proposal(root, proposal_id, status, filename):
    proposal_path = root / proposal_id
    (proposal_path / "design").mkdir(parents=True)
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional proposal",
        "description": "Temporary contract fixture",
        "status": status,
        "created_by": "contract-test",
        "created_at": "2026-11-05T00:00:00Z",
        "domain": "elysia_core",
        "history": [],
    }
    (proposal_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    plan = (
        f"## Step 1: Create file {filename}\n\n"
        f"Create {filename} for this fictional proposal.\n"
    )
    (proposal_path / "design" / "implementation_plan.md").write_text(plan, encoding="utf-8")
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


def _seed(root):
    _write_proposal(root, "fictional-rejected", "approved", "fictional-rejected-sentinel.txt")
    _write_proposal(root, "fictional-bool-true", "approved", "fictional-bool-true-sentinel.txt")
    _write_proposal(root, "fictional-bool-false", "approved", "fictional-bool-false-sentinel.txt")
    _write_proposal(root, "fictional-omitted", "approved", "fictional-omitted-sentinel.txt")


def _assert_contract(post, proposals, cwd):
    rejected_meta = proposals.proposals_root / "fictional-rejected" / "metadata.json"
    original = rejected_meta.read_text(encoding="utf-8")
    invalid_values = ["false", "true", 0, 1, None, "no", 1.5, {"nested": True}]
    for value in invalid_values:
        result = post(
            "/api/proposals/fictional-rejected/implement",
            {"dry_run": value},
        )
        assert result["status"] == 400, value
        assert result["content_type"].startswith("application/json")
        assert result["body"] == {"error": "dry_run must be a boolean"}
        assert rejected_meta.read_text(encoding="utf-8") == original
        assert not (cwd / "fictional-rejected-sentinel.txt").exists()

    missing = post(
        "/api/proposals/fictional-missing/implement",
        {"dry_run": "false"},
    )
    assert missing["status"] == 400
    assert missing["body"] == {"error": "dry_run must be a boolean"}
    assert not (proposals.proposals_root / "fictional-missing").exists()

    dry = post(
        "/api/proposals/fictional-bool-true/implement",
        {"dry_run": True},
    )
    assert dry["status"] == 200
    assert dry["content_type"].startswith("application/json")
    assert dry["body"]["success"] is True
    assert dry["body"]["steps_completed"] == 1
    assert dry["body"]["step_results"][0]["dry_run"] is True
    assert not (cwd / "fictional-bool-true-sentinel.txt").exists()

    live = post(
        "/api/proposals/fictional-bool-false/implement",
        {"dry_run": False},
    )
    assert live["status"] == 200
    assert live["body"]["success"] is True
    assert live["body"]["step_results"][0]["step_type"] == "create_file"
    assert "dry_run" not in live["body"]["step_results"][0]
    created = cwd / "fictional-bool-false-sentinel.txt"
    assert created.is_file()
    assert created.resolve().parent == cwd.resolve()
    assert "fictional-bool-false" in created.read_text(encoding="utf-8")

    omitted = post("/api/proposals/fictional-omitted/implement", {})
    assert omitted["status"] == 200
    assert omitted["body"]["success"] is True
    omitted_file = cwd / "fictional-omitted-sentinel.txt"
    assert omitted_file.is_file()
    assert "fictional-omitted" in omitted_file.read_text(encoding="utf-8")


class TestRuntimeApiImplementDryRun:
    def test_dry_run_flag_through_flask_app(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        proposals = ProposalSystem(
            tmp_path / "proposals",
            event_bus=EventBus(),
            enable_watcher=False,
        )
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

        _assert_contract(post, proposals, cwd)

    def test_dry_run_flag_through_live_http(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        monkeypatch.chdir(cwd)
        proposals = ProposalSystem(
            tmp_path / "proposals",
            event_bus=EventBus(),
            enable_watcher=False,
        )
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

            _assert_contract(post, proposals, cwd)
        finally:
            server.stop()
