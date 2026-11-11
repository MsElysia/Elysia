#!/usr/bin/env python3
"""Fetch GitHub and record sync status. Never mutates local commits or worktrees."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))

from tools.windows_sync import gitutil
from tools.windows_sync.paths import (
    CANONICAL_BRANCH,
    REMOTE_NAME,
    OPERATIONAL_DATA_ROOT,
    PRESERVED_PILOT_DATA,
    PRESERVED_PILOT_ROOT,
    dev_root,
    load_json,
    release_root,
    save_json,
    status_path,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_release_sha(root: Path) -> str | None:
    if not root.is_dir():
        return None
    try:
        return gitutil.rev_parse(root, "HEAD")
    except gitutil.GitError:
        marker = root / "RELEASE_SHA.txt"
        if marker.is_file():
            return marker.read_text(encoding="utf-8").strip() or None
        return None


def build_status(*, do_fetch: bool) -> dict:
    dev = dev_root()
    release = release_root()
    now = utc_now()
    status: dict = {
        "schema": "elysia.windows_sync.v1",
        "checked_at_utc": now,
        "canonical_branch": CANONICAL_BRANCH,
        "github_repo": "MsElysia/Elysia",
        "dev_root": str(dev),
        "release_root": str(release),
        "operational_data_root": str(OPERATIONAL_DATA_ROOT),
        "preserved_pilot_root": str(PRESERVED_PILOT_ROOT),
        "preserved_pilot_data": str(PRESERVED_PILOT_DATA),
        "fetch_attempted": do_fetch,
        "fetch_ok": False,
        "fetch_error": None,
        "github_sha": None,
        "local_development_sha": None,
        "installed_runtime_sha": None,
        "dev_branch": None,
        "dev_dirty": None,
        "ahead": None,
        "behind": None,
        "divergence": "unknown",
        "pending_updates": False,
        "synchronization_status": "unknown",
        "release_verification_status": "unknown",
        # This script inspects SHA identities ONLY. read_release_sha() may
        # fall back to RELEASE_SHA.txt when the release is not a Git worktree.
        # Neither source is evidence that an installed app actually runs.
        "release_verification_scope": "git_head_or_release_marker_comparison_only",
        "operational_verification": {
            "installed_launcher_startup": "not_tested_by_this_check",
            "application_restart_and_memory_recovery": "not_tested_by_this_check",
            "restorable_operational_backup": "not_tested_by_this_check",
        },
        "last_successful_check_utc": None,
        "notes": [],
        "errors": [],
    }

    prev = load_json(status_path())
    status["last_successful_check_utc"] = prev.get("last_successful_check_utc")

    if not dev.is_dir():
        status["errors"].append(f"dev_root missing: {dev}")
        status["synchronization_status"] = "blocked"
        save_json(status_path(), status)
        return status

    try:
        wt = gitutil.worktree_state(dev)
        status["local_development_sha"] = wt.head
        status["dev_branch"] = wt.branch
        status["dev_dirty"] = wt.dirty
        if wt.dirty:
            status["notes"].append("dev worktree has uncommitted changes; integrate will refuse auto-merge")
    except gitutil.GitError as exc:
        status["errors"].append(f"dev identity: {exc}")
        status["synchronization_status"] = "blocked"
        save_json(status_path(), status)
        return status

    if do_fetch:
        try:
            gitutil.fetch(dev, REMOTE_NAME)
            status["fetch_ok"] = True
        except gitutil.GitError as exc:
            status["fetch_error"] = str(exc)
            status["errors"].append(str(exc))
            status["synchronization_status"] = "degraded"
            save_json(status_path(), status)
            return status
    else:
        status["fetch_ok"] = True  # caller skipped fetch intentionally
        status["notes"].append("fetch skipped")

    remote_sha = gitutil.remote_ref_sha(dev, REMOTE_NAME, CANONICAL_BRANCH)
    status["github_sha"] = remote_sha
    if remote_sha is None:
        status["notes"].append(
            f"remote branch {REMOTE_NAME}/{CANONICAL_BRANCH} not present yet — push required"
        )
        status["divergence"] = "local_only"
        status["pending_updates"] = False
        status["synchronization_status"] = "local_ahead_unpushed"
    else:
        ahead, behind = gitutil.ahead_behind(dev, wt.head, remote_sha)
        status["ahead"] = ahead
        status["behind"] = behind
        if ahead == 0 and behind == 0:
            status["divergence"] = "identical"
            status["pending_updates"] = False
            status["synchronization_status"] = "synchronized"
        elif ahead > 0 and behind == 0:
            status["divergence"] = "local_ahead"
            status["pending_updates"] = False
            status["synchronization_status"] = "local_ahead_unpushed"
        elif ahead == 0 and behind > 0:
            status["divergence"] = "remote_ahead"
            status["pending_updates"] = True
            status["synchronization_status"] = "updates_available"
        else:
            status["divergence"] = "diverged"
            status["pending_updates"] = behind > 0
            status["synchronization_status"] = "diverged"

    status["installed_runtime_sha"] = read_release_sha(release)
    if status["installed_runtime_sha"] is None:
        status["release_verification_status"] = "not_installed"
        status["notes"].append("release root missing — run promote_release after tests")
    elif remote_sha and status["installed_runtime_sha"] == remote_sha and status["divergence"] == "identical":
        status["release_verification_status"] = "matches_github_and_dev"
    elif status["installed_runtime_sha"] == status["local_development_sha"]:
        status["release_verification_status"] = "matches_dev"
        if status.get("behind"):
            status["notes"].append("release matches dirty/outdated local tip relative to GitHub")
    else:
        status["release_verification_status"] = "stale_or_mismatch"
        status["pending_updates"] = True

    if not status["errors"] and status["fetch_ok"]:
        status["last_successful_check_utc"] = now

    save_json(status_path(), status)
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Elysia Windows sync check (fetch + status)")
    parser.add_argument("--no-fetch", action="store_true", help="Record status without network fetch")
    parser.add_argument("--json", action="store_true", help="Print full JSON status")
    args = parser.parse_args(argv)
    status = build_status(do_fetch=not args.no_fetch)
    if args.json:
        import json

        print(json.dumps(status, indent=2))
    else:
        print(f"synchronization_status: {status['synchronization_status']}")
        print(f"github_sha:             {status['github_sha']}")
        print(f"local_development_sha:  {status['local_development_sha']}")
        print(f"installed_runtime_sha:  {status['installed_runtime_sha']}")
        print(f"pending_updates:        {status['pending_updates']}")
        print(f"release_code_sha_status:{status['release_verification_status']}")
        print(f"release_verification:   {status['release_verification_status']}")  # legacy key/label
        print("release_check_scope:    Git SHA or release marker comparison only")
        print("NOT TESTED HERE: installed app startup; application restart/memory recovery;")
        print("                 restorable operational-data backup")
        print(f"last_successful_check:  {status['last_successful_check_utc']}")
        for note in status.get("notes") or []:
            print(f"note: {note}")
        for err in status.get("errors") or []:
            print(f"error: {err}", file=sys.stderr)
    return 0 if not status.get("errors") else 2


if __name__ == "__main__":
    raise SystemExit(main())
