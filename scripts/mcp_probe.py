#!/usr/bin/env python3
"""
Probe an MCP server over stdio (official mcp Python SDK).

  pip install -r requirements-optional.txt   # includes mcp

  python scripts/mcp_probe.py --config config/mcp_servers.example.json --server filesystem_readme --list-tools
  python scripts/mcp_probe.py --config config/mcp_servers.example.json --server filesystem_readme --call read_file --arguments-json "{\\\"path\\\": \\\"README.md\\\"}"

Or pass command line directly:

  python scripts/mcp_probe.py --command npx --arg -y --arg @modelcontextprotocol/server-filesystem --arg C:\\\\temp --list-tools
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="MCP stdio probe (list tools / call tool)")
    ap.add_argument("--config", type=Path, help="JSON with servers.{name}.{command,args,env}")
    ap.add_argument("--server", type=str, help="Server name inside config")
    ap.add_argument("--command", type=str, help="stdio server command (if not using --config)")
    ap.add_argument("--arg", action="append", default=[], dest="args", help="One server arg (repeatable)")
    ap.add_argument("--list-tools", action="store_true", help="List tools and exit")
    ap.add_argument("--call", type=str, metavar="TOOL", help="Call a tool by name")
    ap.add_argument(
        "--arguments-json",
        type=str,
        default="{}",
        help="JSON object for tool arguments (default: {})",
    )

    args = ap.parse_args()
    from project_guardian.mcp_stdio_bridge import (
        call_tool_stdio,
        load_mcp_server_from_config,
        list_tools_stdio,
        mcp_sdk_available,
    )

    if not mcp_sdk_available():
        print("The 'mcp' package is not installed. Run:", file=sys.stderr)
        print("  pip install \"mcp>=1.26.0,<2\"", file=sys.stderr)
        return 1

    cmd: str
    sargs: List[str]
    env: Optional[Dict[str, str]] = None

    if args.config:
        if not args.server:
            ap.error("--server is required when using --config")
        cfg = args.config
        if not cfg.is_file():
            print(f"Config not found: {cfg}", file=sys.stderr)
            return 1
        try:
            cmd, sargs, env = load_mcp_server_from_config(cfg, args.server)
        except (KeyError, ValueError, OSError) as e:
            print(e, file=sys.stderr)
            return 1
    elif args.command:
        cmd = args.command
        sargs = list(args.args or [])
    else:
        ap.error("Provide --config and --server, or --command with --arg")

    if args.list_tools:
        tools = list_tools_stdio(cmd, sargs, env=env)
        print(json.dumps(tools, indent=2, ensure_ascii=False))
        return 0

    if args.call:
        try:
            arguments = json.loads(args.arguments_json or "{}")
        except json.JSONDecodeError as e:
            print(f"Invalid --arguments-json: {e}", file=sys.stderr)
            return 1
        if not isinstance(arguments, dict):
            print("--arguments-json must be a JSON object", file=sys.stderr)
            return 1
        out = call_tool_stdio(cmd, sargs, args.call, arguments, env=env)
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
        return 0 if not out.get("isError") else 2

    ap.error("Specify --list-tools and/or --call")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
