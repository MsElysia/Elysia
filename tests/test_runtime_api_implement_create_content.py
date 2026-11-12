"""A live implement call must write fenced file content and must not invent a file.

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
        "created_at": "2026-11-12T00:00:00Z",
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
        "fictional-no-content",
        "## Step 1: Create file\n\n"
        "Write the fictional sentence into fictional-no-content.txt.\n",
    )
    _write_proposal(
        root,
        "fictional-empty-fence",
        "## Step 1: Create file fictional-empty-fence.txt\n\n"
        "Create fictional-empty-fence.txt\n\n```\n\n```\n",
    )
    _write_proposal(
        root,
        "fictional-nested-prose",
        "## Step 1: Create file\n\n"
        "Create fictional-dir/fictional-nested.txt with the notes below.\n",
    )
    _write_proposal(
        root,
        "fictional-add-prose",
        "## Step 1: Add tests for the sentinel\n\n"
        "Add fictional-add-prose.txt without a fence.\n",
    )
    _write_proposal(
        root,
        "fictional-text-title",
        "## Step 1: Create file fictional-text-title.txt\n\n"
        "```text\nfictional-text-bytes\n```\n",
    )
    _write_proposal(
        root,
        "fictional-python-body",
        "## Step 1: Create file\n\n"
        "Create fictional-python-body.py\n\n```python\nprint('fictional')\n```\n",
    )


def _stored(proposals, proposal_id):
    return json.loads(
        (proposals.proposals_root / proposal_id / "metadata.json").read_text(encoding="utf-8")
    )


def _assert_failed(post, proposals, cwd, proposal_id, absent_path):
    result = post(f"/api/proposals/{proposal_id}/implement", {"dry_run": False})
    assert result["status"] == 200
    assert result["content_type"].startswith("application/json")
    assert result["body"]["success"] is False
    assert result["body"]["error"] == "Step 1 failed: File content was not provided"
    assert result["body"]["steps_completed"] == 0
    assert result["body"]["step_results"][0]["created"] is False
    assert result["body"]["step_results"][0]["step_type"] == "create_file"
    assert not (cwd / absent_path).exists()
    stored = _stored(proposals, proposal_id)
    assert stored["status"] == "implementation_failed"
    assert stored["implementation_status"] == "failed"
    summaries = " ".join(entry.get("change_summary", "") for entry in stored["history"])
    assert "Implementation completed" not in summaries
    assert "File content was not provided" in summaries


def _assert_contract(post, proposals, cwd):
    _assert_failed(post, proposals, cwd, "fictional-no-content", "fictional-no-content.txt")
    _assert_failed(post, proposals, cwd, "fictional-empty-fence", "fictional-empty-fence.txt")
    _assert_failed(
        post, proposals, cwd, "fictional-nested-prose", "fictional-dir/fictional-nested.txt"
    )
    assert not (cwd / "fictional-dir").exists()
    _assert_failed(post, proposals, cwd, "fictional-add-prose", "fictional-add-prose.txt")

    titled = post("/api/proposals/fictional-text-title/implement", {"dry_run": False})
    assert titled["status"] == 200
    assert titled["body"]["success"] is True
    text_file = cwd / "fictional-text-title.txt"
    assert text_file.is_file()
    assert text_file.resolve().parent == cwd.resolve()
    assert text_file.read_text(encoding="utf-8") == "fictional-text-bytes\n"
    titled_stored = _stored(proposals, "fictional-text-title")
    assert titled_stored["status"] == "implemented"
    assert titled_stored["implementation_status"] == "completed"

    python = post("/api/proposals/fictional-python-body/implement", {"dry_run": False})
    assert python["status"] == 200
    assert python["body"]["success"] is True
    python_file = cwd / "fictional-python-body.py"
    assert python_file.is_file()
    assert python_file.resolve().parent == cwd.resolve()
    assert python_file.read_text(encoding="utf-8") == "print('fictional')\n"
    python_stored = _stored(proposals, "fictional-python-body")
    assert python_stored["status"] == "implemented"
    assert python_stored["implementation_status"] == "completed"
    assert "Generated by Elysia-Implementer" not in python_file.read_text(encoding="utf-8")
    assert "Generated by Elysia-Implementer" not in text_file.read_text(encoding="utf-8")


class TestRuntimeApiImplementCreateContent:
    def test_missing_content_fails_through_flask_app(self, tmp_path, monkeypatch):
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

    def test_missing_content_fails_through_live_http(self, tmp_path, monkeypatch):
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
