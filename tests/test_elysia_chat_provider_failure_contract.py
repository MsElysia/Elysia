"""No-network regressions for PR #160's configured-provider false-success path.

Extract only the relevant class methods from the exact checked-out source via AST.
This intentionally avoids importing elysia.py (whose top-level imports can start
heavy product initialization). A separate native-Windows runtime check remains required.
"""
from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
import sys
import textwrap
from types import ModuleType, SimpleNamespace

import pytest


REPO = Path(__file__).resolve().parents[1]
METHODS = {
    "_cloud_chat_configured",
    "_offline_chat_reply",
    "_llm_completion_cloud_preferred",
    "_llm_completion_cloud_openai",
    "_llm_completion_cloud_openrouter",
    "_openai_client_direct",
    "chat_with_llm",
}


@pytest.fixture
def isolated_chat(monkeypatch):
    # Preserve actual production method source, but never import the live entrypoint.
    source = (REPO / "elysia.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    cls = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "UnifiedElysiaSystem"
    )
    picked = [
        node for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in METHODS
    ]
    assert {node.name for node in picked} == METHODS
    body = "\n\n".join(textwrap.indent(ast.unparse(node), "    ") for node in picked)
    namespace = {"os": os, "logger": logging.getLogger("elysia-chat-contract")}
    exec(compile("from __future__ import annotations\nclass IsolatedChat:\n" + body,
                 str(REPO / "elysia.py"), "exec"), namespace)

    # Stub all cloud dependencies. No actual transport or credential reads may occur.
    package = ModuleType("project_guardian")
    package.__path__ = []
    cloud = ModuleType("project_guardian.cloud_api_state")
    key_module = ModuleType("project_guardian.api_key_manager")
    manager = SimpleNamespace(
        keys=SimpleNamespace(openai=None, openrouter=None),
        get_openai_client=lambda: None,
    )
    cloud.blocked = False
    cloud.cloud_credentials_snapshot = lambda refresh=False: {
        "openai": bool(manager.keys.openai),
        "openrouter": bool(manager.keys.openrouter),
    }
    cloud.openai_usable_for_routing = lambda: bool(manager.keys.openai) and not cloud.blocked
    cloud.openai_routing_block_reason = lambda: "openai_policy_disabled" if cloud.blocked else "openai_key_missing"
    key_module.get_api_key_manager = lambda: manager

    monkeypatch.setitem(sys.modules, "project_guardian", package)
    monkeypatch.setitem(sys.modules, "project_guardian.cloud_api_state", cloud)
    monkeypatch.setitem(sys.modules, "project_guardian.api_key_manager", key_module)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    system = namespace["IsolatedChat"]()
    system.get_income_generator = lambda: None
    system.get_status = lambda: {"components": {}, "uptime": "0s"}
    system._unified_chat_llm_router_enabled = lambda: False
    return system, manager, cloud


def test_unconfigured_chat_has_an_offline_status(isolated_chat):
    system, _, _ = isolated_chat
    reply, err = system._offline_chat_reply("hello", "local unavailable")
    assert "offline chat mode" in reply
    assert not err


@pytest.mark.parametrize("key", ["OPENAI_API_KEY", "OPENROUTER_API_KEY"])
@pytest.mark.parametrize("route", ["cloud_only", "unified"])
def test_configured_backend_error_is_never_a_success(isolated_chat, monkeypatch, key, route):
    system, _, _ = isolated_chat
    monkeypatch.setenv(key, "synthetic-never-send")
    failure = "synthetic authentication rejected"
    if route == "cloud_only":
        system._chat_with_llm_cloud_only = lambda _: ("", failure)
    else:
        system._unified_chat_llm_router_enabled = lambda: True
        system._mistral_model_for_chat = lambda: "synthetic-local"
        system.guardian = None
        router = ModuleType("project_guardian.unified_llm_route")
        router.unified_chat_completion = lambda **kwargs: ("", failure, {"backend": "openai"})
        monkeypatch.setitem(sys.modules, "project_guardian.unified_llm_route", router)

    reply, err = system.chat_with_llm("hello")
    assert reply == ""
    assert err == failure
    assert "no cloud API keys" not in (reply + err)


