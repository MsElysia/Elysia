#!/usr/bin/env python3
"""Read-only diagnostics for local memory workspaces."""

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
    format_memory_doctor_report,
    run_memory_doctor,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect a local memory workspace without writing files.",
    )
    parser.add_argument("--dest-dir", type=Path, required=True, help="Local memory workspace directory")
    parser.add_argument("--json", action="store_true", help="Print JSON diagnostics")
    args = parser.parse_args()

    report = run_memory_doctor(args.dest_dir)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_memory_doctor_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
