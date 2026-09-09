#!/usr/bin/env python3
"""
Discover Hugging Face and/or OpenRouter models and register the first N into ToolRegistry.

Usage:
  python scripts/register_discovered_capabilities.py --source huggingface --limit 2
  python scripts/register_discovered_capabilities.py --source openrouter --limit 1 --search llama
  python scripts/register_discovered_capabilities.py --dry-run --source huggingface --limit 5

Requires API tokens for inference-backed calls after registration (HF_TOKEN, OPENROUTER_API_KEY).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Register discovered HF/OpenRouter tools into ToolRegistry")
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        metavar="SRC",
        help="huggingface and/or openrouter (repeatable). Default: huggingface",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Max rows to fetch per source (passed to discover_tools)",
    )
    parser.add_argument(
        "--max-register",
        type=int,
        default=3,
        help="Max tools to register total (after discovery)",
    )
    parser.add_argument("--search", type=str, default=None, help="Search string for discovery APIs")
    parser.add_argument("--registry-path", type=Path, default=None, help="Path to tool_registry.json")
    parser.add_argument("--dry-run", action="store_true", help="List discoveries only")
    args = parser.parse_args()

    sources = args.sources or ["huggingface"]
    from project_guardian.ai_tool_registry_engine import ToolRegistry

    reg = ToolRegistry(storage_path=str(args.registry_path or (PROJECT_ROOT / "data" / "tool_registry.json")))
    items = reg.discover_tools(sources, limit_per_source=max(1, args.limit), search=args.search)
    if not items:
        print("No items discovered (check network, tokens, or search).")
        return 2
    cap = max(1, int(args.max_register))
    print(f"Discovered {len(items)} item(s); will register up to {cap} (dry_run={args.dry_run}).\n")
    n = 0
    for it in items:
        if n >= cap:
            break
        prov = str(it.get("provider") or "")
        if args.dry_run:
            print(f"  [dry-run] {it.get('name')} ({prov})")
            n += 1
            continue
        try:
            nm = reg.register_from_discovery_item(it)
            print(f"  [registered] {nm}")
            n += 1
        except Exception as e:
            print(f"  [skip] {it.get('name')}: {e}")
    if args.dry_run:
        print("\nDry-run complete (no files written).")
    else:
        print(f"\nDone. Registry path: {reg.storage_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
