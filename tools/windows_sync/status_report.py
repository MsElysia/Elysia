#!/usr/bin/env python3
"""Operator-facing synchronization status report."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))

from tools.windows_sync.paths import state_root, status_path
from tools.windows_sync.sync_check import build_status


def render_text(status: dict) -> str:
    lines = [
        "════════════════════════════════════════════════════════════",
        " Elysia Windows ↔ GitHub synchronization status",
        "════════════════════════════════════════════════════════════",
        f" Synchronization status : {status.get('synchronization_status')}",
        f" Release verification   : {status.get('release_verification_status')}",
        f" Pending updates        : {status.get('pending_updates')}",
        f" Divergence             : {status.get('divergence')}",
        f" Last successful check  : {status.get('last_successful_check_utc')}",
        f" Checked at (UTC)       : {status.get('checked_at_utc')}",
        "",
        f" GitHub SHA ({status.get('canonical_branch')})",
        f"   {status.get('github_sha')}",
        f" Local development SHA",
        f"   {status.get('local_development_sha')}  (dirty={status.get('dev_dirty')})",
        f" Installed release SOURCE SHA (not a live process)",
        f"   {status.get('installed_release_source_sha', status.get('installed_runtime_sha'))}",
        f" Source provenance      : {status.get('release_source_evidence', 'unknown')}",
        f" Release source dirty   : {status.get('release_source_dirty')}",
        f" Running process SHA    : {status.get('running_runtime_sha') or 'NOT VERIFIED'}",
        f" Runtime verification   : {status.get('running_runtime_verification', 'not_checked')}",
        "",
        f" Dev root     : {status.get('dev_root')}",
        f" Release root : {status.get('release_root')}",
        f" Ops data     : {status.get('operational_data_root')} (never replaced by sync)",
        f" Pilot        : {status.get('preserved_pilot_root')} (preserved)",
        "",
    ]
    for note in status.get("notes") or []:
        lines.append(f" note: {note}")
    for err in status.get("errors") or []:
        lines.append(f" ERROR: {err}")
    lines.append("════════════════════════════════════════════════════════════")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print Elysia sync status report")
    parser.add_argument("--fetch", action="store_true", help="Fetch remotes before reporting")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Also write report.txt next to sync_status.json",
    )
    args = parser.parse_args(argv)
    status = build_status(do_fetch=args.fetch)
    text = render_text(status)
    if args.json:
        print(json.dumps(status, indent=2))
    else:
        print(text, end="")
    if args.write:
        (state_root() / "report.txt").write_text(text, encoding="utf-8")
        # keep status_path already written by build_status
        assert status_path().is_file()
    return 0 if not status.get("errors") else 2


if __name__ == "__main__":
    raise SystemExit(main())
