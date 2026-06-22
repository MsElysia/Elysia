#!/usr/bin/env python3
"""
Run an end-to-end smoke test of the local memory ingestion pipeline.

Uses temporary sample files only. Does not call models, embeddings, APIs, or live memory.

Example:
  python scripts/run_local_memory_pipeline_smoke.py
  python scripts/run_local_memory_pipeline_smoke.py --json
  python scripts/run_local_memory_pipeline_smoke.py --base-dir ./tmp/smoke --keep-temp
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

from project_guardian.local_ingestion.local_memory_pipeline_smoke import (  # noqa: E402
    DEFAULT_SOURCE_TYPE,
    VALID_SOURCE_TYPES,
    LocalMemoryPipelineSmokeError,
    format_operator_summary,
    run_local_memory_pipeline_smoke,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke-test the local memory pipeline on temporary sample files.",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Preserve the temporary working directory after the run",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=None,
        help="Optional base directory for source/dest folders (default: system temp)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON summary instead of operator text",
    )
    parser.add_argument(
        "--source-type",
        choices=sorted(VALID_SOURCE_TYPES),
        default=DEFAULT_SOURCE_TYPE,
        help=f"Pipeline source to smoke-test (default: {DEFAULT_SOURCE_TYPE})",
    )
    args = parser.parse_args()

    try:
        summary = run_local_memory_pipeline_smoke(
            base_dir=args.base_dir,
            keep_temp=args.keep_temp,
            source_type=args.source_type,
        )
    except LocalMemoryPipelineSmokeError as exc:
        payload = {"verdict": "FAIL", "error": str(exc)}
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(payload["error"])
        return 1

    if args.json:
        print(json.dumps(summary.to_dict(), indent=2))
    else:
        print(format_operator_summary(summary))

    return 0 if summary.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
