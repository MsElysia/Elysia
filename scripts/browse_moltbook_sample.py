#!/usr/bin/env python3
"""
Sample: bounded read-only browse of https://www.moltbook.com/ (domain-locked).

Requires: pip install playwright && playwright install chromium

Usage:
  python scripts/browse_moltbook_sample.py
  python scripts/browse_moltbook_sample.py "summarize what is on the homepage"
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> int:
    p = argparse.ArgumentParser(description="Moltbook-only bounded browser sample")
    p.add_argument("goal", nargs="?", default="read the Moltbook homepage and note main sections")
    args = p.parse_args()

    from project_guardian.bounded_browser.moltbook import browse_moltbook

    try:
        r = browse_moltbook(args.goal)
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 2
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    print("stop_reason:", r.stop_reason)
    print("visited:", r.visited_urls)
    for s in r.steps:
        print(f"- [{s.relevance_score:.2f}] {s.url}\n  {s.key_findings[:400]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
