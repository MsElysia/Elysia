#!/usr/bin/env python3
"""
Write approved memory export records into a local JSONL memory store.

Operator-run only. Does not write live runtime memory or vector DB.
Dry-run is the default; pass ``--apply`` to write the store file.

Examples:
  python scripts/write_approved_memory_store.py --dest-dir ./data/phone_transcriptions
  python scripts/write_approved_memory_store.py --dest-dir ./data/phone_transcriptions --apply
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

from project_guardian.local_ingestion.approved_memory_store import (  # noqa: E402
    ApprovedMemoryStoreError,
    write_approved_memory_store,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write approved export records to a local memory store JSONL.",
    )
    parser.add_argument(
        "--dest-dir",
        type=Path,
        default=None,
        help="Destination folder used during transcription ingestion",
    )
    parser.add_argument(
        "--approved-export",
        type=Path,
        default=None,
        help="Approved export JSONL (default: <dest-dir>/memory_candidates/approved_memory_export.jsonl)",
    )
    parser.add_argument(
        "--memory-store",
        type=Path,
        default=None,
        help=f"Output memory store JSONL (default: <dest-dir>/memory_store/approved_memory_store.jsonl)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the memory store file. Without this flag, only report planned writes.",
    )
    args = parser.parse_args()

    if args.dest_dir is None and args.approved_export is None:
        print(json.dumps({"error": "Provide --dest-dir or --approved-export."}))
        return 1

    try:
        report = write_approved_memory_store(
            dest_dir=args.dest_dir,
            approved_export_path=args.approved_export,
            memory_store_path=args.memory_store,
            apply=args.apply,
        )
    except ApprovedMemoryStoreError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1

    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
