#!/usr/bin/env python3
"""Print memory ranking config and sample proposals (read-only; no store mutation)."""

from __future__ import annotations

import argparse
import json

from project_guardian.memory_ranking import (
    get_memory_ranking_config,
    load_memory_ranking_config,
    propose_compression_from_dicts,
    rank_memories_from_snippets,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory ranking diagnostic (dry-run only)")
    parser.add_argument(
        "--config-path",
        default="",
        help="Optional absolute path to memory_ranking.json (clears loader cache once)",
    )
    args = parser.parse_args()

    if args.config_path:
        from project_guardian.memory_ranking import clear_memory_ranking_config_cache

        clear_memory_ranking_config_cache()
        c = get_memory_ranking_config(_path_str=str(args.config_path))
    else:
        c = get_memory_ranking_config()

    flat = load_memory_ranking_config()
    print("=== load_memory_ranking_config() (default path cache) ===")
    print(json.dumps(flat, indent=2))
    if args.config_path:
        print("\nNote: flat dict above reflects default cached config; using custom path for scoring below.")

    samples = [
        {
            "id": "sample-1",
            "thought": "Routine heartbeat status unchanged. " * 25,
            "time": "2021-01-01T00:00:00+00:00",
            "access_count": 0,
            "priority": 0.1,
        },
        {
            "id": "sample-2",
            "thought": "Important decision: keep operator chat dry-run only.",
            "time": "2026-05-14T10:00:00+00:00",
            "access_count": 30,
            "priority": 0.95,
            "user_important": True,
        },
    ]
    ctx = {"now": "2026-05-14T12:00:00+00:00"}
    report = propose_compression_from_dicts(samples, cfg=c, context=ctx)
    print("\n=== sample proposals ===")
    for pr in report.proposals:
        print(
            f"- {pr.memory_id}: action={pr.action} score={pr.original_value_score:.3f} "
            f"len={pr.current_length} dry_run={pr.dry_run} reason={pr.reason}"
        )

    snippets = [s["thought"] for s in samples]
    ranked = rank_memories_from_snippets(snippets, c, current_goal_text="operator chat safety")
    print("\n=== snippet ranking (value scores) ===")
    for r in ranked:
        print(f"- {r.memory_id}: value={r.memory_value_score:.3f}")


if __name__ == "__main__":
    main()
