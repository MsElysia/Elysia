"""Contract tests for GET /api/proposals/<id>/implementation.

Uses the real RuntimeAPIServer, ProposalSystem, and ImplementerAgent.
Fictional proposals live in a temporary directory. The live case binds the
Werkzeug server and calls it over HTTP. No external service is called, and
the plans used here do not write into the repository.
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
from elysia.shell import interactive_shell


def _write_proposal(root, proposal_id, status, plan=None, extra=None):
    proposal_path = root / proposal_id
    proposal_path.mkdir(parents=True)
    metadata = {
        "proposal_id": proposal_id,
        "title": "Fictional proposal",
        "description": "Temporary contract fixture",
        "status": status,
        "created_by": "fictional-operator",
        "created_at": "2026-11-01T00:00:00Z",
        "domain": "elysia_core",
        "history": [],
    }
    if extra:
        metadata.update(extra)
    (proposal_path / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    if plan is not None:
        design = proposal_path / "design"
        design.mkdir()
        (design / "implementation_plan.md").write_text(plan, encoding="utf-8")
    return proposal_path


def _seed(root):
    _write_proposal(root, "fictional-unset", "approved")
    _write_proposal(
        root,
        "fictional-bad-history",
        "approved",
        extra={
            "implementation_status": "completed",
            "history": "not-a-list",
        },
    )
    _write_proposal(
        root,
        "fictional-mixed-history",
        "approved",
        extra={
            "implementation_status": "completed",
            "history": [
                "not-an-entry",
                {
                    "timestamp": "2026-11-01T00:00:01Z",
                    "actor": "Elysia-Implementer",
                    "change_summary": "Fictional earlier note",
                },
            ],
        },
    )
    unreadable = root / "fictional-unreadable"
    unreadable.mkdir()
    (unreadable / "metadata.json").write_text("[]", encoding="utf-8")
    _write_proposal(
        root,
        "fictional-dry-run",
        "approved",
        plan="## Step 1: Record the fictional review note\n\nLeave the repository unchanged.\n",
    )
    _write_proposal(
        root,
        "fictional-bad-step",
        "approved",
        plan=(
            "## Step 1: Create file placeholder\n\n"
            "No filesystem path is given for this fictional step.\n"
        ),
    )


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


def _read_proposal(root, proposal_id):
    return json.loads((root / proposal_id / "metadata.json").read_text(encoding="utf-8"))


def _assert_contract(get, post, root):
    missing = get("/api/proposals/fictional-missing/implementation")
    assert missing["status"] == 404
    assert missing["content_type"].startswith("application/json")
    assert missing["body"] == {"error": "Proposal not found"}

    unset = get("/api/proposals/fictional-unset/implementation")
    assert unset["status"] == 200
    assert unset["content_type"].startswith("application/json")
    assert unset["body"]["implementation_status"] is None
    assert unset["body"]["implementation_status_recorded"] is False
    assert unset["body"]["last_implementation_result"] is None
    assert unset["body"]["result_recorded"] is False
    assert unset["body"]["history_readable"] is True
    assert unset["body"]["recent_history"] == []
    assert "implementation_status" not in _read_proposal(root, "fictional-unset")

    bad_history = get("/api/proposals/fictional-bad-history/implementation")
    assert bad_history["status"] == 200
    assert bad_history["content_type"].startswith("application/json")
    assert bad_history["body"]["implementation_status"] == "completed"
    assert bad_history["body"]["implementation_status_recorded"] is True
    assert bad_history["body"]["result_recorded"] is False
    assert bad_history["body"]["history_readable"] is False
    assert bad_history["body"]["recent_history"] == []

    mixed = get("/api/proposals/fictional-mixed-history/implementation")
    assert mixed["status"] == 200
    assert mixed["content_type"].startswith("application/json")
    assert mixed["body"]["history_readable"] is False
    assert mixed["body"]["recent_history"] == [
        {
            "timestamp": "2026-11-01T00:00:01Z",
            "actor": "Elysia-Implementer",
            "change_summary": "Fictional earlier note",
        }
    ]

    unreadable = get("/api/proposals/fictional-unreadable/implementation")
    assert unreadable["status"] == 500
    assert unreadable["content_type"].startswith("application/json")
    assert unreadable["body"] == {"error": "Proposal metadata is unreadable"}

    dry = post("/api/proposals/fictional-dry-run/implement", {"dry_run": True})
    assert dry["content_type"].startswith("application/json")
    assert dry["body"]["success"] is True
    assert dry["body"]["steps_completed"] == 1

    stored_dry = _read_proposal(root, "fictional-dry-run")
    assert stored_dry["implementation_status"] == "completed"
    assert stored_dry["status"] == "implemented"
    assert stored_dry["last_implementation_result"] == "Implementation completed: 1/1 steps"
    viewed = get("/api/proposals/fictional-dry-run/implementation")
    assert viewed["status"] == 200
    assert viewed["content_type"].startswith("application/json")
    assert viewed["body"]["implementation_status"] == "completed"
    assert viewed["body"]["implementation_status_recorded"] is True
    assert viewed["body"]["result_recorded"] is True
    assert (
        viewed["body"]["last_implementation_result"]
        == stored_dry["last_implementation_result"]
    )
    assert viewed["body"]["history_readable"] is True
    assert any(
        entry.get("actor") == "Elysia-Implementer" for entry in viewed["body"]["recent_history"]
    )
    assert (root / "fictional-dry-run" / "design" / "implementation_plan.md").is_file()

    failed = post("/api/proposals/fictional-bad-step/implement", {"dry_run": False})
    assert failed["content_type"].startswith("application/json")
    assert failed["body"]["success"] is False
    assert "Could not extract file path" in failed["body"]["error"]

    stored_failed = _read_proposal(root, "fictional-bad-step")
    assert stored_failed["implementation_status"] == "failed"
    assert stored_failed["status"] == "implementation_failed"
    assert "Could not extract file path" in stored_failed["last_implementation_result"]
    failed_view = get("/api/proposals/fictional-bad-step/implementation")
    assert failed_view["status"] == 200
    assert failed_view["body"]["implementation_status"] == "failed"
    assert failed_view["body"]["result_recorded"] is True
    assert (
        failed_view["body"]["last_implementation_result"]
        == stored_failed["last_implementation_result"]
    )
    names = sorted(path.name for path in (root / "fictional-bad-step").iterdir())
    assert names == ["design", "metadata.json"]


class TestRuntimeApiImplementation:
    def test_status_contract_through_flask_app(self, tmp_path):
        root = tmp_path / "proposals"
        proposals = ProposalSystem(root, event_bus=EventBus(), enable_watcher=False)
        _seed(root)
        server = RuntimeAPIServer(
            status_provider=lambda: {"running": True},
            event_bus=proposals.event_bus,
            proposal_system=proposals,
        )
        client = server._app.test_client()

        def get(path):
            response = client.get(path)
            return {
                "status": response.status_code,
                "body": response.get_json(),
                "content_type": response.headers.get("Content-Type", ""),
            }

        def post(path, payload):
            response = client.post(path, json=payload)
            return {
                "status": response.status_code,
                "body": response.get_json(),
                "content_type": response.headers.get("Content-Type", ""),
            }

        try:
            _assert_contract(get, post, root)
        finally:
            proposals.shutdown()

    def test_status_contract_through_live_http(self, tmp_path):
        root = tmp_path / "proposals"
        proposals = ProposalSystem(root, event_bus=EventBus(), enable_watcher=False)
        _seed(root)
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

            def request(method, path, payload=None):
                data = None if payload is None else json.dumps(payload).encode("utf-8")
                headers = {"Content-Type": "application/json"} if data else {}
                outgoing = urllib.request.Request(
                    f"http://{server.host}:{server.port}{path}",
                    data=data,
                    headers=headers,
                    method=method,
                )
                try:
                    with urllib.request.urlopen(outgoing, timeout=5) as response:
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

            _assert_contract(
                lambda path: request("GET", path),
                lambda path, payload: request("POST", path, payload),
                root,
            )
        finally:
            server.stop()
            proposals.shutdown()

    def test_missing_proposal_system_is_unavailable(self):
        server = RuntimeAPIServer(
            status_provider=lambda: {"running": True},
            event_bus=EventBus(),
        )
        response = server._app.test_client().get(
            "/api/proposals/fictional-unset/implementation"
        )
        assert response.status_code == 503
        assert response.get_json() == {"error": "Proposal system not available"}
        assert response.headers.get("Content-Type", "").startswith("application/json")

    def test_shell_prints_stored_result_and_api_error(self, tmp_path, monkeypatch, capsys):
        root = tmp_path / "proposals"
        proposals = ProposalSystem(root, event_bus=EventBus(), enable_watcher=False)
        _seed(root)
        server = RuntimeAPIServer(
            status_provider=lambda: {"running": True},
            event_bus=proposals.event_bus,
            host="127.0.0.1",
            port=_free_port(),
            proposal_system=proposals,
        )
        server.start()
        _wait_until_listening(server)
        payload = json.dumps({"dry_run": True}).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.port}/api/proposals/fictional-dry-run/implement",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            started = json.loads(response.read().decode("utf-8"))
        assert started["success"] is True

        commands = iter(
            [
                "implementation",
                "implementation fictional-missing",
                "implementation fictional-bad-history",
                "implementation fictional-dry-run",
                "exit",
            ]
        )
        monkeypatch.setattr("builtins.input", lambda _prompt="": next(commands))
        try:
            interactive_shell("127.0.0.1", server.port)
        finally:
            server.stop()
            proposals.shutdown()

        captured = capsys.readouterr()
        stored = _read_proposal(root, "fictional-dry-run")
        assert "proposal id is required" in captured.err
        assert "HTTP 404: Proposal not found" in captured.err
        assert "Implementation history was not readable" in captured.err
        assert "Implementation result was not stored" in captured.err
        assert stored["last_implementation_result"] in captured.out
        assert '"result_recorded": true' in captured.out
