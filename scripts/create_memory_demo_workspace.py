#!/usr/bin/env python3
"""Create a fake local-only memory demo workspace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from project_guardian.local_ingestion.memory_diagnostics import (  # noqa: E402
    MemoryDiagnosticsError,
    create_memory_demo_workspace,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a fake local memory demo workspace; dry-run by default.",
    )
    parser.add_argument("--dest-dir", type=Path, required=True, help="Destination workspace directory")
    parser.add_argument("--apply", action="store_true", help="Actually write sample files under --dest-dir")
    parser.add_argument(
        "--run-pipeline",
        action="store_true",
        help="Run the local preview/apply/review/export/search/context pipeline on fake data",
    )
    args = parser.parse_args()

    try:
        report = create_memory_demo_workspace(
            dest_dir=args.dest_dir,
            apply=args.apply,
            run_pipeline=args.run_pipeline,
        )
    except MemoryDiagnosticsError as exc:
        print(json.dumps({"verdict": "FAIL", "error": str(exc)}, indent=2))
        return 1

    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0 if report.verdict in {"PASS", "DRY_RUN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
