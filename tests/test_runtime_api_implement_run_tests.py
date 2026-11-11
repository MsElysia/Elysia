"""A live implement call must not mark a proposal implemented by running every test.

Uses the real RuntimeAPIServer, ProposalSystem, and ImplementerAgent. Fictional
proposals and test files live in a temporary directory. The route still builds
the implementer with repo_root=Path("."), so the live case changes to that
directory before the server starts. Named passing and failing files are executed
with pytest. Unnamed steps and paths that resolve outside the directory are not.
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
        "created_at": "2026-11-11T00:00:00Z",
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
    tests = cwd / "tests"
    tests.mkdir()
    (tests / "test_fictional_unrelated.py").write_text(
        "def test_unrelated():\n"
        "    from pathlib import Path\n"
        "    Path('unrelated-ran.txt').write_text('ran', encoding='utf-8')\n",
        encoding="utf-8",
    )
    (tests / "test_fictional_pass.py").write_text(
        "def test_pass():\n"
        "    from pathlib import Path\n"
        "    Path('pass-ran.txt').write_text('ran', encoding='utf-8')\n",
        encoding="utf-8",
    )
    (tests / "test_fictional_fail.py").write_text(
        "def test_fail():\n"
        "    assert False, 'fictional-failure'\n",
        encoding="utf-8",
    )
    escape_marker = outside / "escape-ran.txt"
    (outside / "test_fictional_escape.py").write_text(
        "def test_escape():\n"
        "    from pathlib import Path\n"
        f"    Path({str(escape_marker)!r}).write_text('ran', encoding='utf-8')\n",
        encoding="utf-8",
    )
    (tests / "test_fictional_escape.py").symlink_to(outside / "test_fictional_escape.py")

    _write_proposal(
        root,
        "fictional-unnamed-tests",
        "## Step 1: Run tests\n\nCheck that the suite is healthy.\n",
    )
    _write_proposal(
        root,
        "fictional-pytest-prose",
        "## Step 1: Record the operator note\n\nThe operator can run pytest later.\n",
    )
    _write_proposal(
        root,
        "fictional-missing-test",
        "## Step 1: Run tests\n\nRun pytest on tests/test_fictional_missing.py\n",
    )
    _write_proposal(
        root,
        "fictional-escape-test",
        "## Step 1: Run tests\n\nRun pytest on tests/test_fictional_escape.py\n",
    )
    _write_proposal(
        root,
        "fictional-fail-test",
        "## Step 1: Run tests\n\nRun pytest on tests/test_fictional_fail.py\n",
    )
    _write_proposal(
        root,
        "fictional-pass-test",
        "## Step 1: Run tests\n\nRun pytest on tests/test_fictional_pass.py\n",
    )


def _stored(proposals, proposal_id):
    return json.loads(
        (proposals.proposals_root / proposal_id / "metadata.json").read_text(encoding="utf-8")
    )


def _assert_not_run(cwd, outside):
    assert (cwd / "unrelated-ran.txt").exists() is False
    assert (cwd / "pass-ran.txt").exists() is False
    assert (outside / "escape-ran.txt").exists() is False


def _assert_failed(post, proposals, proposal_id, error, cwd, outside):
    result = post(f"/api/proposals/{proposal_id}/implement", {"dry_run": False})
    assert result["status"] == 200
    assert result["content_type"].startswith("application/json")
    assert result["body"]["success"] is False
    assert result["body"]["error"] == f"Step 1 failed: {error}"
    assert result["body"]["steps_completed"] == 0
    assert result["body"]["step_results"][0]["executed"] is False
    assert result["body"]["step_results"][0]["step_type"] == "run_tests"
    _assert_not_run(cwd, outside)
    stored = _stored(proposals, proposal_id)
    assert stored["status"] == "implementation_failed"
    assert stored["implementation_status"] == "failed"
    summaries = " ".join(entry.get("change_summary", "") for entry in stored["history"])
    assert "Implementation completed" not in summaries
    assert error in summaries


def _assert_contract(post, proposals, cwd, outside):
    _assert_failed(
        post,
        proposals,
        "fictional-unnamed-tests",
        "No test file named in the step",
        cwd,
        outside,
    )
    _assert_failed(
        post,
        proposals,
        "fictional-pytest-prose",
        "No test file named in the step",
        cwd,
        outside,
    )
    _assert_failed(
        post,
        proposals,
        "fictional-missing-test",
        "Test file does not exist",
        cwd,
        outside,
    )
    _assert_failed(
        post,
        proposals,
        "fictional-escape-test",
        "Test path is outside the repository",
        cwd,
        outside,
    )

    failed = post("/api/proposals/fictional-fail-test/implement", {"dry_run": False})
    assert failed["status"] == 200
    assert failed["body"]["success"] is False
    assert failed["body"]["error"] == "Step 1 failed: Tests failed with exit code 1"
    assert failed["body"]["step_results"][0]["executed"] is True
    assert failed["body"]["step_results"][0]["exit_code"] == 1
    assert failed["body"]["step_results"][0]["test_path"] == "tests/test_fictional_fail.py"
    assert "test_fictional_unrelated" not in failed["body"]["step_results"][0]["stdout"]
    _assert_not_run(cwd, outside)
    failed_stored = _stored(proposals, "fictional-fail-test")
    assert failed_stored["status"] == "implementation_failed"
    assert failed_stored["implementation_status"] == "failed"

    passed = post("/api/proposals/fictional-pass-test/implement", {"dry_run": False})
    assert passed["status"] == 200
    assert passed["body"]["success"] is True
    assert passed["body"]["step_results"][0]["executed"] is True
    assert passed["body"]["step_results"][0]["exit_code"] == 0
    assert passed["body"]["step_results"][0]["test_path"] == "tests/test_fictional_pass.py"
    assert "1 passed" in passed["body"]["step_results"][0]["stdout"]
    assert "test_fictional_unrelated" not in passed["body"]["step_results"][0]["stdout"]
    assert (cwd / "pass-ran.txt").read_text(encoding="utf-8") == "ran"
    assert (cwd / "unrelated-ran.txt").exists() is False
    assert (outside / "escape-ran.txt").exists() is False
    passed_stored = _stored(proposals, "fictional-pass-test")
    assert passed_stored["status"] == "implemented"
    assert passed_stored["implementation_status"] == "completed"


class TestRuntimeApiImplementRunTests:
    def test_run_tests_contract_through_flask_app(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        outside = tmp_path / "outside"
        cwd.mkdir()
        outside.mkdir()
        monkeypatch.chdir(cwd)
        proposals = ProposalSystem(
            tmp_path / "proposals",
            event_bus=EventBus(),
            enable_watcher=False,
        )
        _seed(proposals.proposals_root, cwd, outside)
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

        _assert_contract(post, proposals, cwd, outside)

    def test_run_tests_contract_through_live_http(self, tmp_path, monkeypatch):
        cwd = tmp_path / "cwd"
        outside = tmp_path / "outside"
        cwd.mkdir()
        outside.mkdir()
        monkeypatch.chdir(cwd)
        proposals = ProposalSystem(
            tmp_path / "proposals",
            event_bus=EventBus(),
            enable_watcher=False,
        )
        _seed(proposals.proposals_root, cwd, outside)
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

            _assert_contract(post, proposals, cwd, outside)
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
        with urllib.request.urlopen(request, timeout=30) as response:
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
