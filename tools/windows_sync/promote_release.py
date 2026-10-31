#!/usr/bin/env python3
"""Promote a tested development SHA into the stable Windows release install.

Never copies operational memory/credentials. Backs up the previous release tree
(source only) before updating. Requires a clean, exact-verified delivery tip and
passing intel-slice tests unless --skip-tests (emergency only).
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.windows_sync import gitutil
from tools.windows_sync.paths import (
    CANONICAL_BRANCH,
    OPERATIONAL_DATA_ROOT,
    PRESERVED_PILOT_DATA,
    PRESERVED_PILOT_ROOT,
    dev_root,
    release_backup_root,
    release_root,
    save_json,
    state_root,
)
from tools.windows_sync.secrets_scan import scan_repo_changed
from tools.windows_sync.sync_check import build_status


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_log(entry: dict) -> None:
    path = state_root() / "promote_log.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")


def run_intel_tests(repo: Path) -> tuple[bool, str]:
    py = Path(r"C:\Users\Owner\Project guardian\.venv\Scripts\python.exe")
    script = repo / "scripts" / "run_windows_intel_rc_tests.py"
    if not script.is_file():
        return False, f"missing {script}"
    proc = subprocess.run(
        [str(py), str(script)],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return proc.returncode == 0, out[-8000:]


def backup_operational_data_manifest() -> Path | None:
    """Record operational data presence/hashes of CONTROL only — do not copy memory DBs."""
    root = OPERATIONAL_DATA_ROOT
    if not root.is_dir():
        return None
    dest_dir = release_backup_root() / f"ops-manifest-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "at_utc": utc_now(),
        "operational_data_root": str(root),
        "note": "Manifest only — operational memory/settings NOT copied into git backups",
        "entries": [],
    }
    for child in sorted(root.iterdir()):
        manifest["entries"].append(
            {
                "name": child.name,
                "is_dir": child.is_dir(),
                "size": child.stat().st_size if child.is_file() else None,
            }
        )
    control = root / "CONTROL.md"
    if control.is_file():
        shutil.copy2(control, dest_dir / "CONTROL.md")
    path = dest_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return dest_dir


def backup_previous_release(release: Path, sha: str | None) -> Path | None:
    if not release.is_dir():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = (sha or "unknown")[:12]
    dest = release_backup_root() / f"release-{label}-{stamp}"
    # Copy source tree excluding .git bulky objects? Keep .git for rollback checkout ability.
    shutil.copytree(
        release,
        dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", "temp", "logs"),
        dirs_exist_ok=False,
    )
    return dest


def ensure_release_checkout(dev: Path, release: Path, sha: str) -> None:
    """Create or update release worktree/checkout to exact SHA without touching ops data."""
    if not release.exists():
        # Prefer worktree linked to same repo object store.
        gitutil.run_git(
            dev,
            ["worktree", "add", "--detach", str(release), sha],
            timeout=180.0,
        )
        return
    # Existing release: fetch objects via shared repo if worktree, else reset --hard ONLY
    # inside the release path after confirming no local uncommitted release edits we need.
    wt = gitutil.worktree_state(release)
    if wt.dirty:
        raise gitutil.GitError(
            "release worktree dirty; refusing promote (clean or backup manually)"
        )
    # Detached exact SHA update — release is not a development branch.
    gitutil.run_git(release, ["fetch", "origin", CANONICAL_BRANCH], check=False, timeout=180.0)
    gitutil.run_git(release, ["checkout", "--detach", sha])


def promote(*, skip_tests: bool, allow_dirty_dev: bool) -> dict:
    result: dict = {
        "ok": False,
        "at_utc": utc_now(),
        "sha": None,
        "release_root": str(release_root()),
        "backup_release": None,
        "ops_manifest": None,
        "tests_ok": None,
        "error": None,
    }
    # Hard guards: never write into pilot / ops memory trees as source destinations
    for protected in (PRESERVED_PILOT_ROOT, PRESERVED_PILOT_DATA, OPERATIONAL_DATA_ROOT):
        if release_root().resolve() == protected.resolve():
            result["error"] = f"refusing: release_root collides with protected path {protected}"
            _append_log(result)
            return result

    dev = dev_root()
    try:
        wt = gitutil.worktree_state(dev)
    except gitutil.GitError as exc:
        result["error"] = str(exc)
        _append_log(result)
        return result

    if wt.dirty and not allow_dirty_dev:
        result["error"] = "dev dirty; commit first or pass --allow-dirty-dev (not recommended)"
        _append_log(result)
        return result
    if wt.branch and wt.branch != CANONICAL_BRANCH:
        result["error"] = f"dev not on {CANONICAL_BRANCH} (on {wt.branch})"
        _append_log(result)
        return result

    findings = scan_repo_changed(dev)
    if findings:
        result["error"] = "secrets_scan_failed"
        result["secret_findings"] = findings
        _append_log(result)
        return result

    sha = wt.head
    result["sha"] = sha

    if not skip_tests:
        ok, log = run_intel_tests(dev)
        result["tests_ok"] = ok
        result["test_log_tail"] = log[-4000:]
        evidence = state_root() / f"promote-tests-{sha[:12]}.txt"
        evidence.write_text(log, encoding="utf-8")
        result["test_evidence"] = str(evidence)
        if not ok:
            result["error"] = "intel slice tests failed — release not updated"
            _append_log(result)
            return result
    else:
        result["tests_ok"] = None
        result["notes"] = ["tests skipped by operator flag"]

    result["ops_manifest"] = str(backup_operational_data_manifest() or "")
    release = release_root()
    prev_sha = None
    if release.is_dir():
        try:
            prev_sha = gitutil.rev_parse(release, "HEAD")
        except gitutil.GitError:
            prev_sha = None
        try:
            result["backup_release"] = str(backup_previous_release(release, prev_sha))
        except OSError as exc:
            result["error"] = f"release backup failed: {exc}"
            _append_log(result)
            return result

    try:
        ensure_release_checkout(dev, release, sha)
    except gitutil.GitError as exc:
        result["error"] = str(exc)
        _append_log(result)
        return result

    # Metadata lives in sync state — never dirty the release git tree with promote artifacts.
    save_json(
        state_root() / "RELEASE_META.json",
        {
            "sha": sha,
            "promoted_at_utc": utc_now(),
            "canonical_branch": CANONICAL_BRANCH,
            "dev_root": str(dev),
            "release_root": str(release),
            "operational_data_root": str(OPERATIONAL_DATA_ROOT),
            "launcher": "pilot/START_ELYSIA1.bat",
            "previous_sha": prev_sha,
            "backup_release": result.get("backup_release"),
        },
    )
    launcher = release / "pilot" / "START_ELYSIA1.bat"
    if not launcher.is_file():
        result["error"] = f"missing stable launcher after checkout: {launcher}"
        _append_log(result)
        return result

    status = build_status(do_fetch=False)
    result["sync_status"] = status.get("synchronization_status")
    result["release_verification_status"] = status.get("release_verification_status")
    result["installed_runtime_sha"] = status.get("installed_runtime_sha")
    result["ok"] = status.get("installed_runtime_sha") == sha
    if not result["ok"]:
        result["error"] = "post-promote SHA mismatch"
    save_json(state_root() / "last_promote.json", result)
    _append_log(result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Promote tested Dev SHA to Elysia-Windows-Release")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--allow-dirty-dev", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = promote(skip_tests=args.skip_tests, allow_dirty_dev=args.allow_dirty_dev)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"ok={result['ok']} sha={result['sha']} release={result['release_root']}")
        if result.get("error"):
            print(f"error: {result['error']}", file=sys.stderr)
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
