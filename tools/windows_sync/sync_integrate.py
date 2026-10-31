#!/usr/bin/env python3
"""Integrate remote canonical commits into the development workspace.

Safety:
- Refuses if the worktree is dirty
- Never force-resets
- Fast-forward only by default; --merge allows a non-ff merge commit
- Does not touch release install or operational data
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE.parent.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent.parent))

from tools.windows_sync import gitutil
from tools.windows_sync.paths import CANONICAL_BRANCH, REMOTE_NAME, dev_root, save_json, state_root
from tools.windows_sync.sync_check import build_status


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def integrate(*, allow_merge: bool) -> dict:
    result = {
        "ok": False,
        "action": None,
        "before": None,
        "after": None,
        "error": None,
        "at_utc": utc_now(),
    }
    status = build_status(do_fetch=True)
    result["status_before"] = {
        "synchronization_status": status.get("synchronization_status"),
        "github_sha": status.get("github_sha"),
        "local_development_sha": status.get("local_development_sha"),
        "behind": status.get("behind"),
        "ahead": status.get("ahead"),
        "divergence": status.get("divergence"),
    }
    dev = dev_root()
    try:
        wt = gitutil.worktree_state(dev)
    except gitutil.GitError as exc:
        result["error"] = str(exc)
        return result

    result["before"] = wt.head
    if wt.dirty:
        result["error"] = "refusing integrate: uncommitted work present (commit/stash manually)"
        return result
    if wt.branch != CANONICAL_BRANCH:
        result["error"] = (
            f"refusing integrate: expected branch {CANONICAL_BRANCH}, got {wt.branch!r}"
        )
        return result

    remote_sha = status.get("github_sha")
    if not remote_sha:
        result["error"] = "remote canonical branch missing; push first"
        return result
    if status.get("behind", 0) == 0:
        result["ok"] = True
        result["action"] = "noop_already_up_to_date"
        result["after"] = wt.head
        return result

    remote_ref = f"{REMOTE_NAME}/{CANONICAL_BRANCH}"
    ahead = int(status.get("ahead") or 0)
    behind = int(status.get("behind") or 0)

    try:
        if ahead == 0 and behind > 0:
            gitutil.run_git(dev, ["merge", "--ff-only", remote_ref])
            result["action"] = "fast_forward"
        elif allow_merge and behind > 0:
            gitutil.run_git(
                dev,
                [
                    "merge",
                    "--no-ff",
                    "-m",
                    f"merge({CANONICAL_BRANCH}): integrate {remote_ref}",
                    remote_ref,
                ],
            )
            result["action"] = "merge"
        else:
            result["error"] = (
                f"divergence ahead={ahead} behind={behind}; "
                "refusing auto-resolve. Rebase/merge manually or pass --merge when safe."
            )
            return result
    except gitutil.GitError as exc:
        result["error"] = str(exc)
        return result

    result["after"] = gitutil.rev_parse(dev, "HEAD")
    result["ok"] = True
    after_status = build_status(do_fetch=False)
    result["status_after"] = {
        "synchronization_status": after_status.get("synchronization_status"),
        "local_development_sha": after_status.get("local_development_sha"),
        "github_sha": after_status.get("github_sha"),
    }
    save_json(state_root() / "last_integrate.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Integrate GitHub canonical branch into Elysia-Dev")
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Allow non-ff merge when histories diverged (still refuses dirty trees)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = integrate(allow_merge=args.merge)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"ok={result['ok']} action={result['action']} before={result['before']} after={result['after']}")
        if result.get("error"):
            print(f"error: {result['error']}", file=sys.stderr)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
