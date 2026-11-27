"""POST /mutations/create must not replace an existing mutation payload."""

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
    absent. Mutation payload creation does not need that module.
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
    (tmp_path / "MUTATIONS").mkdir()
    monkeypatch.setattr(module, "project_root", tmp_path)
    return app, tmp_path


def _post(client, payload_name, summary, path, content):
    return client.post(
        "/mutations/create",
        data={
            "payload_name": payload_name,
            "summary": summary,
            "file_paths": [path],
            "file_contents": [content],
        },
    )


def test_existing_payload_is_not_replaced(dashboard):
    app, root = dashboard
    original = '{"summary":"keep-fictional"}\n'
    payload_file = root / "MUTATIONS" / "fictional.json"
    payload_file.write_text(original, encoding="utf-8")
    target = root / "fictional-link-target.json"
    target.write_text("link-target-bytes", encoding="utf-8")
    link = root / "MUTATIONS" / "fictional-link.json"
    link.symlink_to(target)
    client = TestClient(app, client=("127.0.0.1", 50000))

    conflict = _post(
        client,
        "fictional.json",
        "replacement-fictional",
        "fictional_note.txt",
        "fictional-bytes",
    )

    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "Mutation payload MUTATIONS/fictional.json already exists"
    assert payload_file.read_text(encoding="utf-8") == original

    linked = _post(
        client,
        "fictional-link.json",
        "replacement-fictional",
        "fictional_note.txt",
        "fictional-bytes",
    )
    assert linked.status_code == 409
    assert linked.json()["detail"] == "Mutation payload MUTATIONS/fictional-link.json already exists"
    assert target.read_text(encoding="utf-8") == "link-target-bytes"
    assert link.is_symlink()

    created = _post(
        client,
        "fictional-new.json",
        "created-fictional",
        "fictional_note.txt",
        "fictional-bytes",
    )
    assert created.status_code == 200
    body = created.json()
    assert body["status"] == "created"
    assert body["payload_name"] == "MUTATIONS/fictional-new.json"
    new_file = root / "MUTATIONS" / "fictional-new.json"
    stored = json.loads(new_file.read_text(encoding="utf-8"))
    assert stored["summary"] == "created-fictional"
    assert stored["touched_paths"] == ["fictional_note.txt"]
    assert stored["changes"] == [
        {"path": "fictional_note.txt", "content": "fictional-bytes"}
    ]
    created_bytes = new_file.read_text(encoding="utf-8")

    repeat = _post(
        client,
        "fictional-new.json",
        "second-fictional",
        "fictional_note.txt",
        "other-bytes",
    )
    assert repeat.status_code == 409
    assert new_file.read_text(encoding="utf-8") == created_bytes
    assert payload_file.read_text(encoding="utf-8") == original


def _multipart(payload_name, summary, path, content):
    boundary = "----elysia-mutation-create"
    parts = (
        ("payload_name", payload_name),
        ("summary", summary),
        ("file_paths", path),
        ("file_contents", content),
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


def _live_post(port, payload_name, summary, path, content):
    body, headers = _multipart(payload_name, summary, path, content)
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/mutations/create",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_live_http_refuses_existing_payload(dashboard):
    app, root = dashboard
    original = '{"summary":"keep-fictional-live"}\n'
    payload_file = root / "MUTATIONS" / "fictional-live.json"
    payload_file.write_text(original, encoding="utf-8")
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
            port,
            "fictional-live.json",
            "replacement-fictional",
            "fictional_note.txt",
            "fictional-bytes",
        )
        assert status == 409
        assert body["detail"] == "Mutation payload MUTATIONS/fictional-live.json already exists"
        assert payload_file.read_text(encoding="utf-8") == original

        created_status, created = _live_post(
            port,
            "fictional-live-new.json",
            "created-fictional",
            "fictional_note.txt",
            "fictional-bytes",
        )
        assert created_status == 200
        assert created["status"] == "created"
        new_file = root / "MUTATIONS" / "fictional-live-new.json"
        stored = json.loads(new_file.read_text(encoding="utf-8"))
        assert stored["summary"] == "created-fictional"
        assert stored["changes"][0]["content"] == "fictional-bytes"
    finally:
        server.should_exit = True
        thread.join(5)
