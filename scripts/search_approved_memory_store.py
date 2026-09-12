#!/usr/bin/env python3
"""
Search and recall operator-approved memories from the local JSONL store.

Read-only. No live memory, vector DB, embeddings, or model calls.

Examples:
  python scripts/search_approved_memory_store.py --dest-dir ./data/phone_transcriptions search "drywall quote"
  python scripts/search_approved_memory_store.py --dest-dir ./data/phone_transcriptions show <memory_id>
  python scripts/search_approved_memory_store.py --dest-dir ./data/phone_transcriptions list --limit 10
  python scripts/search_approved_memory_store.py --dest-dir ./data/phone_transcriptions stats
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from project_guardian.local_ingestion.approved_memory_search import (  # noqa: E402
    ApprovedMemorySearchError,
    list_recent_memories,
    load_memory_store,
    memory_store_stats,
    resolve_memory_store_path,
    search_memory_store,
    show_memory_record,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search approved local memory store (read-only).",
    )
    parser.add_argument(
        "--dest-dir",
        type=Path,
        default=None,
        help="Destination folder used during transcription ingestion",
    )
    parser.add_argument(
        "--memory-store",
        type=Path,
        default=None,
        help="Direct path to approved_memory_store.jsonl",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Search memories by text")
    search_parser.add_argument("query", help="Search query (multiple terms supported)")
    search_parser.add_argument("--limit", type=int, default=None)

    show_parser = subparsers.add_parser("show", help="Show one memory by memory_id")
    show_parser.add_argument("memory_id", help="Memory ID to display")

    list_parser = subparsers.add_parser("list", help="List recent memories")
    list_parser.add_argument("--limit", type=int, default=10)

    subparsers.add_parser("stats", help="Show basic memory store statistics")

    args = parser.parse_args()

    if args.dest_dir is None and args.memory_store is None:
        print(json.dumps({"error": "Provide --dest-dir or --memory-store."}))
        return 1

    try:
        store_path = resolve_memory_store_path(
            dest_dir=args.dest_dir,
            memory_store_path=args.memory_store,
        )
        records = load_memory_store(store_path)

        if args.command == "search":
            report = search_memory_store(records, args.query, limit=args.limit)
            report.memory_store_path = str(store_path)
            print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
            return 0
        if args.command == "show":
            record = show_memory_record(records, args.memory_id)
            print(json.dumps(record, indent=2, ensure_ascii=False))
            return 0
        if args.command == "list":
            report = list_recent_memories(records, limit=args.limit)
            report.memory_store_path = str(store_path)
            print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
            return 0
        if args.command == "stats":
            report = memory_store_stats(records)
            report.memory_store_path = str(store_path)
            print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
            return 0

        print(json.dumps({"error": f"Unknown command: {args.command}"}))
        return 1
    except ApprovedMemorySearchError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
