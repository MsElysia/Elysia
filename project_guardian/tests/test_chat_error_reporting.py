"""
ELY-160-CHAT-ERROR-REPAIR-001 regressions.

Configured cloud auth/transport failures must remain errors (not a successful
offline reply claiming no API keys). Direct env clients must honor existing
OpenAI routing policy before construction or request execution.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Tuple
from unittest.mock import MagicMock

import pytest

_ROOT_ELYSIA = Path(__file__).resolve().parents[2] / "elysia.py"

# Synthetic credentials — never real provider secrets.
SYN_OPENAI = "sk-test-SYNTHETIC-OPENAI-KEY-ely160-do-not-use"
SYN_OPENROUTER = "sk-or-test-SYNTHETIC-OPENROUTER-KEY-ely160-do-not-use"


def _load_unified_elysia_system():
    spec = importlib.util.spec_from_file_location("elysia_root_app_chat_err", _ROOT_ELYSIA)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.UnifiedElysiaSystem


def _fresh_inst(monkeypatch, *, unified: bool = False):
    UnifiedElysiaSystem = _load_unified_elysia_system()
    inst = UnifiedElysiaSystem.__new__(UnifiedElysiaSystem)
    inst.guardian = None
    inst._last_autonomy_unified_meta = None
    monkeypatch.setattr(inst, "_unified_chat_llm_router_enabled", lambda: unified)
    monkeypatch.setattr(inst, "_mistral_model_for_chat", lambda: "mistral")
    monkeypatch.setattr(inst, "get_income_generator", lambda: None)
    monkeypatch.setattr(
        inst,
        "get_status",
        lambda: {"uptime": "0s", "components": {"guardian_core": True, "runtime_loop": False, "architect_core": False, "integrated_modules": 0}},
    )
    return UnifiedElysiaSystem, inst


def _assert_no_secret_leak(*blobs: Any) -> None:
    joined = " ".join("" if b is None else str(b) for b in blobs)
    assert SYN_OPENAI not in joined
    assert SYN_OPENROUTER not in joined


# ---------------------------------------------------------------------------
# Baseline defect: configured failure → false offline success
# ---------------------------------------------------------------------------


def test_openai_auth_failure_remains_error(monkeypatch):
    UnifiedElysiaSystem, inst = _fresh_inst(monkeypatch, unified=False)
    monkeypatch.setenv("OPENAI_API_KEY", SYN_OPENAI)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    monkeypatch.setattr(
        inst,
        "_llm_completion_cloud_openai",
        lambda m, t: ("", "Error code: 401 - Incorrect API key provided"),
    )
    monkeypatch.setattr(
        inst,
        "_llm_completion_cloud_openrouter",
        lambda m, t: ("", "OPENROUTER_API_KEY not set (and income API manager unavailable)."),
    )

    reply, err = UnifiedElysiaSystem.chat_with_llm(inst, "ping")
    assert err, "configured OpenAI auth failure must surface as error"
    assert "401" in err or "Incorrect API key" in err or "API key" in err
    assert "no cloud API keys" not in (reply or "").lower()
    assert "offline chat mode" not in (reply or "").lower()
    _assert_no_secret_leak(reply, err)


def test_openrouter_auth_failure_remains_error(monkeypatch):
    UnifiedElysiaSystem, inst = _fresh_inst(monkeypatch, unified=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", SYN_OPENROUTER)

    monkeypatch.setattr(
        inst,
        "_llm_completion_cloud_openai",
        lambda m, t: ("", "OPENAI_API_KEY not set (and income API manager unavailable)."),
    )
    monkeypatch.setattr(
        inst,
        "_llm_completion_cloud_openrouter",
        lambda m, t: ("", "Error code: 401 - User not found."),
    )

    reply, err = UnifiedElysiaSystem.chat_with_llm(inst, "ping")
    assert err, "configured OpenRouter auth failure must surface as error"
    assert "401" in err or "User not found" in err
    assert "no cloud API keys" not in (reply or "").lower()
    _assert_no_secret_leak(reply, err)


def test_openai_transport_failure_remains_error(monkeypatch):
    UnifiedElysiaSystem, inst = _fresh_inst(monkeypatch, unified=False)
    monkeypatch.setenv("OPENAI_API_KEY", SYN_OPENAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", SYN_OPENROUTER)

    monkeypatch.setattr(
        inst,
        "_llm_completion_cloud_openai",
        lambda m, t: ("", "Connection error: timed out contacting api.openai.com"),
    )
    monkeypatch.setattr(
        inst,
        "_llm_completion_cloud_openrouter",
        lambda m, t: ("", "Connection error: timed out contacting openrouter.ai"),
    )

    reply, err = UnifiedElysiaSystem.chat_with_llm(inst, "ping")
    assert err
    assert "timed out" in err.lower() or "connection" in err.lower()
    assert "no cloud API keys" not in (reply or "").lower()
    _assert_no_secret_leak(reply, err)


def test_client_construction_failure_remains_error(monkeypatch):
    UnifiedElysiaSystem, inst = _fresh_inst(monkeypatch, unified=False)
    monkeypatch.setenv("OPENAI_API_KEY", SYN_OPENAI)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("ELYSIA_DISABLE_OPENAI_ROUTING", "0")

    constructions: List[dict] = []

    class BoomOpenAI:
        def __init__(self, *args, **kwargs):
            constructions.append(dict(kwargs))
            raise RuntimeError(f"client_init_failed key={kwargs.get('api_key')}")

    import sys

    fake_openai = SimpleNamespace(OpenAI=BoomOpenAI)
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    reply, err = UnifiedElysiaSystem.chat_with_llm(inst, "ping")
    assert constructions, "direct client construction should have been attempted"
    assert err, "client construction failure must remain an error"
    assert "no cloud API keys" not in (reply or "").lower()
    _assert_no_secret_leak(reply, err)


def test_dashboard_reports_failure_when_all_configured_backends_fail(monkeypatch):
    try:
        from project_guardian.ui_control_panel import UIControlPanel
    except ImportError:
        pytest.skip("Flask not available for UI testing")

    UnifiedElysiaSystem, inst = _fresh_inst(monkeypatch, unified=False)
    monkeypatch.setenv("OPENAI_API_KEY", SYN_OPENAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", SYN_OPENROUTER)
    monkeypatch.setattr(
        inst,
        "_llm_completion_cloud_openai",
        lambda m, t: ("", "Error code: 401 - Incorrect API key provided"),
    )
    monkeypatch.setattr(
        inst,
        "_llm_completion_cloud_openrouter",
        lambda m, t: ("", "Error code: 401 - User not found."),
    )

    orch = MagicMock()
    orch._unified_system = inst
    panel = UIControlPanel(orch)

    with panel.app.test_client() as client:
        resp = client.post(
            "/api/chat",
            data=json.dumps({"message": "hello"}),
            content_type="application/json",
        )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("success") is False
    assert data.get("error")
    assert "no cloud API keys" not in str(data.get("reply") or "").lower()
    _assert_no_secret_leak(data.get("error"), data.get("reply"), json.dumps(data))


def test_errors_do_not_expose_synthetic_credentials(monkeypatch):
    UnifiedElysiaSystem, inst = _fresh_inst(monkeypatch, unified=False)
    monkeypatch.setenv("OPENAI_API_KEY", SYN_OPENAI)

    monkeypatch.setattr(
        inst,
        "_llm_completion_cloud_openai",
        lambda m, t: ("", f"Unauthorized: invalid key {SYN_OPENAI}"),
    )
    monkeypatch.setattr(
        inst,
        "_llm_completion_cloud_openrouter",
        lambda m, t: ("", "OPENROUTER_API_KEY not set (and income API manager unavailable)."),
    )

    reply, err = UnifiedElysiaSystem.chat_with_llm(inst, "ping")
    assert err
    _assert_no_secret_leak(reply, err)


# ---------------------------------------------------------------------------
# Genuine unconfigured offline status + fallback success
# ---------------------------------------------------------------------------


def test_genuine_unconfigured_offline_is_status_not_model_answer(monkeypatch):
    UnifiedElysiaSystem, inst = _fresh_inst(monkeypatch, unified=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    monkeypatch.setattr(
        inst,
        "_llm_completion_cloud_openai",
        lambda m, t: ("", "OPENAI_API_KEY not set (and income API manager unavailable)."),
    )
    monkeypatch.setattr(
        inst,
        "_llm_completion_cloud_openrouter",
        lambda m, t: ("", "OPENROUTER_API_KEY not set (and income API manager unavailable)."),
    )

    reply, err = UnifiedElysiaSystem.chat_with_llm(inst, "status check")
    assert not err
    assert reply
    low = reply.lower()
    assert "status" in low or "offline" in low
    assert "no cloud api keys" in low or "no llm backend" in low or "offline chat" in low
    # Must not look like a fabricated model completion claiming to be the assistant persona only
    assert "i am elysia" not in low


def test_authorized_fallback_success_after_openai_failure(monkeypatch):
    UnifiedElysiaSystem, inst = _fresh_inst(monkeypatch, unified=False)
    monkeypatch.setenv("OPENAI_API_KEY", SYN_OPENAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", SYN_OPENROUTER)

    monkeypatch.setattr(
        inst,
        "_llm_completion_cloud_openai",
        lambda m, t: ("", "Error code: 401 - Incorrect API key provided"),
    )
    monkeypatch.setattr(
        inst,
        "_llm_completion_cloud_openrouter",
        lambda m, t: ("fallback-ok", ""),
    )

    reply, err = UnifiedElysiaSystem.chat_with_llm(inst, "ping")
    assert reply == "fallback-ok"
    assert not err
    _assert_no_secret_leak(reply, err)


# ---------------------------------------------------------------------------
# Provider authorization (existing ELYSIA_DISABLE_OPENAI_ROUTING boundary)
# ---------------------------------------------------------------------------


def test_policy_disabled_openai_zero_client_construction_and_requests(monkeypatch):
    UnifiedElysiaSystem, inst = _fresh_inst(monkeypatch, unified=False)
    monkeypatch.setenv("OPENAI_API_KEY", SYN_OPENAI)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("ELYSIA_DISABLE_OPENAI_ROUTING", "1")

    constructions: List[dict] = []
    creates: List[dict] = []

    class TrackingCompletions:
        def create(self, **kwargs):
            creates.append(dict(kwargs))
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="leak"))])

    class TrackingChat:
        completions = TrackingCompletions()

    class TrackingOpenAI:
        def __init__(self, *args, **kwargs):
            constructions.append(dict(kwargs))
            self.chat = TrackingChat()

    import sys

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=TrackingOpenAI))

    # Also exercise preferred path (openai then openrouter).
    reply, err = UnifiedElysiaSystem._llm_completion_cloud_openai(
        inst, [{"role": "user", "content": "x"}], 16
    )
    assert constructions == []
    assert creates == []
    assert not reply
    assert err
    assert "policy" in err.lower() or "disabled" in err.lower()
    _assert_no_secret_leak(reply, err)

    # chat_with_llm must not succeed via a fabricated offline "no keys" claim when key is present.
    monkeypatch.setattr(
        inst,
        "_llm_completion_cloud_openrouter",
        lambda m, t: ("", "OPENROUTER_API_KEY not set (and income API manager unavailable)."),
    )
    # Re-bind openai path to real method (policy-aware) — already using real method above.
    chat_reply, chat_err = UnifiedElysiaSystem.chat_with_llm(inst, "ping")
    assert constructions == []
    assert creates == []
    assert "no cloud API keys" not in (chat_reply or "").lower()
    # With OpenAI disabled by policy and no OpenRouter, surface failure (not false offline success).
    assert chat_err or ("policy" in (chat_reply or "").lower())
    if chat_err:
        assert chat_reply == "" or "status" in (chat_reply or "").lower()
        # Prefer error channel for configured-but-disabled + other backends missing
        assert chat_err
    _assert_no_secret_leak(chat_reply, chat_err)


def test_policy_disabled_openai_still_allows_openrouter_fallback(monkeypatch):
    UnifiedElysiaSystem, inst = _fresh_inst(monkeypatch, unified=False)
    monkeypatch.setenv("OPENAI_API_KEY", SYN_OPENAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", SYN_OPENROUTER)
    monkeypatch.setenv("ELYSIA_DISABLE_OPENAI_ROUTING", "1")

    constructions: List[dict] = []
    creates: List[dict] = []

    class TrackingCompletions:
        def create(self, **kwargs):
            creates.append(dict(kwargs))
            model = kwargs.get("model") or ""
            if "openrouter" in str(kwargs.get("base_url") or "") or str(model).startswith("openai/"):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="or-ok"))]
                )
            raise AssertionError("OpenAI create must not run when policy-disabled")

    class TrackingChat:
        completions = TrackingCompletions()

    class TrackingOpenAI:
        def __init__(self, *args, **kwargs):
            constructions.append(dict(kwargs))
            self.chat = TrackingChat()
            self._base = kwargs.get("base_url")

    import sys

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=TrackingOpenAI))

    reply, err = UnifiedElysiaSystem.chat_with_llm(inst, "ping")
    # OpenAI direct (no base_url) must not construct; OpenRouter may construct with base_url.
    openai_only = [c for c in constructions if not c.get("base_url")]
    assert openai_only == [], f"policy-disabled OpenAI must not construct: {openai_only}"
    assert reply == "or-ok"
    assert not err
    _assert_no_secret_leak(reply, err)
