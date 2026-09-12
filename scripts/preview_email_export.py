#!/usr/bin/env python3
"""
Preview local .eml email exports for memory candidate staging.

Preview-only: does not write memory candidates or call models/APIs.

Example:
  python scripts/preview_email_export.py --dest-dir <path> --input <file-or-folder>
  python scripts/preview_email_export.py --dest-dir <path> --input <folder> --recursive
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

from project_guardian.local_ingestion.email_export_ingest import (  # noqa: E402
    EmailExportIngestError,
    preview_email_export,
)
from project_guardian.local_ingestion.transcription_ingest import DEFAULT_MAX_FILE_MB  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview local .eml email exports (no import, no network).",
    )
    parser.add_argument(
        "--dest-dir",
        type=Path,
        required=True,
        help="Destination workspace for preview session artifacts",
    )
    parser.add_argument(
        "--input",
        type=Path,
        action="append",
        required=True,
        dest="inputs",
        help="Explicit file or folder path (repeatable)",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Scan subdirectories when an input is a folder",
    )
    parser.add_argument(
        "--max-file-mb",
        type=float,
        default=DEFAULT_MAX_FILE_MB,
        help=f"Maximum file size in megabytes (default: {DEFAULT_MAX_FILE_MB})",
    )
    args = parser.parse_args()

    try:
        report = preview_email_export(
            dest_dir=args.dest_dir,
            input_paths=args.inputs,
            recursive=args.recursive,
            max_file_mb=args.max_file_mb,
        )
    except EmailExportIngestError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1

    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
