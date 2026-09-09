"""Tests for tool discovery and provider adapters (ai_tool_registry_engine)."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

from project_guardian.ai_tool_registry_engine import (
    HuggingFaceInferenceToolAdapter,
    OpenRouterChatToolAdapter,
    ToolMetadata,
    ToolRegistry,
    discover_huggingface_hub_models,
    discover_openrouter_models,
)


class _FakeHttpResponse:
    def __init__(self, body: bytes, *, status: int = 200, headers=None):
        self._body = body
        self.status = status
        self.headers = headers or {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._body


def test_discover_huggingface_hub_models_parses_response():
    payload = [
        {
            "modelId": "org/Some-Model",
            "pipeline_tag": "text-generation",
            "likes": 10,
            "downloads": 1000,
        }
    ]
    fake = _FakeHttpResponse(json.dumps(payload).encode("utf-8"))

    with patch(
        "project_guardian.ai_tool_registry_engine.urllib.request.urlopen",
        return_value=fake,
    ):
        out = discover_huggingface_hub_models(limit=5, search="llama")

    assert len(out) == 1
    assert out[0]["provider"] == "huggingface"
    assert out[0]["model_id"] == "org/Some-Model"
    assert out[0]["name"] == "hf_org__Some-Model"
    assert "text-generation" in out[0]["description"]
    assert "api-inference.huggingface.co/models/org/Some-Model" in out[0]["api_endpoint"]


def test_discover_huggingface_uses_id_when_no_modelId():
    payload = [{"id": "legacy/id", "pipeline_tag": None}]
    fake = _FakeHttpResponse(json.dumps(payload).encode("utf-8"))

    with patch(
        "project_guardian.ai_tool_registry_engine.urllib.request.urlopen",
        return_value=fake,
    ):
        out = discover_huggingface_hub_models(limit=3)

    assert len(out) == 1
    assert out[0]["model_id"] == "legacy/id"


def test_tool_registry_discover_tools_huggingface(tmp_path):
    payload = [{"modelId": "toy/model", "likes": 1, "downloads": 2}]
    fake = _FakeHttpResponse(json.dumps(payload).encode("utf-8"))

    reg = ToolRegistry(storage_path=str(tmp_path / "tool_registry.json"))
    with patch(
        "project_guardian.ai_tool_registry_engine.urllib.request.urlopen",
        return_value=fake,
    ):
        found = reg.discover_tools(["huggingface"], limit_per_source=10)
    assert len(found) == 1
    assert found[0]["name"] == "hf_toy__model"


def test_discover_openrouter_models_parses_response():
    payload = {
        "data": [
            {
                "id": "openai/gpt-4",
                "name": "GPT-4",
                "description": "General-purpose model",
                "context_length": 8192,
                "architecture": {"modality": "text->text"},
            }
        ]
    }
    fake = _FakeHttpResponse(json.dumps(payload).encode("utf-8"))

    with patch(
        "project_guardian.ai_tool_registry_engine.urllib.request.urlopen",
        return_value=fake,
    ):
        out = discover_openrouter_models(limit=5, search="gpt-4")

    assert len(out) == 1
    assert out[0]["provider"] == "openrouter"
    assert out[0]["model_id"] == "openai/gpt-4"
    assert out[0]["api_endpoint"] == "https://openrouter.ai/api/v1/chat/completions"
    assert out[0]["api_key_env"] == "OPENROUTER_API_KEY"


def test_tool_registry_discover_tools_openrouter(tmp_path):
    payload = {"data": [{"id": "anthropic/claude-3.5-haiku", "name": "Claude 3.5 Haiku"}]}
    fake = _FakeHttpResponse(json.dumps(payload).encode("utf-8"))

    reg = ToolRegistry(storage_path=str(tmp_path / "tool_registry2.json"))
    with patch(
        "project_guardian.ai_tool_registry_engine.urllib.request.urlopen",
        return_value=fake,
    ):
        found = reg.discover_tools(["openrouter"], limit_per_source=5)

    assert len(found) == 1
    assert found[0]["name"] == "openrouter_anthropic__claude-3_5-haiku"


def test_create_adapter_uses_huggingface_inference_adapter(tmp_path):
    reg = ToolRegistry(storage_path=str(tmp_path / "tool_registry3.json"))

    reg.register_tool(
        name="hf_tool",
        description="Test HF tool",
        provider="huggingface",
        api_endpoint="https://api-inference.huggingface.co/models/test/model",
        api_key_env="HF_TOKEN",
    )

    assert isinstance(reg.get_tool("hf_tool"), HuggingFaceInferenceToolAdapter)


def test_huggingface_inference_adapter_posts_json():
    captured = {}

    def _fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["method"] = request.get_method()
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeHttpResponse(
            json.dumps({"generated_text": "hello world"}).encode("utf-8")
        )

    adapter = HuggingFaceInferenceToolAdapter(
        ToolMetadata(
            name="hf_test",
            description="HF inference test",
            provider="huggingface",
            api_endpoint="https://api-inference.huggingface.co/models/org/model",
            api_key="hf_test_token",
        )
    )

    with patch(
        "project_guardian.ai_tool_registry_engine.urllib.request.urlopen",
        side_effect=_fake_urlopen,
    ):
        result = adapter.call(
            "predict",
            inputs="hello",
            parameters={"max_new_tokens": 5},
            timeout_sec=4,
        )

    assert result["success"] is True
    assert result["data"]["generated_text"] == "hello world"
    assert captured["url"] == "https://api-inference.huggingface.co/models/org/model"
    assert captured["method"] == "POST"
    assert captured["timeout"] == 4.0
    assert captured["headers"]["Authorization"] == "Bearer hf_test_token"
    assert captured["payload"]["inputs"] == "hello"


def test_create_adapter_uses_openrouter_chat_adapter(tmp_path):
    reg = ToolRegistry(storage_path=str(tmp_path / "tool_registry_or.json"))
    reg.register_tool(
        name="or_tool",
        description="Test OR tool",
        provider="openrouter",
        api_endpoint="https://openrouter.ai/api/v1/chat/completions",
        api_key_env="OPENROUTER_API_KEY",
        metadata={"model_id": "openai/gpt-4o-mini"},
    )
    assert isinstance(reg.get_tool("or_tool"), OpenRouterChatToolAdapter)


def test_register_from_discovery_item(tmp_path):
    reg = ToolRegistry(storage_path=str(tmp_path / "tool_registry_rd.json"))
    item = {
        "name": "hf_unit__x",
        "description": "Unit model",
        "provider": "huggingface",
        "api_endpoint": "https://api-inference.huggingface.co/models/unit/x",
        "model_id": "unit/x",
        "api_key_env": "HF_TOKEN",
    }
    nm = reg.register_from_discovery_item(item)
    assert nm == "hf_unit__x"
    meta = reg.get_tool_metadata("hf_unit__x")
    assert meta is not None
    assert meta.metadata.get("model_id") == "unit/x"
    assert "llm" in (meta.capabilities or [])


def test_openrouter_chat_adapter_posts_json():
    captured = {}

    def _fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        body = {
            "choices": [{"message": {"content": "hi from or"}}],
        }
        return _FakeHttpResponse(json.dumps(body).encode("utf-8"))

    adapter = OpenRouterChatToolAdapter(
        ToolMetadata(
            name="or_test",
            description="OR test",
            provider="openrouter",
            api_endpoint="https://openrouter.ai/api/v1/chat/completions",
            api_key="sk-or-test",
            metadata={"model_id": "openai/gpt-4o-mini"},
        )
    )
    with patch(
        "project_guardian.ai_tool_registry_engine.urllib.request.urlopen",
        side_effect=_fake_urlopen,
    ):
        out = adapter.call("chat", prompt="hello")
    assert out["success"] is True
    assert out["data"]["text"] == "hi from or"
    assert captured["payload"]["model"] == "openai/gpt-4o-mini"


def test_call_tool_invokes_outcome_logger(tmp_path):
    reg = ToolRegistry(storage_path=str(tmp_path / "tool_registry_out.json"))
    reg.register_tool(
        name="hf_log_tool",
        description="HF log",
        provider="huggingface",
        api_endpoint="https://api-inference.huggingface.co/models/m",
        api_key="tok",
    )
    with (
        patch(
            "project_guardian.ai_tool_registry_engine.urllib.request.urlopen",
            return_value=_FakeHttpResponse(
                json.dumps({"ok": True}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            ),
        ),
        patch("project_guardian.capability_registry.log_tool_registry_call_outcome") as log_fn,
    ):
        reg.call_tool("hf_log_tool", "call", inputs="x")
    assert log_fn.called
    kwargs = log_fn.call_args.kwargs
    assert kwargs["tool_name"] == "hf_log_tool"
    assert kwargs["success"] is True


def test_builtin_tool_metadata_uses_capability_state(tmp_path):
    reg = ToolRegistry(storage_path=str(tmp_path / "tool_registry_builtin.json"))
    reg.ensure_minimal_builtin_tools()

    web = reg.get_tool_metadata("elysia_builtin_web")
    exec_tool = reg.get_tool_metadata("elysia_builtin_exec")
    bounded = reg.get_tool_metadata("elysia_bounded_browser")

    assert web is not None
    assert web.metadata.get("builtin") is True
    assert web.metadata.get("capability_state") == "operational"
    assert "builtin_stub" not in web.metadata

    assert exec_tool is not None
    assert exec_tool.metadata.get("capability_state") == "gated"
    assert exec_tool.metadata.get("requires_approval") is True

    assert bounded is not None
    assert bounded.metadata.get("capability_state") == "fallback_operational"
    assert bounded.metadata.get("preferred_dependency") == "playwright"
    assert bounded.metadata.get("fallback_backend") == "urllib_static"


def test_core_metacoder_adapter_generates_non_stub_code():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "core_modules" / "elysia_core_comprehensive" / "ai_tool_registry.py"
    spec = importlib.util.spec_from_file_location("core_ai_tool_registry_for_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    registry = module.ToolRegistry()
    registry.add_tool(
        "external_api",
        {
            "provider": "custom",
            "capabilities": ["fetch"],
            "api_endpoint": "https://example.com/api",
        },
    )
    code = module.MetaCoderAdapter(registry).generate_adapter("external_api", "POST JSON docs")

    assert "TODO" not in code
    assert "\n        pass" not in code
    tool = registry.tools["external_api"]
    assert tool["adapter_status"] == "generic_http_generated"
    assert tool["adapter_operational"] is True
    assert tool["adapter_class"] == "external_apiAdapter"

    registry.ensure_minimal_builtin_tools()
    local_code = module.MetaCoderAdapter(registry).generate_adapter("elysia_builtin_web", "local docs")
    assert "local_bridge_required" in local_code
    assert registry.tools["elysia_builtin_web"]["adapter_operational"] is False
    assert registry.tools["elysia_builtin_web"]["capability_state"] == "operational"
    assert "builtin_stub" not in registry.tools["elysia_builtin_web"]
