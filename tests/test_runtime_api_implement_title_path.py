"""A titled create step must write the named file, not an earlier prose path.

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


def _write_proposal(root, proposal_id, plan):
    proposal_path = root / proposal_id
    (proposal_path / "design").mkdir(parents=True)
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional proposal",
        "description": "Temporary contract fixture",
        "status": "approved",
        "created_by": "contract-test",
        "created_at": "2026-11-14T00:00:00Z",
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


def _seed(root):
    _write_proposal(
        root,
        "fictional-title-target",
        "## Step 1: Create file fictional_widget.py\n\n"
        "Background is in docs/notes.md.\n\n"
        "```python\nprint('fictional-widget')\n```\n",
    )
    _write_proposal(
        root,
        "fictional-body-target",
        "## Step 1: Create file\n\n"
        "Create fictional_body_target.py\n\n"
        "```python\nprint('fictional-body')\n```\n",
    )
    _write_proposal(
        root,
        "fictional-add-tests-title",
        "## Step 1: Add tests tests/test_fictional_widget.py\n\n"
        "See docs/notes.md before adding the test.\n\n"
        "```python\ndef test_fictional_widget():\n    assert True\n```\n",
    )


def _stored(proposals, proposal_id):
    return json.loads(
        (proposals.proposals_root / proposal_id / "metadata.json").read_text(encoding="utf-8")
    )


def _assert_contract(post, proposals, cwd):
    titled = post("/api/proposals/fictional-title-target/implement", {"dry_run": False})
    assert titled["status"] == 200
    assert titled["content_type"].startswith("application/json")
    assert titled["body"]["success"] is True
    widget = cwd / "fictional_widget.py"
    assert widget.is_file()
    assert widget.resolve().parent == cwd.resolve()
    assert widget.read_text(encoding="utf-8") == "print('fictional-widget')\n"
    assert not (cwd / "docs" / "notes.md").exists()
    assert titled["body"]["step_results"][0]["file_path"].endswith("fictional_widget.py")
    stored = _stored(proposals, "fictional-title-target")
    assert stored["status"] == "implemented"
    assert stored["implementation_status"] == "completed"

    body = post("/api/proposals/fictional-body-target/implement", {"dry_run": False})
    assert body["status"] == 200
    assert body["body"]["success"] is True
    body_file = cwd / "fictional_body_target.py"
    assert body_file.is_file()
    assert body_file.read_text(encoding="utf-8") == "print('fictional-body')\n"
    assert not (cwd / "docs" / "notes.md").exists()

    added = post("/api/proposals/fictional-add-tests-title/implement", {"dry_run": False})
    assert added["status"] == 200
    assert added["body"]["success"] is True
    test_file = cwd / "tests" / "test_fictional_widget.py"
    assert test_file.is_file()
    assert test_file.read_text(encoding="utf-8") == "def test_fictional_widget():\n    assert True\n"
    assert not (cwd / "docs" / "notes.md").exists()
    assert added["body"]["step_results"][0]["file_path"].endswith("tests/test_fictional_widget.py")


class TestRuntimeApiImplementTitlePath:
    def test_title_path_wins_through_flask_app(self, tmp_path, monkeypatch):
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

    def test_title_path_wins_through_live_http(self, tmp_path, monkeypatch):
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
    with urllib.request.urlopen(request, timeout=10) as response:
        return {
            "status": response.status,
            "body": json.loads(response.read().decode("utf-8")),
            "content_type": response.headers.get("Content-Type", ""),
        }
