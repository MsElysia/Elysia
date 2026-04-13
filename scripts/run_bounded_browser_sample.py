#!/usr/bin/env python3
"""
Sample trigger for the bounded browser agent (read-only, small budgets).

Requires: pip install playwright && playwright install chromium

From project root:
  python scripts/run_bounded_browser_sample.py
  python scripts/run_bounded_browser_sample.py "https://example.com"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from project_guardian.bounded_browser import browse_task

    url = (sys.argv[1] if len(sys.argv) > 1 else "https://docs.python.org/3/library/asyncio.html").strip()
    goal = f"Summarize main topics and APIs relevant to: {url}"

    try:
        result = browse_task(
            goal,
            start_url=url,
            max_pages=3,
            max_scrolls_per_page=2,
            max_depth=1,
        )
    except RuntimeError as e:
        print(e)
        return 2
    except ValueError as e:
        print(e)
        return 2

    print("stop_reason:", result.stop_reason)
    print("visited:", len(result.visited_urls))
    for i, s in enumerate(result.steps):
        print(json.dumps({"i": i, "url": s.url, "type": s.page_type, "rel": s.relevance_score, "next": s.continue_recommendation}, indent=2))
        print("  findings:", (s.key_findings or "")[:300].replace("\n", " "))
    print("State also appended to browser_agent_state.json (project root).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
