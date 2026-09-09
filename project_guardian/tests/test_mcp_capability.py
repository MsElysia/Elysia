"""mcp_capability: chat inference and allowlist wiring (no live MCP server)."""

import json
from pathlib import Path
import pytest

from project_guardian.mcp_capability import infer_elysia_mcp_tool_chat_input, run_builtin_mcp_tool


def test_infer_mcp_list():
    out = infer_elysia_mcp_tool_chat_input("mcp list myserver")
    assert out.get("mcp_list_tools") is True
    assert out.get("mcp_server") == "myserver"


def test_infer_mcp_tools_alias():
    out = infer_elysia_mcp_tool_chat_input("MCP tools demo_srv")
    assert out.get("mcp_list_tools") is True
    assert out.get("mcp_server") == "demo_srv"


def test_infer_mcp_json_call():
    raw = json.dumps({"server": "s", "tool": "t", "arguments": {"a": 1}})
    out = infer_elysia_mcp_tool_chat_input(raw)
    assert out.get("mcp_call") == {"server": "s", "tool": "t", "arguments": {"a": 1}}


def test_infer_mcp_json_missing_tool():
    out = infer_elysia_mcp_tool_chat_input(json.dumps({"server": "only"}))
    assert out.get("mcp_parse_error")


def test_run_builtin_without_allowlist(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "project_guardian.mcp_capability._DEFAULT_ALLOWLIST",
        tmp_path / "nope.json",
    )
    g = object()
    r = run_builtin_mcp_tool(g, {"mcp_list_tools": True, "mcp_server": "x"})
    assert r.get("success") is False


def test_run_builtin_list_rejects_unknown_server(tmp_path, monkeypatch):
    allow = tmp_path / "allow.json"
    allow.write_text(
        json.dumps(
            {
                "enabled": True,
                "servers_config": "config/mcp_servers.json",
                "allowed_calls": [{"server": "only_one", "tools": ["*"]}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("project_guardian.mcp_capability._DEFAULT_ALLOWLIST", allow)
    monkeypatch.setattr("project_guardian.mcp_stdio_bridge.mcp_sdk_available", lambda: True)
    g = object()
    r = run_builtin_mcp_tool(g, {"mcp_list_tools": True, "mcp_server": "other"})
    assert r.get("success") is False
    assert "not allowlisted" in (r.get("error") or "").lower()


def test_infer_chat_capability_routes_mcp_tool():
    from project_guardian.capability_execution import infer_chat_capability_input

    entry = {"name": "elysia_mcp_tool", "type": "tool", "description": "MCP"}
    out = infer_chat_capability_input("mcp list fs", entry)
    assert out.get("mcp_list_tools") is True
    assert out.get("mcp_server") == "fs"
