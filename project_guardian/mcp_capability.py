# project_guardian/mcp_capability.py
"""
Allowlisted MCP stdio execution for the ``elysia_mcp_tool`` chat capability / builtin tool path.

Configuration:
  - ``config/mcp_capability_allowlist.json`` (copy from ``mcp_capability_allowlist.example.json``)
  - ``config/mcp_servers.json`` (copy from ``mcp_servers.example.json``) — path relative to repo root
    or override via ``servers_config`` in the allowlist file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_ALLOWLIST = _REPO_ROOT / "config" / "mcp_capability_allowlist.json"


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            out = json.load(f)
        return out if isinstance(out, dict) else None
    except Exception as e:
        logger.debug("[mcp_capability] read %s: %s", path, e)
        return None


def is_mcp_stdio_capability_enabled() -> bool:
    if not _DEFAULT_ALLOWLIST.is_file():
        return False
    raw = _read_json(_DEFAULT_ALLOWLIST)
    if not raw or not bool(raw.get("enabled")):
        return False
    try:
        from .mcp_stdio_bridge import mcp_sdk_available

        return mcp_sdk_available()
    except Exception:
        return False


def _servers_config_path(allowlist: Dict[str, Any]) -> Path:
    rel = str(allowlist.get("servers_config") or "config/mcp_servers.json").strip()
    p = Path(rel)
    if not p.is_absolute():
        p = (_REPO_ROOT / p).resolve()
    return p


def _allowed_entry(allowlist: Dict[str, Any], server: str) -> Optional[Dict[str, Any]]:
    for row in allowlist.get("allowed_calls") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("server") or "").strip() == server.strip():
            return row
    return None


def _tool_allowed(allowlist: Dict[str, Any], server: str, tool: str) -> bool:
    row = _allowed_entry(allowlist, server)
    if row is None:
        return False
    tools = row.get("tools")
    if not isinstance(tools, list):
        return False
    tl = [str(t).strip() for t in tools if str(t).strip()]
    if "*" in tl:
        return True
    return tool.strip() in tl


def run_builtin_mcp_tool(guardian: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Execute allowlisted MCP list/call; used from ``_builtin_operator_tool_result``."""
    _ = guardian
    allow = _read_json(_DEFAULT_ALLOWLIST)
    if not allow or not bool(allow.get("enabled")):
        return {"success": False, "error": "mcp_capability_allowlist.json missing or enabled=false"}
    try:
        from .mcp_stdio_bridge import call_tool_stdio, list_tools_stdio, load_mcp_server_from_config, mcp_sdk_available

        if not mcp_sdk_available():
            return {"success": False, "error": "mcp package not installed (pip install mcp)"}
    except Exception as e:
        return {"success": False, "error": str(e)}

    cfg_path = _servers_config_path(allow)
    if payload.get("mcp_list_tools"):
        server = str(payload.get("mcp_server") or "").strip()
        if not server:
            return {"success": False, "error": "mcp_server required for list"}
        if _allowed_entry(allow, server) is None:
            return {"success": False, "error": f"server {server!r} not allowlisted"}
        try:
            cmd, args, env = load_mcp_server_from_config(cfg_path, server)
            tools = list_tools_stdio(cmd, args, env=env)
            return {"success": True, "result": {"server": server, "tools": tools}}
        except Exception as e:
            logger.info("[mcp_capability] list_tools failed: %s", e)
            return {"success": False, "error": str(e)[:500]}

    call = payload.get("mcp_call")
    if isinstance(call, dict):
        server = str(call.get("server") or "").strip()
        tool = str(call.get("tool") or "").strip()
        arguments = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
        if not server or not tool:
            return {"success": False, "error": "mcp_call requires server and tool"}
        if not _tool_allowed(allow, server, tool):
            return {"success": False, "error": f"call not allowlisted: {server}/{tool}"}
        try:
            cmd, args, env = load_mcp_server_from_config(cfg_path, server)
            out = call_tool_stdio(cmd, args, tool, dict(arguments or {}), env=env)
            return {"success": not bool(out.get("isError")), "result": out}
        except Exception as e:
            logger.info("[mcp_capability] call_tool failed: %s", e)
            return {"success": False, "error": str(e)[:500]}

    if payload.get("mcp_parse_error"):
        return {
            "success": True,
            "result": {"hint": str(payload.get("mcp_parse_error") or "invalid MCP chat payload")},
        }
    return {"success": False, "error": "expected mcp_list_tools or mcp_call in payload"}


def infer_elysia_mcp_tool_chat_input(user_text: str) -> Dict[str, Any]:
    """Map operator chat text into execute_capability payload for ``elysia_mcp_tool``."""
    text = (user_text or "").strip()
    low = text.lower()
    parts = text.split()
    if len(parts) >= 3 and parts[0].lower() == "mcp" and parts[1].lower() in ("list", "tools"):
        server = " ".join(parts[2:]).strip()
        if not server:
            return {"method": "execute", "mcp_parse_error": "usage: mcp list <server_name>"}
        return {"method": "execute", "mcp_list_tools": True, "mcp_server": server}
    if text.startswith("{") and text.endswith("}"):
        try:
            d = json.loads(text)
        except json.JSONDecodeError as e:
            return {"method": "execute", "mcp_parse_error": f"invalid JSON: {e}"}
        if isinstance(d, dict) and d.get("server") and d.get("tool"):
            return {"method": "execute", "mcp_call": d}
        return {"method": "execute", "mcp_parse_error": "JSON needs string fields server and tool (optional arguments object)"}
    return {
        "method": "execute",
        "mcp_parse_error": "Chat MCP: send `mcp list <server>` or a single JSON object {\"server\":\"...\",\"tool\":\"...\",\"arguments\":{}}",
    }
