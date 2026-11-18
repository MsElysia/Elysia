"""Contract for the unified status server's OpenAI chat route.

The handler under test is the real ``elysia.py`` status server. Chat is a
local stub, so the test never calls a model or another service.
"""

from __future__ import annotations

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

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
    module.API_TOKEN = FICTIONAL_TOKEN
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


def _post(port, path, body, token=FICTIONAL_TOKEN, content_length=None):
    if isinstance(body, bytes):
        data = body
    else:
        data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if content_length is not None:
        headers["Content-Length"] = content_length
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return exc.code, parsed


def test_openai_chat_reports_model_failure_without_a_completion(status_server):
    module, port = status_server
    stub = ChatStub(result=("", "fictional-model-down"))
    module._status_system = stub

    status, body = _post(
        port,
        "/v1/chat/completions",
        {"messages": [{"role": "user", "content": "fictional-ping"}]},
    )

    assert status == 502
    assert body == {
        "error": {"message": "fictional-model-down", "type": "chat_failed"}
    }
    assert "choices" not in body
    assert stub.calls == ["fictional-ping"]


def test_openai_chat_rejects_a_request_that_would_not_call_a_model(status_server):
    module, port = status_server
    stub = ChatStub(result=("should-not-run", ""))
    module._status_system = stub

    cases = [
        (b"{not-json", 400, "invalid_request_error"),
        (["not-an-object"], 400, "invalid_request_error"),
        ({"messages": "fictional-ping"}, 400, "invalid_request_error"),
        ({"messages": [{"role": "user", "content": "  "}]}, 400, "invalid_request_error"),
        ({"messages": [{"role": "user", "content": ["not-text"]}]}, 400, "invalid_request_error"),
        ({"messages": ["not-an-object"]}, 400, "invalid_request_error"),
    ]
    for body, expected_status, error_type in cases:
        status, payload = _post(port, "/v1/chat/completions", body)
        assert status == expected_status
        assert payload["error"]["type"] == error_type
        assert "choices" not in payload

    status, payload = _post(
        port,
        "/v1/chat/completions",
        {"messages": [{"role": "user", "content": "fictional-ping"}]},
        content_length="nope",
    )
    assert status == 400
    assert payload["error"]["type"] == "invalid_request_error"
    assert stub.calls == []

    module._status_system = None
    status, payload = _post(
        port,
        "/v1/chat/completions",
        {"messages": [{"role": "user", "content": "fictional-ping"}]},
    )
    assert status == 503
    assert payload == {
        "error": {"message": "System not initialized", "type": "service_unavailable"}
    }
    assert stub.calls == []


def test_openai_chat_returns_a_completion_only_for_a_reply(status_server):
    module, port = status_server
    stub = ChatStub(result=("fictional-reply", ""))
    module._status_system = stub

    status, body = _post(
        port,
        "/v1/chat/completions",
        {
            "messages": [
                {"role": "system", "content": "ignore"},
                {"role": "user", "content": " alpha "},
                {"role": "user", "content": " beta "},
            ]
        },
    )

    assert status == 200
    assert body["object"] == "chat.completion"
    assert body["choices"] == [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "fictional-reply"},
            "finish_reason": "stop",
        }
    ]
    assert "error" not in body
    assert stub.calls == ["alpha   beta"]

    failing = ChatStub(error=RuntimeError("fictional-chat-exception"))
    module._status_system = failing
    status, body = _post(
        port,
        "/v1/chat/completions",
        {"messages": [{"role": "user", "content": "fictional-ping"}]},
    )
    assert status == 500
    assert body == {
        "error": {"message": "fictional-chat-exception", "type": "server_error"}
    }
    assert "choices" not in body
    assert failing.calls == ["fictional-ping"]

    both = ChatStub(result=("fictional-reply", "fictional-also-failed"))
    module._status_system = both
    status, body = _post(
        port,
        "/v1/chat/completions",
        {"messages": [{"role": "user", "content": "fictional-ping"}]},
    )
    assert status == 502
    assert body["error"]["message"] == "fictional-also-failed"
    assert "choices" not in body


def test_openai_chat_requires_the_configured_token(status_server):
    module, port = status_server
    stub = ChatStub(result=("fictional-reply", ""))
    module._status_system = stub

    status, body = _post(
        port,
        "/v1/chat/completions",
        {"messages": [{"role": "user", "content": "fictional-ping"}]},
        token=None,
    )
    assert status == 401
    assert "Unauthorized" in body["error"]
    assert stub.calls == []

    status, body = _post(
        port,
        "/v1/chat/completions",
        {"messages": [{"role": "user", "content": "fictional-ping"}]},
        token="wrong-token",
    )
    assert status == 401
    assert stub.calls == []


def test_plain_chat_still_returns_the_error_field_the_desktop_client_reads(status_server):
    module, port = status_server
    stub = ChatStub(result=("", "fictional-desktop-error"))
    module._status_system = stub

    status, body = _post(port, "/chat", {"message": "fictional-ping"})

    assert status == 200
    assert body["error"] == "fictional-desktop-error"
    assert body.get("reply", "") == ""
    assert stub.calls == ["fictional-ping"]
