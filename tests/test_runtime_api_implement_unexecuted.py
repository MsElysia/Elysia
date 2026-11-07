"""A live implement call must not store a proposal as implemented when the step did not run.

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
        "created_at": "2026-11-07T00:00:00Z",
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
        "fictional-generic-step",
        "## Step 1: Review the fictional design\n\nRead the notes. Do not write a file.\n",
    )
    _write_proposal(
        root,
        "fictional-modify-step",
        "## Step 1: Modify the sentinel\n\nUpdate fictional-modify-sentinel.txt in place.\n",
    )
    _write_proposal(
        root,
        "fictional-config-step",
        "## Step 1: Add config for the sentinel\n\nUpdate fictional-config-sentinel.txt in place.\n",
    )
    _write_proposal(
        root,
        "fictional-create-step",
        "## Step 1: Create file fictional-create-sentinel.txt\n\n"
        "Create fictional-create-sentinel.txt\n\n```\ncreated\n```\n",
    )
    (cwd / "fictional-modify-sentinel.txt").write_text("original-bytes", encoding="utf-8")
    (cwd / "fictional-config-sentinel.txt").write_text("original-config", encoding="utf-8")


def _stored(proposals, proposal_id):
    return json.loads(
        (proposals.proposals_root / proposal_id / "metadata.json").read_text(encoding="utf-8")
    )


def _assert_contract(post, proposals, cwd):
    generic = post("/api/proposals/fictional-generic-step/implement", {"dry_run": False})
    assert generic["status"] == 200
    assert generic["content_type"].startswith("application/json")
    assert generic["body"]["success"] is False
    assert generic["body"]["error"] == "Step 1 failed: Step was not executed"
    assert generic["body"]["steps_completed"] == 0
    assert generic["body"]["step_results"][0]["executed"] is False
    assert generic["body"]["step_results"][0]["step_type"] == "generic"
    generic_stored = _stored(proposals, "fictional-generic-step")
    assert generic_stored["status"] == "implementation_failed"
    assert generic_stored["implementation_status"] == "failed"
    summaries = " ".join(entry.get("change_summary", "") for entry in generic_stored["history"])
    assert "Implementation completed" not in summaries
    assert "Step was not executed" in summaries
    assert not (cwd / "fictional-generic-sentinel.txt").exists()

    modify = post("/api/proposals/fictional-modify-step/implement", {"dry_run": False})
    assert modify["status"] == 200
    assert modify["body"]["success"] is False
    assert modify["body"]["error"] == "Step 1 failed: File modification was not applied"
    assert modify["body"]["step_results"][0]["executed"] is False
    assert modify["body"]["step_results"][0]["step_type"] == "modify_file"
    assert (cwd / "fictional-modify-sentinel.txt").read_text(encoding="utf-8") == "original-bytes"
    modify_stored = _stored(proposals, "fictional-modify-step")
    assert modify_stored["status"] == "implementation_failed"
    assert modify_stored["implementation_status"] == "failed"

    config = post("/api/proposals/fictional-config-step/implement", {"dry_run": False})
    assert config["status"] == 200
    assert config["body"]["success"] is False
    assert config["body"]["error"] == "Step 1 failed: File modification was not applied"
    assert config["body"]["step_results"][0]["step_type"] == "modify_file"
    assert (cwd / "fictional-config-sentinel.txt").read_text(encoding="utf-8") == "original-config"
    config_stored = _stored(proposals, "fictional-config-step")
    assert config_stored["status"] == "implementation_failed"

    created = post("/api/proposals/fictional-create-step/implement", {"dry_run": False})
    assert created["status"] == 200
    assert created["body"]["success"] is True
    sentinel = cwd / "fictional-create-sentinel.txt"
    assert sentinel.is_file()
    assert sentinel.resolve().parent == cwd.resolve()
    assert "created" in sentinel.read_text(encoding="utf-8")
    created_stored = _stored(proposals, "fictional-create-step")
    assert created_stored["status"] == "implemented"
    assert created_stored["implementation_status"] == "completed"


class TestRuntimeApiImplementUnexecuted:
    def test_unexecuted_steps_fail_through_flask_app(self, tmp_path, monkeypatch):
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

    def test_unexecuted_steps_fail_through_live_http(self, tmp_path, monkeypatch):
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
