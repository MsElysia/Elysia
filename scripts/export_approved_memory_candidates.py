#!/usr/bin/env python3
"""
Export operator-approved memory candidates to a local JSONL package.

Does not write live memory. Rebuilds the export file deterministically from the
current approved review state.

Examples:
  python scripts/export_approved_memory_candidates.py --dest-dir ./data/phone_transcriptions
  python scripts/export_approved_memory_candidates.py --dest-dir ./data/phone_transcriptions --output ./out.jsonl
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

from project_guardian.local_ingestion.approved_memory_export import (  # noqa: E402
    ApprovedMemoryExportError,
    export_approved_memory_candidates,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export approved memory candidates (no live memory writes).",
    )
    parser.add_argument(
        "--dest-dir",
        type=Path,
        default=None,
        help="Destination folder used during transcription ingestion",
    )
    parser.add_argument(
        "--queue-path",
        type=Path,
        default=None,
        help="Direct path to review_queue.jsonl",
    )
    parser.add_argument(
        "--decisions-path",
        type=Path,
        default=None,
        help="Direct path to review_decisions.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Export JSONL output path (default: <dest-dir>/memory_candidates/approved_memory_export.jsonl)",
    )
    args = parser.parse_args()

    if args.dest_dir is None and args.queue_path is None:
        print(json.dumps({"error": "Provide --dest-dir or --queue-path."}))
        return 1

    try:
        report = export_approved_memory_candidates(
            dest_dir=args.dest_dir,
            queue_path=args.queue_path,
            decisions_path=args.decisions_path,
            output_path=args.output,
        )
    except ApprovedMemoryExportError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1

    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
