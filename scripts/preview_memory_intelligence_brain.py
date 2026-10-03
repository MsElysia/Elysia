#!/usr/bin/env python3
"""Read an explicit ingestion destination through Brain/TDA without persistence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest-dir", type=Path, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--expand-highlight", help="Explicitly include one recalled highlight's raw source")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    from project_guardian.brain.memory_intelligence_bridge import (
        ReadOnlyMemoryIntelligenceBridge,
        run_memory_intelligence_preview,
    )
    from project_guardian.local_ingestion.memory_intelligence import MemoryIntelligenceError

    try:
        trace, _ = run_memory_intelligence_preview(args.dest_dir, args.query)
        payload = trace.unified_export
        if args.expand_highlight:
            bridge = ReadOnlyMemoryIntelligenceBridge(args.dest_dir)
            bridge.retrieve(args.query[:800], limit=10)
            payload["expanded_highlight"] = bridge.expand(args.expand_highlight)
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    except (MemoryIntelligenceError, ValueError) as exc:
        print(f"Read-only preview blocked: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
