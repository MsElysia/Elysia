"""POST /tasks/create must not replace an existing task contract."""

import json
import sys
import threading
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import uvicorn
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def _load_dashboard_app():
    """Load the real FastAPI app.

    ``python -m uvicorn project_guardian.ui.app:app`` still runs
    ``project_guardian/__init__.py``, which imports GuardianCore. That import
    fails on this checkout because ``project_guardian.module_activity`` is
    absent. Task creation does not need that module.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    if "project_guardian.ui.app" in sys.modules:
        return sys.modules["project_guardian.ui.app"].app
    try:
        from project_guardian.ui.app import app
        return app
    except ImportError as exc:
        if "module_activity" not in str(exc):
            raise
    pkg = sys.modules.get("project_guardian")
    if pkg is None:
        pkg = types.ModuleType("project_guardian")
        pkg.__path__ = [str(ROOT / "project_guardian")]
        sys.modules["project_guardian"] = pkg
    elif not getattr(pkg, "__path__", None):
        pkg.__path__ = [str(ROOT / "project_guardian")]
    from project_guardian.ui.app import app
    return app


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    app = _load_dashboard_app()
    module = sys.modules["project_guardian.ui.app"]
    (tmp_path / "TASKS").mkdir()
    (tmp_path / "CONTROL.md").write_text("CURRENT_TASK: NONE\n", encoding="utf-8")
    monkeypatch.setattr(module, "project_root", tmp_path)
    return app, tmp_path


def _post(client, task_id, task_type, activate_now):
    return client.post(
        "/tasks/create",
        data={
            "task_id": task_id,
            "task_type": task_type,
            "activate_now": activate_now,
        },
    )


def test_existing_task_is_not_replaced(dashboard):
    app, root = dashboard
    original = "TASK_TYPE: RUN_ACCEPTANCE\n"
    task_file = root / "TASKS" / "TASK-FICTIONAL-KEEP.md"
    task_file.write_text(original, encoding="utf-8")
    client = TestClient(app, client=("127.0.0.1", 50000))

    conflict = _post(client, "TASK-FICTIONAL-KEEP", "CLEAR_CURRENT_TASK", "true")

    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "Task TASK-FICTIONAL-KEEP already exists"
    assert task_file.read_text(encoding="utf-8") == original
    assert root.joinpath("CONTROL.md").read_text(encoding="utf-8") == "CURRENT_TASK: NONE\n"

    created = _post(client, "TASK-FICTIONAL-NEW", "RUN_ACCEPTANCE", "true")
    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "created"
    assert body["task_id"] == "TASK-FICTIONAL-NEW"
    new_file = root / "TASKS" / "TASK-FICTIONAL-NEW.md"
    assert new_file.read_text(encoding="utf-8") == "TASK_TYPE: RUN_ACCEPTANCE\n"
    assert (
        root.joinpath("CONTROL.md").read_text(encoding="utf-8")
        == "CURRENT_TASK: TASK-FICTIONAL-NEW\n"
    )

    repeat = _post(client, "TASK-FICTIONAL-NEW", "CLEAR_CURRENT_TASK", "true")
    assert repeat.status_code == 409
    assert new_file.read_text(encoding="utf-8") == "TASK_TYPE: RUN_ACCEPTANCE\n"
    assert (
        root.joinpath("CONTROL.md").read_text(encoding="utf-8")
        == "CURRENT_TASK: TASK-FICTIONAL-NEW\n"
    )


def _multipart(task_id, task_type, activate_now):
    boundary = "----elysia-task-create"
    parts = (
        ("task_id", task_id),
        ("task_type", task_type),
        ("activate_now", activate_now),
    )
    chunks = []
    for name, value in parts:
        chunks.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        )
    chunks.append(f"--{boundary}--\r\n")
    body = "".join(chunks).encode("utf-8")
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    return body, headers


def _live_post(port, task_id, task_type, activate_now):
    body, headers = _multipart(task_id, task_type, activate_now)
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/tasks/create",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_live_http_refuses_existing_task(dashboard):
    app, root = dashboard
    original = "TASK_TYPE: RUN_ACCEPTANCE\n"
    task_file = root / "TASKS" / "TASK-FICTIONAL-LIVE.md"
    task_file.write_text(original, encoding="utf-8")
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if getattr(server, "started", False):
                break
            thread.join(0.05)
        assert server.started
        port = server.servers[0].sockets[0].getsockname()[1]

        status, body = _live_post(
            port, "TASK-FICTIONAL-LIVE", "CLEAR_CURRENT_TASK", "true"
        )
        assert status == 409
        assert body["detail"] == "Task TASK-FICTIONAL-LIVE already exists"
        assert task_file.read_text(encoding="utf-8") == original
        assert root.joinpath("CONTROL.md").read_text(encoding="utf-8") == "CURRENT_TASK: NONE\n"

        created_status, created = _live_post(
            port, "TASK-FICTIONAL-LIVE2", "RUN_ACCEPTANCE", "false"
        )
        assert created_status == 200
        assert created["status"] == "created"
        assert (
            (root / "TASKS" / "TASK-FICTIONAL-LIVE2.md").read_text(encoding="utf-8")
            == "TASK_TYPE: RUN_ACCEPTANCE\n"
        )
        assert root.joinpath("CONTROL.md").read_text(encoding="utf-8") == "CURRENT_TASK: NONE\n"
    finally:
        server.should_exit = True
        thread.join(5)