def test_key_manager_keys_count_even_without_env(isolated_chat):
    system, manager, _ = isolated_chat
    manager.keys.openrouter = "synthetic-manager-key"
    reply, err = system._offline_chat_reply("hello", "synthetic transport timeout")
    assert not reply
    assert "synthetic transport timeout" in err


def test_unreadable_credential_state_fails_closed(isolated_chat):
    system, _, cloud = isolated_chat
    def broken(*args, **kwargs):
        raise RuntimeError("synthetic key manager error")
    cloud.cloud_credentials_snapshot = broken
    reply, err = system._offline_chat_reply("hello", "synthetic transport error")
    assert not reply
    assert err == "synthetic transport error"


def test_earlier_provider_error_survives_failed_fallback(isolated_chat):
    system, _, _ = isolated_chat
    system._llm_completion_cloud_openai = lambda *a: ("", "synthetic OpenAI 401")
    system._llm_completion_cloud_openrouter = lambda *a: ("", "OpenRouter key missing")
    reply, err = system._llm_completion_cloud_preferred([{"role": "user", "content": "hi"}], 5)
    assert not reply
    assert "synthetic OpenAI 401" in err
    assert "OpenRouter key missing" in err


def test_successful_provider_fallback_is_still_success(isolated_chat):
    system, _, _ = isolated_chat
    system._llm_completion_cloud_openai = lambda *a: ("", "synthetic OpenAI 401")
    system._llm_completion_cloud_openrouter = lambda *a: ("synthetic answer", "")
    assert system._llm_completion_cloud_preferred([], 5) == ("synthetic answer", "")


def test_openai_policy_denial_prevents_transport(isolated_chat):
    system, manager, cloud = isolated_chat
    manager.keys.openai = "synthetic-key"
    cloud.blocked = True
    manager.get_openai_client = lambda: pytest.fail("client creation bypassed routing policy")
    reply, err = system._llm_completion_cloud_openai([], 5)
    assert not reply
    assert "openai_policy_disabled" in err


def test_openai_configured_transport_error_preserved(isolated_chat):
    system, manager, _ = isolated_chat
    manager.keys.openai = "synthetic-key"
    seen = []
    def fail_create(**kwargs):
        seen.append(kwargs)
        raise RuntimeError("synthetic OpenAI transport denied")
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail_create)))
    manager.get_openai_client = lambda: client
    reply, err = system._llm_completion_cloud_openai([{"role": "user", "content": "hello"}], 5)
    assert not reply
    assert "synthetic OpenAI transport denied" in err
    assert len(seen) == 1


def test_openrouter_configured_transport_error_preserved(isolated_chat, monkeypatch):
    system, manager, _ = isolated_chat
    manager.keys.openrouter = "synthetic-key"
    seen = []
    def fail_create(**kwargs):
        seen.append(kwargs)
        raise RuntimeError("synthetic OpenRouter transport denied")
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fail_create)))
    fake_openai = ModuleType("openai")
    fake_openai.OpenAI = lambda **kwargs: client
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    reply, err = system._llm_completion_cloud_openrouter(
        [{"role": "user", "content": "hello"}], 5
    )
    assert not reply
    assert "synthetic OpenRouter transport denied" in err
    assert len(seen) == 1


def test_unconfigured_openrouter_never_constructs_client(isolated_chat, monkeypatch):
    system, _, _ = isolated_chat
    fake_openai = ModuleType("openai")
    fake_openai.OpenAI = lambda **kwargs: pytest.fail("unconfigured provider contacted")
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    reply, err = system._llm_completion_cloud_openrouter([], 5)
    assert not reply
    assert "key not loaded" in err
