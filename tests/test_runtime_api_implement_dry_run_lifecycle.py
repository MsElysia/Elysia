"""A boolean dry run must not store a proposal as implemented.

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


def _write_proposal(root, proposal_id, filename):
    proposal_path = root / proposal_id
    (proposal_path / "design").mkdir(parents=True)
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional proposal",
        "description": "Temporary contract fixture",
        "status": "approved",
        "created_by": "contract-test",
        "created_at": "2026-11-06T00:00:00Z",
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
    _write_proposal(root, "fictional-dry-lifecycle", "fictional-dry-lifecycle-sentinel.txt")
    _write_proposal(root, "fictional-live-lifecycle", "fictional-live-lifecycle-sentinel.txt")


def _assert_contract(post, get, proposals, cwd):
    dry = post(
        "/api/proposals/fictional-dry-lifecycle/implement",
        {"dry_run": True},
    )
    assert dry["status"] == 200
    assert dry["content_type"].startswith("application/json")
    assert dry["body"]["success"] is True
    assert dry["body"]["dry_run"] is True
    assert dry["body"]["status_unchanged"] is True
    assert dry["body"]["lifecycle_status"] == "approved"
    assert dry["body"]["implementation_status"] is None
    assert dry["body"]["steps_completed"] == 1
    assert dry["body"]["step_results"][0]["dry_run"] is True
    assert not (cwd / "fictional-dry-lifecycle-sentinel.txt").exists()

    stored = json.loads(
        (proposals.proposals_root / "fictional-dry-lifecycle" / "metadata.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["status"] == "approved"
    assert "implementation_status" not in stored
    assert "last_implemented_at" not in stored
    summaries = [entry.get("change_summary") for entry in stored["history"]]
    assert summaries == ["Dry run completed; proposal status unchanged"]
    assert "implemented" not in " ".join(summaries)

    preview = get("/api/proposals/fictional-dry-lifecycle/implementation")
    assert preview["status"] == 200
    assert preview["body"]["implementation_status"] == "not_started"
    assert preview["body"]["last_implemented_at"] is None
    assert preview["body"]["recent_history"][0]["change_summary"] == (
        "Dry run completed; proposal status unchanged"
    )

    live = post(
        "/api/proposals/fictional-live-lifecycle/implement",
        {"dry_run": False},
    )
    assert live["status"] == 200
    assert live["body"]["success"] is True
    assert "dry_run" not in live["body"]
    created = cwd / "fictional-live-lifecycle-sentinel.txt"
    assert created.is_file()
    assert created.resolve().parent == cwd.resolve()
    assert "fictional-live-lifecycle" in created.read_text(encoding="utf-8")

    live_stored = json.loads(
        (proposals.proposals_root / "fictional-live-lifecycle" / "metadata.json").read_text(
            encoding="utf-8"
        )
    )
    assert live_stored["status"] == "implemented"
    assert live_stored["implementation_status"] == "completed"
    live_view = get("/api/proposals/fictional-live-lifecycle/implementation")
    assert live_view["status"] == 200
    assert live_view["body"]["implementation_status"] == "completed"


class TestRuntimeApiImplementDryRunLifecycle:
    def test_dry_run_leaves_lifecycle_through_flask_app(self, tmp_path, monkeypatch):
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

        def get(path):
            response = client.get(path)
            return {
                "status": response.status_code,
                "body": response.get_json(),
                "content_type": response.headers.get("Content-Type", ""),
            }

        _assert_contract(post, get, proposals, cwd)

    def test_dry_run_leaves_lifecycle_through_live_http(self, tmp_path, monkeypatch):
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
                return _http("POST", server, path, payload)

            def get(path):
                return _http("GET", server, path, None)

            _assert_contract(post, get, proposals, cwd)
        finally:
            server.stop()


def _http(method, server, path, payload):
    url = f"http://{server.host}:{server.port}{path}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {} if payload is None else {"Content-Type": "application/json"}
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
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
