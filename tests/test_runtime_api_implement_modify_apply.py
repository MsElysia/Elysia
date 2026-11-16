"""A live modify or add-config step writes its fenced replacement, or it fails.

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
        "created_at": "2026-11-16T00:00:00Z",
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
    notes = cwd / "docs"
    notes.mkdir()
    (notes / "notes.md").write_text("notes-original", encoding="utf-8")
    (cwd / "fictional_widget.txt").write_text("original-bytes", encoding="utf-8")
    (cwd / "fictional_prose.txt").write_text("prose-original", encoding="utf-8")
    (cwd / "fictional_same.txt").write_text("original-bytes\n", encoding="utf-8")
    (cwd / "fictional_none.txt").write_text("none-original", encoding="utf-8")
    (cwd / "fictional_config.txt").write_text("config-original", encoding="utf-8")
    (cwd / "fictional_left.txt").write_text("left-original", encoding="utf-8")
    (cwd / "fictional_right.txt").write_text("right-original", encoding="utf-8")
    escape = outside / "fictional-escape.txt"
    escape.write_text("outside-original", encoding="utf-8")
    (cwd / "fictional_link.txt").symlink_to(escape)

    _write_proposal(
        root,
        "fictional-modify-title",
        "## Step 1: Modify fictional_widget.txt\n\n"
        "Mention docs/notes.md first.\n\n"
        "```text\n"
        "fictional-replacement\n"
        "```\n",
    )
    _write_proposal(
        root,
        "fictional-modify-prose",
        "## Step 1: Modify the sentinel\n\n"
        "See docs/notes.md then replace fictional_prose.txt.\n\n"
        "```text\n"
        "fictional-prose\n"
        "```\n",
    )
    _write_proposal(
        root,
        "fictional-modify-same",
        "## Step 1: Modify fictional_same.txt\n\n"
        "Replace fictional_same.txt.\n\n"
        "```text\n"
        "original-bytes\n"
        "```\n",
    )
    _write_proposal(
        root,
        "fictional-modify-none",
        "## Step 1: Modify fictional_none.txt\n\n"
        "Update fictional_none.txt in place. No fence.\n",
    )
    _write_proposal(
        root,
        "fictional-config-apply",
        "## Step 1: Add config fictional_config.txt\n\n"
        "Mention docs/notes.md first.\n\n"
        "```text\n"
        "config-replacement\n"
        "```\n",
    )
    _write_proposal(
        root,
        "fictional-modify-outside",
        "## Step 1: Modify the escape\n\n"
        f"Update {escape.as_posix()} in place.\n\n"
        "```text\n"
        "should-not-write\n"
        "```\n",
    )
    _write_proposal(
        root,
        "fictional-modify-link",
        "## Step 1: Modify the linked sentinel\n\n"
        "Update fictional_link.txt.\n\n"
        "```text\n"
        "should-not-write\n"
        "```\n",
    )
    _write_proposal(
        root,
        "fictional-modify-ambiguous",
        "## Step 1: Modify fictional_left.txt and fictional_right.txt\n\n"
        "Update fictional_left.txt and fictional_right.txt.\n\n"
        "```text\n"
        "should-not-write\n"
        "```\n",
    )
    return escape


def _stored(proposals, proposal_id):
    return json.loads(
        (proposals.proposals_root / proposal_id / "metadata.json").read_text(encoding="utf-8")
    )


def _assert_contract(post, proposals, cwd, outside_file):
    title = post("/api/proposals/fictional-modify-title/implement", {"dry_run": False})
    assert title["status"] == 200
    assert title["content_type"].startswith("application/json")
    assert title["body"]["success"] is True
    assert title["body"]["step_results"][0]["applied"] is True
    assert title["body"]["step_results"][0]["step_type"] == "modify_file"
    assert (cwd / "fictional_widget.txt").read_text(encoding="utf-8") == "fictional-replacement\n"
    assert (cwd / "docs" / "notes.md").read_text(encoding="utf-8") == "notes-original"
    title_stored = _stored(proposals, "fictional-modify-title")
    assert title_stored["status"] == "implemented"
    assert title_stored["implementation_status"] == "completed"

    prose = post("/api/proposals/fictional-modify-prose/implement", {"dry_run": False})
    assert prose["status"] == 200
    assert prose["body"]["success"] is True
    assert (cwd / "fictional_prose.txt").read_text(encoding="utf-8") == "fictional-prose\n"
    assert (cwd / "docs" / "notes.md").read_text(encoding="utf-8") == "notes-original"
    assert _stored(proposals, "fictional-modify-prose")["status"] == "implemented"

    same = post("/api/proposals/fictional-modify-same/implement", {"dry_run": False})
    assert same["status"] == 200
    assert same["body"]["success"] is False
    assert same["body"]["error"] == "Step 1 failed: File modification was not applied"
    assert same["body"]["step_results"][0]["applied"] is False
    assert (cwd / "fictional_same.txt").read_text(encoding="utf-8") == "original-bytes\n"
    same_stored = _stored(proposals, "fictional-modify-same")
    assert same_stored["status"] == "implementation_failed"
    assert same_stored["implementation_status"] == "failed"

    missing = post("/api/proposals/fictional-modify-none/implement", {"dry_run": False})
    assert missing["status"] == 200
    assert missing["body"]["success"] is False
    assert missing["body"]["error"] == "Step 1 failed: File content was not provided"
    assert (cwd / "fictional_none.txt").read_text(encoding="utf-8") == "none-original"
    assert _stored(proposals, "fictional-modify-none")["status"] == "implementation_failed"

    config = post("/api/proposals/fictional-config-apply/implement", {"dry_run": False})
    assert config["status"] == 200
    assert config["body"]["success"] is True
    assert config["body"]["step_results"][0]["step_type"] == "update_config"
    assert (cwd / "fictional_config.txt").read_text(encoding="utf-8") == "config-replacement\n"
    assert (cwd / "docs" / "notes.md").read_text(encoding="utf-8") == "notes-original"
    assert _stored(proposals, "fictional-config-apply")["status"] == "implemented"

    outside = post("/api/proposals/fictional-modify-outside/implement", {"dry_run": False})
    assert outside["status"] == 200
    assert outside["body"]["success"] is False
    assert outside["body"]["error"] == "Step 1 failed: File path is outside the repository"
    assert outside_file.read_text(encoding="utf-8") == "outside-original"
    assert _stored(proposals, "fictional-modify-outside")["status"] == "implementation_failed"

    link = post("/api/proposals/fictional-modify-link/implement", {"dry_run": False})
    assert link["status"] == 200
    assert link["body"]["success"] is False
    assert link["body"]["error"] == "Step 1 failed: File path is outside the repository"
    assert outside_file.read_text(encoding="utf-8") == "outside-original"
    assert _stored(proposals, "fictional-modify-link")["status"] == "implementation_failed"

    ambiguous = post("/api/proposals/fictional-modify-ambiguous/implement", {"dry_run": False})
    assert ambiguous["status"] == 200
    assert ambiguous["body"]["success"] is False
    assert ambiguous["body"]["error"] == "Step 1 failed: File path is ambiguous"
    assert (cwd / "fictional_left.txt").read_text(encoding="utf-8") == "left-original"
    assert (cwd / "fictional_right.txt").read_text(encoding="utf-8") == "right-original"
    assert _stored(proposals, "fictional-modify-ambiguous")["status"] == "implementation_failed"


class TestRuntimeApiImplementModifyApply:
    def test_modify_apply_through_flask_app(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        monkeypatch.chdir(cwd)
        proposals = ProposalSystem(
            tmp_path / "proposals",
            event_bus=EventBus(),
            enable_watcher=False,
        )
        outside_file = _seed(proposals.proposals_root, cwd, outside)
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

        _assert_contract(post, proposals, cwd, outside_file)

    def test_modify_apply_through_live_http(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        monkeypatch.chdir(cwd)
        proposals = ProposalSystem(
            tmp_path / "proposals",
            event_bus=EventBus(),
            enable_watcher=False,
        )
        outside_file = _seed(proposals.proposals_root, cwd, outside)
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

            _assert_contract(post, proposals, cwd, outside_file)
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
