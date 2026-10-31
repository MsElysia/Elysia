#!/usr/bin/env python3
"""Record SHA + test evidence after a completed local task (pre/post push)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.windows_sync import gitutil
from tools.windows_sync.paths import save_json, state_root
from tools.windows_sync.secrets_scan import scan_repo_changed
from tools.windows_sync.sync_check import build_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True, help="Path to test log/evidence file")
    parser.add_argument("--summary", default="", help="Short task summary")
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args(argv)

    repo = _REPO
    wt = gitutil.worktree_state(repo)
    findings = scan_repo_changed(repo)
    if findings:
        print("secrets_scan_failed:", *findings, sep="\n  ", file=sys.stderr)
        return 2

    evidence = Path(args.evidence)
    record = {
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "sha": wt.head,
        "branch": wt.branch,
        "dirty": wt.dirty,
        "summary": args.summary,
        "evidence": str(evidence.resolve()) if evidence.exists() else str(evidence),
        "secret_findings": findings,
    }
    out = state_root() / f"task-{wt.head[:12]}-{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    save_json(out, record)
    status = build_status(do_fetch=args.fetch)
    print(json.dumps({"record": str(out), "sha": wt.head, "sync": status.get("synchronization_status")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
