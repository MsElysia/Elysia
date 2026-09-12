#!/usr/bin/env python
"""CLI wrapper for Project Guardian autonomy log health analysis."""
from __future__ import annotations

import sys
from pathlib import Path


def _ensure_repo_on_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def main() -> int:
    _ensure_repo_on_path()
    from project_guardian.autonomy_log_health import main as health_main

    return health_main()


if __name__ == "__main__":
    raise SystemExit(main())
