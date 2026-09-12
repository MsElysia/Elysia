#!/usr/bin/env python3
"""
Unified local memory import preview and apply.

Routes to the existing safe transcription, ChatGPT export, and email export
importers. Preview-only by default; apply stages pending candidates only with
explicit --apply.

Examples:
  python scripts/memory_import.py preview --dest-dir <path> --input <file-or-folder>
  python scripts/memory_import.py preview --dest-dir <path> --source-type email_export --input <path>
  python scripts/memory_import.py apply --session-json <path>/import_session_preview.json
  python scripts/memory_import.py apply --session-json <path>/email_export_preview.json --apply
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

from project_guardian.local_ingestion.transcription_ingest import DEFAULT_MAX_FILE_MB  # noqa: E402
from project_guardian.local_ingestion.unified_memory_import import (  # noqa: E402
    UnifiedMemoryImportError,
    format_apply_operator_summary,
    format_preview_operator_summary,
    unified_apply_memory_import,
    unified_preview_memory_import,
)


def _build_preview_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "preview",
        help="Preview a local memory import session (no import, no models).",
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
        dest="inputs",
        required=True,
        help="Explicit file or folder path (repeatable)",
    )
    parser.add_argument(
        "--source-type",
        default=None,
        help="Optional explicit source type: transcription, chatgpt_export, email_export",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively scan folder inputs",
    )
    parser.add_argument(
        "--max-file-mb",
        type=float,
        default=DEFAULT_MAX_FILE_MB,
        help=f"Maximum per-file size in MB (default: {DEFAULT_MAX_FILE_MB})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON summary only",
    )


def _build_apply_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "apply",
        help="Apply a preview session JSON to stage memory candidates (dry-run default).",
    )
    parser.add_argument(
        "--session-json",
        type=Path,
        required=True,
        help="Path to a preview session JSON from preview step",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Stage pending memory candidates in the review queue",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON summary only",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unified local memory import preview/apply (local files only).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _build_preview_parser(subparsers)
    _build_apply_parser(subparsers)
    args = parser.parse_args()

    try:
        if args.command == "preview":
            summary = unified_preview_memory_import(
                dest_dir=args.dest_dir,
                input_paths=args.inputs,
                source_type=args.source_type,
                recursive=args.recursive,
                max_file_mb=args.max_file_mb,
            )
            if args.json:
                print(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False))
            else:
                print(format_preview_operator_summary(summary))
            return 0

        summary = unified_apply_memory_import(
            session_json=args.session_json,
            apply=args.apply,
        )
        if args.json:
            print(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(format_apply_operator_summary(summary))
        return 0
    except UnifiedMemoryImportError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
