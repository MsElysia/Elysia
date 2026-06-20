#!/usr/bin/env python3
"""
Review and approve/reject/edit staged memory candidates.

Operator-run only. Records audit decisions locally; does not write live memory.

Examples:
  python scripts/review_memory_candidates.py --dest-dir ./data/phone_transcriptions list
  python scripts/review_memory_candidates.py --dest-dir ./data/phone_transcriptions list --all
  python scripts/review_memory_candidates.py --dest-dir ./data/phone_transcriptions approve <candidate_id> --notes "useful memory"
  python scripts/review_memory_candidates.py --dest-dir ./data/phone_transcriptions reject <candidate_id>
  python scripts/review_memory_candidates.py --dest-dir ./data/phone_transcriptions edit <candidate_id> --replacement-text-file ./cleaned.txt
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

from project_guardian.local_ingestion.memory_candidate_review import (  # noqa: E402
    MemoryCandidateReviewError,
    approve_candidate,
    edit_candidate,
    list_candidates,
    reject_candidate,
    resolve_review_paths,
)


def _load_replacement_text(args: argparse.Namespace) -> str:
    if args.replacement_text_file is not None:
        path = args.replacement_text_file.expanduser().resolve()
        if not path.is_file():
            raise MemoryCandidateReviewError(f"Replacement text file not found: {path}")
        return path.read_text(encoding="utf-8")
    if args.replacement_text is not None:
        return args.replacement_text
    raise MemoryCandidateReviewError(
        "Edit requires --replacement-text-file or --replacement-text."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Review staged memory candidates (no live memory writes).",
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
        help="Direct path to review_queue.jsonl (alternative to --dest-dir)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List candidates")
    list_parser.add_argument(
        "--all",
        action="store_true",
        help="Include candidates with any effective review status (default: pending only)",
    )

    approve_parser = subparsers.add_parser("approve", help="Approve one candidate")
    approve_parser.add_argument("candidate_id", help="Candidate ID to approve")
    approve_parser.add_argument("--notes", default=None, help="Optional operator notes")
    approve_parser.add_argument(
        "--force",
        action="store_true",
        help="Allow a new decision when a final decision already exists",
    )

    reject_parser = subparsers.add_parser("reject", help="Reject one candidate")
    reject_parser.add_argument("candidate_id", help="Candidate ID to reject")
    reject_parser.add_argument("--notes", default=None, help="Optional operator notes")
    reject_parser.add_argument("--force", action="store_true")

    edit_parser = subparsers.add_parser("edit", help="Edit one candidate text")
    edit_parser.add_argument("candidate_id", help="Candidate ID to edit")
    edit_parser.add_argument("--notes", default=None, help="Optional operator notes")
    edit_parser.add_argument("--replacement-text-file", type=Path, default=None)
    edit_parser.add_argument("--replacement-text", default=None)
    edit_parser.add_argument("--force", action="store_true")

    args = parser.parse_args()

    try:
        paths = resolve_review_paths(dest_dir=args.dest_dir, queue_path=args.queue_path)
        if args.command == "list":
            report = list_candidates(paths, include_all=args.all)
            print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
            return 0
        if args.command == "approve":
            report = approve_candidate(
                paths,
                args.candidate_id,
                notes=args.notes,
                force=args.force,
            )
        elif args.command == "reject":
            report = reject_candidate(
                paths,
                args.candidate_id,
                notes=args.notes,
                force=args.force,
            )
        elif args.command == "edit":
            replacement = _load_replacement_text(args)
            report = edit_candidate(
                paths,
                args.candidate_id,
                replacement,
                notes=args.notes,
                force=args.force,
            )
        else:
            raise MemoryCandidateReviewError(f"Unknown command: {args.command}")

        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0
    except MemoryCandidateReviewError as exc:
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
