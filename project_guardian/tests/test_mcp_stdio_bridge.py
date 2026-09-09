"""mcp_stdio_bridge: config loading (MCP SDK optional for list/call integration)."""

import json
from pathlib import Path

import pytest

from project_guardian.mcp_stdio_bridge import load_mcp_server_from_config


def test_load_mcp_server_from_config(tmp_path: Path):
    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        json.dumps(
            {
                "servers": {
                    "demo": {"command": "echo", "args": ["hi"], "env": {"FOO": "bar"}},
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    cmd, args, env = load_mcp_server_from_config(cfg, "demo")
    assert cmd == "echo"
    assert args == ["hi"]
    assert env == {"FOO": "bar"}


def test_load_mcp_server_unknown_raises(tmp_path: Path):
    cfg = tmp_path / "mcp.json"
    cfg.write_text(json.dumps({"servers": {}}), encoding="utf-8")
    with pytest.raises(KeyError):
        load_mcp_server_from_config(cfg, "nope")


def test_load_mcp_server_empty_env_is_none(tmp_path: Path):
    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        json.dumps({"servers": {"x": {"command": "python", "args": ["-V"], "env": {}}}}),
        encoding="utf-8",
    )
    _, _, env = load_mcp_server_from_config(cfg, "x")
    assert env is None
