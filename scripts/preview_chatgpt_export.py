#!/usr/bin/env python3
"""
Preview a local ChatGPT export JSON for memory candidate staging.

Preview-only: does not write memory candidates or call models/APIs.

Example:
  python scripts/preview_chatgpt_export.py --export-json ./conversations.json --dest-dir ./data/chatgpt_import
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
    DEFAULT_MAX_CONVERSATION_CHARS,
    ChatGPTExportIngestError,
    preview_chatgpt_export,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Preview local ChatGPT export JSON (no import, no network).",
    )
    parser.add_argument(
        "--export-json",
        type=Path,
        required=True,
        help="Path to local conversations.json export file",
    )
    parser.add_argument(
        "--dest-dir",
        type=Path,
        required=True,
        help="Destination workspace for preview session artifacts",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of conversations to preview",
    )
    parser.add_argument(
        "--max-conversation-chars",
        type=int,
        default=DEFAULT_MAX_CONVERSATION_CHARS,
        help=f"Max characters per conversation (default: {DEFAULT_MAX_CONVERSATION_CHARS})",
    )
    args = parser.parse_args()

    try:
        report = preview_chatgpt_export(
            export_json=args.export_json,
            dest_dir=args.dest_dir,
            limit=args.limit,
            max_conversation_chars=args.max_conversation_chars,
        )
    except ChatGPTExportIngestError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1

    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
