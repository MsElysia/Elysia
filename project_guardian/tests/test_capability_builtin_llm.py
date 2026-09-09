# Builtin LLM capability when tool_registry has no call_tool (core catalog).

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from unittest.mock import patch

from project_guardian.capability_execution import execute_capability_kind


class _FakeUnified:
    def __init__(self, reply: str = "ok", err: str = ""):
        self.reply = reply
        self.err = err
        self.last_messages: List[Dict[str, str]] = []
        self.last_skip_capability_preamble = None

    def _autonomy_llm_completion(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 2000,
        *,
        module_name: str = "planner",
        agent_name: Any = "orchestrator",
        prompt_extra: Any = None,
        skip_capability_preamble: bool = False,
        **_: Any,
    ) -> Tuple[str, str]:
        self.last_messages = list(messages)
        self.last_skip_capability_preamble = skip_capability_preamble
        return self.reply, self.err


class _FakeToolRegistry:
    """Mimics core_modules catalog: list_tools + metadata only."""

    tools = {"elysia_builtin_llm": {"id": "elysia_builtin_llm"}}

    def list_tools(self):
        return list(self.tools.keys())

    def tools_map(self):
        return dict(self.tools)


def test_execute_capability_elysia_builtin_llm_without_call_tool():
    uni = _FakeUnified(reply="hello-model", err="")
    g = type(
        "G",
        (),
        {
            "_unified_system": uni,
            "_modules": {"tool_registry": _FakeToolRegistry()},
        },
    )()
    out = execute_capability_kind(
        g,
        "tool",
        "elysia_builtin_llm",
        {"method": "execute", "task": "ping"},
    )
    assert out["success"] is True
    res = out.get("result") or {}
    assert res.get("success") is True
    assert res.get("data") == "hello-model"
    assert uni.last_messages and "ping" in uni.last_messages[-1].get("content", "")
    assert uni.last_skip_capability_preamble is True


def test_execute_capability_elysia_builtin_llm_forwards_structured_role():
    class _U(_FakeUnified):
        def __init__(self) -> None:
            super().__init__(reply="ok", err="")
            self.seen_role: Any = None

        def _autonomy_llm_completion(
            self,
            messages: List[Dict[str, str]],
            max_tokens: int = 2000,
            *,
            module_name: str = "planner",
            agent_name: Any = "orchestrator",
            prompt_extra: Any = None,
            skip_capability_preamble: bool = False,
            structured_role: Any = None,
            **__: Any,
        ) -> Tuple[str, str]:
            self.last_messages = list(messages)
            self.last_skip_capability_preamble = skip_capability_preamble
            self.seen_role = structured_role
            return self.reply, self.err

    uni = _U()
    g = type(
        "G",
        (),
        {"_unified_system": uni, "_modules": {"tool_registry": _FakeToolRegistry()}},
    )()
    execute_capability_kind(
        g,
        "tool",
        "elysia_builtin_llm",
        {"prompt": "x", "structured_role": "tool_registry:argument_planning"},
    )
    assert uni.seen_role == "tool_registry:argument_planning"


def test_execute_capability_elysia_builtin_llm_no_unified_fails():
    g = type("G", (), {"_modules": {"tool_registry": _FakeToolRegistry()}})()
    out = execute_capability_kind(
        g,
        "tool",
        "elysia_builtin_llm",
        {"prompt": "x"},
    )
    assert out["success"] is False
    assert "call_tool" in str(out.get("error", "")) or "unified" in str(out).lower()


class _FakeWebResponse:
    status = 200
    headers = {"Content-Type": "text/plain; charset=utf-8"}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limit):
        return b"hello from builtin web"


def test_execute_capability_builtin_web_fetches_safe_url():
    g = type("G", (), {"_modules": {"tool_registry": _FakeToolRegistry()}})()
    with patch(
        "project_guardian.capability_execution.urllib.request.urlopen",
        return_value=_FakeWebResponse(),
    ) as urlopen:
        out = execute_capability_kind(
            g,
            "tool",
            "elysia_builtin_web",
            {"query": "fetch https://example.com/page"},
        )

    assert out["success"] is True
    assert out["data"]["url"] == "https://example.com/page"
    assert out["data"]["text"] == "hello from builtin web"
    assert urlopen.called


def test_execute_capability_builtin_exec_is_gated():
    g = type("G", (), {"_modules": {"tool_registry": _FakeToolRegistry()}})()
    out = execute_capability_kind(
        g,
        "tool",
        "elysia_builtin_exec",
        {"task": "run whoami"},
    )
    assert out["success"] is False
    assert out["requires_approval"] is True
    assert out["status"] == "deferred"
