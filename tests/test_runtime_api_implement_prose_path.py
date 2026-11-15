"""A title-less create step must write the file beside the fence.

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
        "created_at": "2026-11-15T00:00:00Z",
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
        "fictional-prose-target",
        "## Step 1: Create file\n\n"
        "Background is in docs/notes.md.\n\n"
        "Write fictional_widget.py:\n\n"
        "```python\n"
        "# helper lives in helper_other.py\n"
        "print('fictional-widget')\n"
        "```\n",
    )
    _write_proposal(
        root,
        "fictional-only-target",
        "## Step 1: Create file\n\n"
        "Create fictional_only_target.py\n\n"
        "```python\nprint('fictional-only')\n```\n",
    )
    _write_proposal(
        root,
        "fictional-add-tests-prose",
        "## Step 1: Add tests\n\n"
        "See docs/notes.md before adding the test.\n\n"
        "Write tests/test_fictional_widget.py:\n\n"
        "```python\ndef test_fictional_widget():\n    assert True\n```\n",
    )


def _stored(proposals, proposal_id):
    return json.loads(
        (proposals.proposals_root / proposal_id / "metadata.json").read_text(encoding="utf-8")
    )


def _assert_contract(post, proposals, cwd):
    prose = post("/api/proposals/fictional-prose-target/implement", {"dry_run": False})
    assert prose["status"] == 200
    assert prose["content_type"].startswith("application/json")
    assert prose["body"]["success"] is True
    widget = cwd / "fictional_widget.py"
    assert widget.is_file()
    assert widget.resolve().parent == cwd.resolve()
    assert widget.read_text(encoding="utf-8") == (
        "# helper lives in helper_other.py\nprint('fictional-widget')\n"
    )
    assert not (cwd / "docs" / "notes.md").exists()
    assert not (cwd / "helper_other.py").exists()
    assert prose["body"]["step_results"][0]["file_path"].endswith("fictional_widget.py")
    stored = _stored(proposals, "fictional-prose-target")
    assert stored["status"] == "implemented"
    assert stored["implementation_status"] == "completed"

    only = post("/api/proposals/fictional-only-target/implement", {"dry_run": False})
    assert only["status"] == 200
    assert only["body"]["success"] is True
    only_file = cwd / "fictional_only_target.py"
    assert only_file.is_file()
    assert only_file.read_text(encoding="utf-8") == "print('fictional-only')\n"
    assert not (cwd / "docs" / "notes.md").exists()

    added = post("/api/proposals/fictional-add-tests-prose/implement", {"dry_run": False})
    assert added["status"] == 200
    assert added["body"]["success"] is True
    test_file = cwd / "tests" / "test_fictional_widget.py"
    assert test_file.is_file()
    assert test_file.read_text(encoding="utf-8") == "def test_fictional_widget():\n    assert True\n"
    assert not (cwd / "docs" / "notes.md").exists()
    assert added["body"]["step_results"][0]["file_path"].endswith("tests/test_fictional_widget.py")


class TestRuntimeApiImplementProsePath:
    def test_prose_path_uses_fence_target_through_flask_app(self, tmp_path, monkeypatch):
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

    def test_prose_path_uses_fence_target_through_live_http(self, tmp_path, monkeypatch):
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
