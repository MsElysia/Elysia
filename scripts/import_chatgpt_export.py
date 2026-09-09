#!/usr/bin/env python3
"""
Import ChatGPT export (ZIP or extracted folder) into Elysia personal chatlogs.

Reads only ``conversations-*.json`` (or ``conversations.json``) from the archive — no
full ZIP extract — and writes ``elysia_chatgpt_<id>.md`` under the same directory
``get_chatlogs_path()`` uses so auto-learning / fetch_chatlogs can ingest them.

Usage:
  python scripts/import_chatgpt_export.py path/to/export.zip
  python scripts/import_chatgpt_export.py path/to/extracted_folder
  python scripts/import_chatgpt_export.py path/to/export.zip --limit 50
  python scripts/import_chatgpt_export.py path/to/export.zip --dry-run
  python scripts/import_chatgpt_export.py path/to/export.zip --force
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import ChatGPT export into Elysia chatlogs (markdown for auto-learning)",
    )
    parser.add_argument("source", type=Path, help="Path to .zip or extracted export folder")
    parser.add_argument("--limit", type=int, default=None, help="Max new conversations to write")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: get_chatlogs_path())",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and count writes without creating files",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing elysia_chatgpt_*.md files",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Write all conversations (same as --force for overwrite)",
    )
    args = parser.parse_args()
    src = args.source.expanduser().resolve()
    if not src.exists():
        print(f"[ERROR] Source not found: {src}")
        return 1

    from project_guardian.auto_learning import get_chatlogs_path
    from project_guardian.chatgpt_export_import import import_chatgpt_export

    out_dir = args.out.expanduser().resolve() if args.out else get_chatlogs_path()
    out_dir.mkdir(parents=True, exist_ok=True)

    skip_existing = not args.no_skip_existing and not args.force
    print(f"Source: {src}")
    print(f"Output: {out_dir}")
    if args.dry_run:
        print("(dry-run: no files written)\n")
    try:
        stats = import_chatgpt_export(
            src,
            out_dir,
            limit=args.limit,
            dry_run=args.dry_run,
            skip_existing=skip_existing,
            force=args.force,
        )
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        return 1
    print(
        f"Written: {stats.written} | skipped (existing): {stats.skipped_existing} | "
        f"skipped (empty): {stats.skipped_empty} | errors: {stats.errors}"
    )
    for msg in stats.error_messages[:10]:
        print(f"  ! {msg}")
    if len(stats.error_messages) > 10:
        print(f"  ... and {len(stats.error_messages) - 10} more")
    return 0 if stats.errors == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
