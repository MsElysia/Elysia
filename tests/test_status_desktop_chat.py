"""Contract for the unified status server's desktop POST /chat route.

The handler under test is the real ``elysia.py`` status server. The attach
client is the real ``elysia_interface`` chat call. Chat itself is a local
stub, so the test never calls a model or another service.
"""

from __future__ import annotations

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import elysia_interface
import pytest

ROOT = Path(__file__).resolve().parents[1]
FICTIONAL_TOKEN = "fictional-token"


def _load_status_module():
    spec = importlib.util.spec_from_file_location("elysia_status_server", ROOT / "elysia.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ChatStub:
    def __init__(self, result=("", ""), error=None):
        self.result = result
        self.error = error
        self.calls = []

    def chat_with_llm(self, message):
        self.calls.append(message)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture(scope="module")
def status_server():
    module = _load_status_module()
    original_token = module.API_TOKEN
    module.API_TOKEN = None
    module._status_system = None
    handler = module._make_status_handler()
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield module, server.server_address[1]
    finally:
        module.API_TOKEN = original_token
        module._status_system = None
        server.shutdown()
        server.server_close()


def _post(port, body, token=None, content_length=None, raw=None):
    if raw is not None:
        data = raw
    elif isinstance(body, bytes):
        data = body
    else:
        data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if content_length is not None:
        headers["Content-Length"] = content_length
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/chat",
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw_body}
        return exc.code, parsed


def test_desktop_chat_reports_failure_without_a_reply(status_server):
    module, port = status_server
    stub = ChatStub(result=("", "fictional-model-down"))
    module._status_system = stub

    status, body = _post(port, {"message": "fictional-ping"})

    assert status == 502
    assert body == {"error": "fictional-model-down"}
    assert "reply" not in body
    assert stub.calls == ["fictional-ping"]

    stub.result = ("fictional-reply", "fictional-model-down")
    stub.calls.clear()
    status, body = _post(port, {"message": "fictional-both"})
    assert status == 502
    assert body == {"error": "fictional-model-down"}
    assert "reply" not in body
    assert stub.calls == ["fictional-both"]

    stub.result = ("   ", "")
    status, body = _post(port, {"message": "fictional-blank-reply"})
    assert status == 502
    assert body == {"error": "Chat returned no reply"}

    stub.error = RuntimeError("fictional-chat-failure")
    status, body = _post(port, {"message": "fictional-raises"})
    assert status == 500
    assert body == {"error": "fictional-chat-failure"}

    stub.error = None
    stub.result = ("not-a-pair",)
    status, body = _post(port, {"message": "fictional-shape"})
    assert status == 500
    assert body == {"error": "Chat returned an invalid result"}

    stub.result = ("fictional-reply", "")
    stub.calls.clear()
    status, body = _post(port, {"message": "fictional-ok"})
    assert status == 200
    assert body == {"reply": "fictional-reply"}
    assert stub.calls == ["fictional-ok"]


def test_desktop_chat_rejects_a_request_that_would_not_call_chat(status_server):
    module, port = status_server
    stub = ChatStub(result=("should-not-run", ""))
    module._status_system = stub
    module.API_TOKEN = FICTIONAL_TOKEN

    status, body = _post(port, {"message": "fictional-ping"})
    assert status == 401
    assert body["error"] == "Unauthorized"
    assert stub.calls == []

    status, body = _post(port, {"message": "fictional-ping"}, token="wrong-token")
    assert status == 401
    assert stub.calls == []

    module.API_TOKEN = None
    module._status_system = None
    status, body = _post(port, {"message": "fictional-ping"})
    assert status == 503
    assert body == {"error": "System not initialized"}

    module._status_system = stub
    cases = [
        (b"{not-json", 400),
        (["not-an-object"], 400),
        ({"message": 12}, 400),
        ({"message": "   "}, 400),
        ({}, 400),
    ]
    for payload, expected in cases:
        status, body = _post(port, payload)
        assert status == expected, payload
        assert "error" in body
        assert "reply" not in body
    status, body = _post(port, {"message": "fictional-ping"}, content_length="nope")
    assert status == 400
    assert body == {"error": "Content-Length must be an integer"}
    assert stub.calls == []


def test_attach_client_reads_the_chat_error(status_server):
    module, port = status_server
    module.API_TOKEN = None
    stub = ChatStub(result=("", "fictional-model-down"))
    module._status_system = stub
    original_url = elysia_interface.STATUS_URL
    elysia_interface.STATUS_URL = f"http://127.0.0.1:{port}"
    try:
        client = elysia_interface.ElysiaInterface(attach_only=True)
        reply, err, connected = client._chat_via_backend("fictional-ping")
        assert (reply, err, connected) == ("", "fictional-model-down", True)
        assert client._render_chat_result(reply, err, connected) == (
            "\nElysia: fictional-model-down\n"
        )
        assert stub.calls == ["fictional-ping"]

        stub.result = ("fictional-reply", "")
        reply, err, connected = client._chat_via_backend("fictional-ok")
        assert (reply, err, connected) == ("fictional-reply", "", True)
        assert client._render_chat_result(reply, err, connected) == (
            "\nElysia: fictional-reply\n"
        )

        elysia_interface.STATUS_URL = "http://127.0.0.1:9"
        reply, err, connected = client._chat_via_backend("fictional-offline")
        assert reply == ""
        assert connected is False
        rendered = client._render_chat_result(reply, err, connected)
        assert "Could not connect to AI" in rendered
        assert "elysia.py is running" in rendered
        assert "fictional-model-down" not in rendered
    finally:
        elysia_interface.STATUS_URL = original_url
