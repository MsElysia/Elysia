from __future__ import annotations

import asyncio

from project_guardian.llm.openai_http_chat import (
    build_openai_chat_url,
    post_openai_chat_completion_async,
    post_openai_chat_completion_sync,
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, *args, **kwargs):
        self.last_url = None
        self.last_headers = None
        self.last_json = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, headers=None, json=None):
        self.last_url = url
        self.last_headers = headers
        self.last_json = json
        return _FakeResponse({"ok": True, "echo": json})


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.last_url = None
        self.last_headers = None
        self.last_json = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        self.last_url = url
        self.last_headers = headers
        self.last_json = json
        return _FakeResponse({"ok": True, "echo": json})


def test_build_openai_chat_url():
    assert build_openai_chat_url("https://api.openai.com/v1/") == "https://api.openai.com/v1/chat/completions"


def test_post_openai_chat_completion_sync(monkeypatch):
    import project_guardian.llm.openai_chat_transport as m

    monkeypatch.setattr(m.httpx, "Client", _FakeClient)
    out = post_openai_chat_completion_sync(
        base_url="https://api.openai.com/v1",
        api_key="k",
        body={"model": "x", "messages": []},
        timeout_sec=10.0,
    )
    assert out["ok"] is True


def test_post_openai_chat_completion_async(monkeypatch):
    import project_guardian.llm.openai_chat_transport as m

    monkeypatch.setattr(m.httpx, "AsyncClient", _FakeAsyncClient)
    out = asyncio.run(
        post_openai_chat_completion_async(
            base_url="https://api.openai.com/v1",
            api_key="k",
            body={"model": "x", "messages": []},
            timeout_sec=10.0,
        )
    )
    assert out["ok"] is True
