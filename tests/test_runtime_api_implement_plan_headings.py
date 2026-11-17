"""Prose headings are not implementation steps.

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


def _write_proposal(root, proposal_id, filename, body):
    proposal_path = root / proposal_id
    (proposal_path / "design").mkdir(parents=True)
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional proposal",
        "description": "Temporary contract fixture",
        "status": "approved",
        "created_by": "contract-test",
        "created_at": "2026-11-17T00:00:00Z",
        "domain": "elysia_core",
        "history": [],
    }
    (proposal_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (proposal_path / "design" / filename).write_text(body, encoding="utf-8")


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
        "fictional-prose-plan",
        "implementation_plan.md",
        "## Overview\n\nDesign notes only.\n\n## Components\n\nNo numbered steps.\n",
    )
    _write_proposal(
        root,
        "fictional-arch-heading",
        "architecture.md",
        "## Create file fictional_widget.txt\n\n"
        "```\n"
        "should-not-write\n"
        "```\n",
    )
    _write_proposal(
        root,
        "fictional-numbered-step",
        "implementation_plan.md",
        "## Step 1: Create file fictional_kept.txt\n\n"
        "Create fictional_kept.txt\n\n"
        "```\n"
        "fictional-kept\n"
        "```\n",
    )
    _write_proposal(
        root,
        "fictional-dotted-step",
        "implementation_plan.md",
        "## 1. Create file fictional_numbered.txt\n\n"
        "Create fictional_numbered.txt\n\n"
        "```\n"
        "fictional-numbered\n"
        "```\n",
    )
    _write_proposal(
        root,
        "fictional-arch-step",
        "architecture.md",
        "## Step 1: Create file fictional_arch_step.txt\n\n"
        "Create fictional_arch_step.txt\n\n"
        "```\n"
        "fictional-arch-step\n"
        "```\n",
    )
    _write_proposal(
        root,
        "fictional-integration-only",
        "integration.md",
        "## Step 1: Create file fictional_integration.txt\n\n"
        "Create fictional_integration.txt\n\n"
        "```\n"
        "should-not-write\n"
        "```\n",
    )


def _stored(proposals, proposal_id):
    return json.loads(
        (proposals.proposals_root / proposal_id / "metadata.json").read_text(encoding="utf-8")
    )


def _assert_contract(post, proposals, cwd):
    prose = post("/api/proposals/fictional-prose-plan/implement", {"dry_run": False})
    assert prose["status"] == 200
    assert prose["content_type"].startswith("application/json")
    assert prose["body"]["success"] is False
    assert prose["body"]["steps_total"] == 0
    assert prose["body"]["error"] == (
        "No implementation steps found in implementation_plan.md for fictional-prose-plan"
    )
    prose_stored = _stored(proposals, "fictional-prose-plan")
    assert prose_stored["status"] == "approved"
    assert "implementation_status" not in prose_stored
    assert prose_stored["history"] == []

    heading = post("/api/proposals/fictional-arch-heading/implement", {"dry_run": False})
    assert heading["status"] == 200
    assert heading["body"]["success"] is False
    assert heading["body"]["steps_total"] == 0
    assert heading["body"]["error"] == (
        "No implementation steps found in architecture.md for fictional-arch-heading"
    )
    assert not (cwd / "fictional_widget.txt").exists()
    heading_stored = _stored(proposals, "fictional-arch-heading")
    assert heading_stored["status"] == "approved"
    assert "implementation_status" not in heading_stored

    numbered = post("/api/proposals/fictional-numbered-step/implement", {"dry_run": False})
    assert numbered["status"] == 200
    assert numbered["body"]["success"] is True
    assert numbered["body"]["steps_completed"] == 1
    assert numbered["body"]["step_results"][0]["step_type"] == "create_file"
    assert (cwd / "fictional_kept.txt").read_text(encoding="utf-8") == "fictional-kept\n"
    numbered_stored = _stored(proposals, "fictional-numbered-step")
    assert numbered_stored["status"] == "implemented"
    assert numbered_stored["implementation_status"] == "completed"

    dotted = post("/api/proposals/fictional-dotted-step/implement", {"dry_run": False})
    assert dotted["status"] == 200
    assert dotted["body"]["success"] is True
    assert (cwd / "fictional_numbered.txt").read_text(encoding="utf-8") == "fictional-numbered\n"
    assert _stored(proposals, "fictional-dotted-step")["status"] == "implemented"

    arch_step = post("/api/proposals/fictional-arch-step/implement", {"dry_run": False})
    assert arch_step["status"] == 200
    assert arch_step["body"]["success"] is True
    assert (cwd / "fictional_arch_step.txt").read_text(encoding="utf-8") == "fictional-arch-step\n"
    assert _stored(proposals, "fictional-arch-step")["status"] == "implemented"

    integration = post("/api/proposals/fictional-integration-only/implement", {"dry_run": False})
    assert integration["status"] == 200
    assert integration["body"]["success"] is False
    assert integration["body"]["error"] == (
        "Implementation plan not found for fictional-integration-only"
    )
    assert not (cwd / "fictional_integration.txt").exists()
    assert _stored(proposals, "fictional-integration-only")["status"] == "approved"


class TestRuntimeApiImplementPlanHeadings:
    def test_plan_headings_through_flask_app(self, tmp_path, monkeypatch):
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

    def test_plan_headings_through_live_http(self, tmp_path, monkeypatch):
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
