#!/usr/bin/env python3
"""Read-only diagnostic for the canonical self-improvement proposal queue.

Does not apply patches, run shell commands, or trigger autonomy.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

# Repo root: scripts/ -> parent
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project_guardian.self_improvement.proposal_queue import (  # noqa: E402
    DEFAULT_PROPOSALS_PATH,
    LEGACY_BRAIN_QUEUE_PATH,
    LEGACY_QUEUE_WRITE_ENV,
    ProposalQueue,
    count_jsonl_rows,
    legacy_queue_write_enabled,
    rank_proposals,
)


def _migration_recommendation(*, canonical_count: int, legacy_exists: bool, legacy_count: int) -> str:
    if legacy_queue_write_enabled():
        return (
            f"Legacy dual-write is ON ({LEGACY_QUEUE_WRITE_ENV}). "
            "Unset that env var when all consumers read the canonical queue only."
        )
    if legacy_exists and legacy_count > 0 and canonical_count > 0:
        return (
            "Canonical queue is source of truth; legacy file is historical. "
            "Do not delete legacy rows automatically — migrate or archive manually if needed."
        )
    if legacy_exists and legacy_count > 0 and canonical_count == 0:
        return (
            "Legacy file has rows but canonical queue is empty. "
            "Review legacy JSONL for one-time migration into canonical proposals if needed."
        )
    return "Canonical queue only (default). No legacy dual-write."


def main() -> int:
    path = Path(DEFAULT_PROPOSALS_PATH)
    legacy_path = Path(LEGACY_BRAIN_QUEUE_PATH)
    q = ProposalQueue(path)
    rows = q.read_all()
    ranked = rank_proposals(rows)
    top = ranked[:5]
    statuses = Counter(p.status for p in rows)
    legacy_exists = legacy_path.exists()
    legacy_count = count_jsonl_rows(legacy_path)
    legacy_write = legacy_queue_write_enabled()

    print("Self-improvement proposal queue (read-only)")
    print(f"  Canonical path: {path}")
    print(f"  Canonical proposal count: {len(rows)}")
    print(f"  Legacy path: {legacy_path}")
    print(f"  Legacy file exists: {legacy_exists}")
    print(f"  Legacy row count (non-empty lines): {legacy_count}")
    print(f"  Legacy write enabled ({LEGACY_QUEUE_WRITE_ENV}): {legacy_write}")
    print(f"  Statuses: {dict(statuses)}")
    print("  Top 5 by priority_score (then recency):")
    for i, p in enumerate(top, 1):
        print(
            f"    {i}. {p.proposal_id[:24]}…  status={p.status}  "
            f"priority={p.priority_score:.2f}  title={p.title[:72]!r}"
        )
    print()
    print("Migration / compatibility:")
    print(f"  {_migration_recommendation(canonical_count=len(rows), legacy_exists=legacy_exists, legacy_count=legacy_count)}")
    print()
    print("This script does not apply patches or execute commands.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
