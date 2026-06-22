#!/usr/bin/env python3
"""
Apply a ChatGPT export preview to stage memory candidates.

Dry-run by default. Use --apply to write candidates to the review queue.

Example:
  python scripts/apply_chatgpt_export.py --preview-json <path>/chatgpt_export_preview.json
  python scripts/apply_chatgpt_export.py --preview-json <path>/chatgpt_export_preview.json --apply
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

from project_guardian.local_ingestion.chatgpt_export_ingest import (  # noqa: E402
    ChatGPTExportIngestError,
    apply_chatgpt_export,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply ChatGPT export preview to stage memory candidates (dry-run default).",
    )
    parser.add_argument(
        "--preview-json",
        type=Path,
        required=True,
        help="Path to chatgpt_export_preview.json",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Stage memory candidates in review queue",
    )
    args = parser.parse_args()

    try:
        report = apply_chatgpt_export(
            preview_json=args.preview_json,
            apply=args.apply,
        )
    except ChatGPTExportIngestError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1

    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
