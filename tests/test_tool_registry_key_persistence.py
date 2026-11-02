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


def test_nested_credential_metadata_is_not_saved_or_exported(tmp_path):
    registry = ToolRegistry(str(tmp_path / "registry.json"))
    registry.register_tool(
        name="nested", description="safe", provider="synthetic",
        api_endpoint="https://example.invalid/v1",
        metadata={
            "headers": {"Authorization": SENTINEL, "X-Api-Key": SENTINEL,
                        "Accept": "application/json"},
            "workers": [{"refresh_token": SENTINEL, "latency_ms": 42}],
            "provider": "synthetic",
        },
        rate_limit={"max_requests": 4, "access_token": SENTINEL},
    )
    # The registry may use secrets during this process, but storage never sees them.
    assert registry.get_tool_metadata("nested").metadata["headers"]["Authorization"] == SENTINEL
    saved = (tmp_path / "registry.json").read_text(encoding="utf-8")
    exported = (tmp_path / "export.json")
    registry.export_config(str(exported))
    for content in (saved, exported.read_text(encoding="utf-8")):
        assert SENTINEL not in content
        obj = json.loads(content)["tools"][0]
        assert obj["metadata"]["headers"] == {"Accept": "application/json"}
        assert obj["metadata"]["workers"] == [{"latency_ms": 42}]
        assert obj["metadata"]["provider"] == "synthetic"
        assert obj["rate_limit"] == {"max_requests": 4}


def test_endpoint_userinfo_and_query_are_removed_before_persistence(tmp_path):
    endpoint = f"https://operator:{SENTINEL}@example.invalid:8443/v1?key={SENTINEL}&mode=fast#token={SENTINEL}"
    registry = ToolRegistry(str(tmp_path / "registry.json"))
    registry.register_tool(
        name="url", description="synthetic", provider="synthetic", api_endpoint=endpoint,
        metadata={"docs_url": f"https://example.invalid/info?token={SENTINEL}",
                  "locale": "en-US"},
    )
    assert registry.get_tool_metadata("url").api_endpoint == endpoint
    saved = (tmp_path / "registry.json").read_text(encoding="utf-8")
    assert SENTINEL not in saved
    tool = json.loads(saved)["tools"][0]
    assert tool["api_endpoint"] == "https://example.invalid:8443/v1"
    assert tool["metadata"]["docs_url"] == "https://example.invalid/info"
    assert tool["metadata"]["locale"] == "en-US"
    reloaded = ToolRegistry(str(tmp_path / "registry.json"))
    assert reloaded.get_tool_metadata("url").api_endpoint == "https://example.invalid:8443/v1"


def test_legacy_nested_plaintext_is_not_reexported(tmp_path):
    raw = {"tools": [{
        "name": "historical", "description": "synthetic", "provider": "test",
        "api_endpoint": f"https://user:{SENTINEL}@example.invalid/v1?k={SENTINEL}",
        "metadata": {"nested": [{"client_secret": SENTINEL, "nonsecret": 7}]},
    }]}
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    registry = ToolRegistry(str(path))
    assert registry.get_tool_metadata("historical").metadata["nested"][0]["client_secret"] == SENTINEL
    export = registry.export_config(str(tmp_path / "export.json"))
    assert SENTINEL not in (tmp_path / "export.json").read_text(encoding="utf-8")
    registry.save()
    assert SENTINEL not in path.read_text(encoding="utf-8")


def test_environment_reference_and_local_endpoint_remain_usable(tmp_path, monkeypatch):
    monkeypatch.setenv("ELYSIA_TEST_FAKE_KEY", SENTINEL)
    registry = ToolRegistry(str(tmp_path / "registry.json"))
    registry.register_tool(
        name="local", description="synthetic", provider="builtin",
        api_endpoint="local://llm", api_key_env="ELYSIA_TEST_FAKE_KEY",
        metadata={"api_key_env": "ELYSIA_TEST_FAKE_KEY", "enabled": False},
    )
    loaded = ToolRegistry(str(tmp_path / "registry.json"))
    assert loaded.get_tool_metadata("local").api_endpoint == "local://llm"
    assert loaded.get_tool_metadata("local").metadata["api_key_env"] == "ELYSIA_TEST_FAKE_KEY"
    assert loaded.get_tool("local").api_key == SENTINEL
    assert SENTINEL not in (tmp_path / "registry.json").read_text(encoding="utf-8")


def test_deeply_nested_metadata_refuses_unsafe_save(tmp_path):
    nested = {"ordinary": "safe"}
    for _ in range(27):
        nested = {"nested": nested}
    registry = ToolRegistry(str(tmp_path / "registry.json"))
    try:
        registry.register_tool(
            name="deep", description="synthetic", provider="synthetic",
            api_endpoint="local://llm", metadata=nested,
        )
    except ValueError as exc:
        assert "nesting" in str(exc)
    else:
        raise AssertionError("Nested metadata was written without complete screening")
    assert not (tmp_path / "registry.json").exists()
