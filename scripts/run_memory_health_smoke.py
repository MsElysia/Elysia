#!/usr/bin/env python3
"""Smoke-test local memory diagnostics and demo workspace behavior."""

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
    format_memory_health_smoke_report,
    run_memory_health_smoke,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the local memory diagnostics/demo health smoke.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON smoke result")
    parser.add_argument("--keep-temp", action="store_true", help="Preserve the temporary workspace")
    args = parser.parse_args()

    report = run_memory_health_smoke(keep_temp=args.keep_temp)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(format_memory_health_smoke_report(report))
    return 0 if report.verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
