"""Regression: legacy AI-tool registry must not persist direct API keys.

No provider requests, external network calls, or operational data are used.
"""
import json

from project_guardian.ai_tool_registry_engine import ToolMetadata, ToolRegistry

SENTINEL = "not-a-real-secret-regression-sentinel"


def _register(registry, *, key=SENTINEL, env=None):
    registry.register_tool(
        name="example",
        description="synthetic provider",
        provider="example",
        api_endpoint="https://example.invalid/api",
        api_key=key,
        api_key_env=env,
        capabilities=["synthetic"],
        cost_per_request=0.01,
    )


def test_public_metadata_omits_direct_key():
    meta = ToolMetadata(
        name="example",
        description="synthetic",
        provider="example",
        api_endpoint="https://example.invalid/api",
        api_key=SENTINEL,
        api_key_env="ELYSIA_TEST_FAKE_KEY",
    )
    exported = meta.to_dict()
    assert "api_key" not in exported
    assert SENTINEL not in json.dumps(exported)
    assert exported["api_key_env"] == "ELYSIA_TEST_FAKE_KEY"
    assert meta.api_key == SENTINEL  # runtime credential remains available


def test_registry_save_and_export_do_not_write_direct_keys(tmp_path):
    registry = ToolRegistry(str(tmp_path / "registry.json"))
    _register(registry)
    assert registry.get_tool("example").api_key == SENTINEL
    assert SENTINEL not in (tmp_path / "registry.json").read_text(encoding="utf-8")
    destination = registry.export_config(str(tmp_path / "export.json"))
    assert SENTINEL not in open(destination, encoding="utf-8").read()
    loaded = ToolRegistry(str(tmp_path / "registry.json"))
    assert loaded.get_tool_metadata("example").api_key is None
    assert loaded.get_tool_metadata("example").cost_per_request == 0.01


def test_env_key_survives_reload_without_key_leak(monkeypatch, tmp_path):
    monkeypatch.setenv("ELYSIA_TEST_FAKE_KEY", SENTINEL)
    registry = ToolRegistry(str(tmp_path / "registry.json"))
    _register(registry, key=None, env="ELYSIA_TEST_FAKE_KEY")
    assert SENTINEL not in (tmp_path / "registry.json").read_text(encoding="utf-8")
    loaded = ToolRegistry(str(tmp_path / "registry.json"))
    assert loaded.get_tool("example").api_key == SENTINEL
    assert loaded.get_tool_metadata("example").api_key is None


def test_legacy_plaintext_load_is_not_reexported(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({"tools": [{
        "name": "legacy",
        "description": "historical synthetic data",
        "provider": "example",
        "api_endpoint": "https://example.invalid/api",
        "api_key": SENTINEL,
    }]}), encoding="utf-8")
    registry = ToolRegistry(str(path))
    assert registry.get_tool_metadata("legacy").api_key == SENTINEL
    assert SENTINEL not in open(registry.export_config(str(tmp_path / "export.json")), encoding="utf-8").read()
    registry.save()
    assert SENTINEL not in path.read_text(encoding="utf-8")
