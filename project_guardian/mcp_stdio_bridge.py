# project_guardian/mcp_stdio_bridge.py
"""
Minimal Model Context Protocol (MCP) **stdio client** bridge for Elysia / Guardian.

Uses the official ``mcp`` PyPI package (install from ``requirements-optional.txt``). This module does
not auto-start servers from chat; it provides building blocks and a CLI probe (``scripts/mcp_probe.py``).

**Sync helpers** use ``asyncio.run`` and must not be called from a thread that already has a running
event loop; use the ``*_async`` variants from async code instead.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def mcp_sdk_available() -> bool:
    try:
        import mcp  # noqa: F401

        return True
    except ImportError:
        return False


def load_mcp_server_from_config(config_path: Path, server_name: str) -> Tuple[str, List[str], Optional[Dict[str, str]]]:
    """Load ``command``, ``args``, ``env`` for ``servers.<server_name>`` from a JSON config file."""
    raw = Path(config_path).read_text(encoding="utf-8")
    data = json.loads(raw)
    servers = data.get("servers") or {}
    if server_name not in servers:
        raise KeyError(f"Unknown MCP server {server_name!r}; defined: {list(servers)}")
    row = servers[server_name]
    if not isinstance(row, dict) or "command" not in row:
        raise ValueError(f"Invalid server entry for {server_name!r}")
    cmd = str(row["command"])
    sargs = [str(x) for x in (row.get("args") or [])]
    env_raw = row.get("env")
    env: Optional[Dict[str, str]] = None
    if isinstance(env_raw, dict) and env_raw:
        env = {str(k): str(v) for k, v in env_raw.items()}
    return cmd, sargs, env


def _tool_to_dict(t: Any) -> Dict[str, Any]:
    name = getattr(t, "name", "") or ""
    desc = (getattr(t, "description", None) or "") or ""
    row: Dict[str, Any] = {"name": name, "description": desc[:4000]}
    schema = getattr(t, "inputSchema", None)
    if schema is not None:
        if isinstance(schema, dict):
            row["inputSchema"] = schema
        elif hasattr(schema, "model_dump"):
            try:
                row["inputSchema"] = schema.model_dump()
            except Exception:
                row["inputSchema"] = None
        else:
            try:
                row["inputSchema"] = json.loads(json.dumps(schema, default=str))
            except Exception:
                row["inputSchema"] = None
    return row


async def list_tools_stdio_async(
    command: str,
    args: List[str],
    *,
    env: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(command=command, args=list(args or []), env=env if env else None)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            out = await session.list_tools()
            return [_tool_to_dict(t) for t in (getattr(out, "tools", None) or [])]


async def call_tool_stdio_async(
    command: str,
    args: List[str],
    tool_name: str,
    arguments: Dict[str, Any],
    *,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(command=command, args=list(args or []), env=env if env else None)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool(tool_name, arguments=dict(arguments or {}))
            texts: List[str] = []
            for c in getattr(res, "content", None) or []:
                tx = getattr(c, "text", None)
                if tx:
                    texts.append(str(tx))
            return {
                "isError": bool(getattr(res, "isError", False)),
                "text": "\n".join(texts),
                "structuredContent": getattr(res, "structuredContent", None),
            }


def list_tools_stdio(
    command: str,
    args: List[str],
    *,
    env: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(list_tools_stdio_async(command, args, env=env))
    raise RuntimeError("list_tools_stdio cannot be used inside a running event loop; use list_tools_stdio_async")


def call_tool_stdio(
    command: str,
    args: List[str],
    tool_name: str,
    arguments: Dict[str, Any],
    *,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            call_tool_stdio_async(command, args, tool_name, arguments, env=env)
        )
    raise RuntimeError("call_tool_stdio cannot be used inside a running event loop; use call_tool_stdio_async")
