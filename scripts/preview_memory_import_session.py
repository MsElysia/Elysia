#!/usr/bin/env python3
"""
Preview a memory import session from explicit file or folder paths.

Preview-only: does not import files, call models, or write live memory.

Example:
  python scripts/preview_memory_import_session.py --dest-dir ./data/phone_transcriptions --input ./notes.txt
  python scripts/preview_memory_import_session.py --dest-dir ./data/phone_transcriptions --input ./folder --recursive
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

from project_guardian.local_ingestion.import_session_preview import (  # noqa: E402
    ImportSessionPreviewError,
    preview_memory_import_session,
)
from project_guardian.local_ingestion.transcription_ingest import DEFAULT_MAX_FILE_MB  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview a memory import session from explicit paths (no import).",
    )
    parser.add_argument(
        "--dest-dir",
        type=Path,
        required=True,
        help="Destination workspace for import session artifacts",
    )
    parser.add_argument(
        "--input",
        type=Path,
        action="append",
        dest="inputs",
        required=True,
        help="Explicit file or folder path (repeatable)",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively scan folder inputs",
    )
    parser.add_argument(
        "--session-dir",
        type=Path,
        default=None,
        help="Optional explicit session output directory",
    )
    parser.add_argument(
        "--max-file-mb",
        type=float,
        default=DEFAULT_MAX_FILE_MB,
        help=f"Maximum per-file size in MB (default: {DEFAULT_MAX_FILE_MB})",
    )
    args = parser.parse_args()

    if not args.inputs:
        print(json.dumps({"error": "Provide at least one --input path."}))
        return 1

    try:
        report = preview_memory_import_session(
            dest_dir=args.dest_dir,
            input_paths=args.inputs,
            recursive=args.recursive,
            session_dir=args.session_dir,
            max_file_mb=args.max_file_mb,
        )
    except ImportSessionPreviewError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1

    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
