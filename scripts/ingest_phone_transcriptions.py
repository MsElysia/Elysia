#!/usr/bin/env python3
"""
Import phone voice-to-text / transcription files into normalized local storage.

Operator-run only. Does not modify source files. Dry-run is the default; pass
``--apply`` to write normalized text, metadata sidecars, and a manifest JSONL.

Examples:
  python scripts/ingest_phone_transcriptions.py --source-dir ~/Downloads/voice-notes
  python scripts/ingest_phone_transcriptions.py --source-dir ./inbox --dest-dir ./data/phone_transcriptions --apply
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

from project_guardian.local_ingestion.transcription_ingest import (  # noqa: E402
    DEFAULT_MAX_FILE_MB,
    default_dest_dir,
    ingest_transcriptions,
)


def _print_human_summary(report_dict: dict) -> None:
    mode = "APPLY" if report_dict.get("apply") else "DRY-RUN"
    print(f"Phone transcription ingestion ({mode})")
    print(f"  source: {report_dict['source_dir']}")
    print(f"  dest:   {report_dict['dest_dir']}")
    print(
        "  scanned={scanned} ingested={ingested} duplicates={duplicates} skipped={skipped}".format(
            **report_dict
        )
    )
    for item in report_dict.get("results", []):
        print(
            "  - {status}: {name} ({ext}, {size} bytes)".format(
                status=item.get("status"),
                name=item.get("original_filename"),
                ext=item.get("detected_extension") or "n/a",
                size=item.get("source_size_bytes", 0),
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import phone transcription text files into normalized local storage.",
    )
    parser.add_argument(
        "--source-dir",
        required=True,
        type=Path,
        help="Folder containing transcription exports to import",
    )
    parser.add_argument(
        "--dest-dir",
        type=Path,
        default=None,
        help=f"Output folder (default: {default_dest_dir()})",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write outputs. Without this flag, only report planned imports.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Scan subfolders (default: only the top-level source folder).",
    )
    parser.add_argument(
        "--max-file-mb",
        type=float,
        default=DEFAULT_MAX_FILE_MB,
        help=f"Skip files larger than this many megabytes (default: {DEFAULT_MAX_FILE_MB}).",
    )
    args = parser.parse_args()

    source = args.source_dir.expanduser().resolve()
    if not source.is_dir():
        print(json.dumps({"error": f"Source directory not found: {source}"}))
        return 1

    dest = (
        args.dest_dir.expanduser().resolve()
        if args.dest_dir is not None
        else default_dest_dir(PROJECT_ROOT)
    )

    try:
        report = ingest_transcriptions(
            source,
            dest,
            apply=args.apply,
            recursive=args.recursive,
            max_file_mb=args.max_file_mb,
        )
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1

    payload = report.to_dict()
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print()
    _print_human_summary(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
