"""Guardian control-panel HTML pages render on the installed Starlette."""

import sys
import threading
import types
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
    absent. The page routes themselves do not need that module, so the test
    loads ``project_guardian.ui.app`` after recording the package-init failure.
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
    app_module_name = "project_guardian.ui.app"
    app = _load_dashboard_app()
    module = sys.modules[app_module_name]
    control = tmp_path / "CONTROL.md"
    control.write_text("CURRENT_TASK: NONE\n", encoding="utf-8")
    (tmp_path / "REPORTS").mkdir()
    monkeypatch.setattr(module, "project_root", tmp_path)
    return app


def test_dashboard_and_task_builder_render(dashboard):
    client = TestClient(dashboard, client=("127.0.0.1", 50000))

    home = client.get("/")
    assert home.status_code == 200
    assert "Project Guardian Control Panel" in home.text
    assert "Current Task" in home.text

    builder = client.get("/tasks/new")
    assert builder.status_code == 200
    assert "Create Task" in builder.text
    assert 'action="/tasks/create"' in builder.text

    for path, marker in (
        ("/mutations/new", "Mutation"),
        ("/history", "History"),
        ("/reviews", "Review"),
        ("/mutations", "Mutation"),
    ):
        page = client.get(path)
        assert page.status_code == 200, path
        assert marker in page.text


def test_remote_denial_page_renders(dashboard):
    client = TestClient(dashboard, client=("192.0.2.8", 50000))
    response = client.get("/")
    assert response.status_code == 403
    assert "Local-only UI: remote access denied" in response.text


def test_live_http_dashboard(dashboard):
    config = uvicorn.Config(dashboard, host="127.0.0.1", port=0, log_level="warning")
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
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/tasks/new", timeout=5) as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
        assert "Create Task" in body
    finally:
        server.should_exit = True
        thread.join(5)
