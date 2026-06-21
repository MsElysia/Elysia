#!/usr/bin/env python3
"""
Apply a reviewed import session preview to stage transcription memory candidates.

Dry-run by default. Use --apply to write ingestion outputs and memory candidates.

Example:
  python scripts/apply_memory_import_session.py --session-json ./data/phone_transcriptions/import_sessions/<id>/import_session_preview.json
  python scripts/apply_memory_import_session.py --session-json <path> --apply
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

from project_guardian.local_ingestion.import_session_apply import (  # noqa: E402
    ImportSessionApplyError,
    apply_memory_import_session,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply import session preview to stage memory candidates (dry-run default).",
    )
    parser.add_argument(
        "--session-json",
        type=Path,
        required=True,
        help="Path to import_session_preview.json",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write ingestion outputs and stage memory candidates",
    )
    args = parser.parse_args()

    try:
        report = apply_memory_import_session(
            session_json=args.session_json,
            apply=args.apply,
        )
    except ImportSessionApplyError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1

    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
