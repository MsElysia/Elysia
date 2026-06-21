#!/usr/bin/env python3
"""
Build a local context bundle from approved memory search results.

Does not call any model, embeddings, or live memory systems.

Example:
  python scripts/build_approved_memory_context.py --dest-dir ./data/phone_transcriptions --query "drywall quote"
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

from project_guardian.local_ingestion.approved_memory_context import (  # noqa: E402
    DEFAULT_MAX_CHARS,
    ApprovedMemoryContextError,
    build_approved_memory_context,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build approved memory context bundle (no model calls).",
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
    parser.add_argument(
        "--query",
        required=True,
        help="Search query used to select approved memories",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (default: <dest-dir>/memory_context/)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of search hits to include (default: 5)",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=DEFAULT_MAX_CHARS,
        help=f"Maximum total characters for included memory text (default: {DEFAULT_MAX_CHARS})",
    )
    parser.add_argument(
        "--include-full-text",
        action="store_true",
        help="Include full memory text instead of snippets (still respects --max-chars)",
    )
    args = parser.parse_args()

    if args.dest_dir is None and args.memory_store is None:
        print(json.dumps({"error": "Provide --dest-dir or --memory-store."}))
        return 1

    try:
        report = build_approved_memory_context(
            query=args.query,
            dest_dir=args.dest_dir,
            memory_store_path=args.memory_store,
            output_dir=args.output_dir,
            limit=args.limit,
            max_chars=args.max_chars,
            include_full_text=args.include_full_text,
        )
    except ApprovedMemoryContextError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1

    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
