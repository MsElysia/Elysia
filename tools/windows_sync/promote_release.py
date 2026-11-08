#!/usr/bin/env python3
"""Promote a tested development SHA into the stable Windows release install.

Never copies operational memory/credentials. Backs up the previous release tree
(source only) before updating. Requires a clean, exact-verified delivery tip and
passing intel-slice tests. Promotion requires an independently approved exact SHA;
legacy test/dirty bypass flags are rejected before any release mutation.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
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
    REMOTE_NAME,
    DEFAULT_RELEASE_ROOT,
    DEFAULT_RELEASE_BACKUP_ROOT,
    DEFAULT_STATE_ROOT,
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



# Preflight is deliberately read-only. No state_root(), release_backup_root(),
# network fetch, log creation, checkout, or operational-data access here.
_LAUNCHER_SOURCE = (
    "pilot/START_ELYSIA1.bat",
    "pilot/START_ELYSIA_VERIFIED_PILOT.bat",
    "pilot/launch_verified_pilot.py",
)
_HEX_SHA = re.compile(r"[0-9a-f]{40}")


def _configured_release_path() -> Path:
    """Return raw release destination, BEFORE paths.release_root() resolves links."""
    raw = (os.environ.get("ELYSIA_RELEASE_ROOT") or "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_RELEASE_ROOT


def _configured_protected_path(env_name: str, default: Path) -> Path:
    raw = (os.environ.get(env_name) or "").strip()
    return Path(raw).expanduser() if raw else default


def _protected_release_roots(dev: Path) -> tuple[Path, ...]:
    """Use read-only path identities; these functions must not create folders."""
    return (
        dev,
        _REPO,
        OPERATIONAL_DATA_ROOT,
        PRESERVED_PILOT_ROOT,
        PRESERVED_PILOT_DATA,
        _configured_protected_path("ELYSIA_SYNC_STATE_ROOT", DEFAULT_STATE_ROOT),
        _configured_protected_path("ELYSIA_RELEASE_BACKUP_ROOT", DEFAULT_RELEASE_BACKUP_ROOT),
    )


def _is_redirected_path(path: Path) -> bool:
    """Identify symlinks, junctions and Windows reparse points without following."""
    if path.is_symlink():
        return True
    if os.name != "nt":
        return False
    junction = getattr(path, "is_junction", None)
    if junction is None:
        raise RuntimeError("cannot verify Windows junction safety")
    if junction():
        return True
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        return True
    return False


def _no_overlap(left: Path, right: Path) -> bool:
    """Reject equality and parent/child relationships in either direction."""
    return left != right and left not in right.parents and right not in left.parents


def _validate_release_destination(requested: Path, protected_roots: tuple[Path, ...]) -> Path:
    """Read-only destination identity check; rejects aliases before resolving."""
    requested = Path(requested).expanduser()
    if not requested.is_absolute() or ".." in requested.parts:
        raise RuntimeError("release destination must be absolute without traversal")
    for ancestor in (requested, *requested.parents):
        if _is_redirected_path(ancestor):
            raise RuntimeError("release destination includes symlink/junction/reparse alias")
    if requested.exists() and not requested.is_dir():
        raise RuntimeError("release destination is an existing nondirectory")
    # Paths that contain (or are contained by) any protected root are unsafe.
    # Check both literal and resolved versions; the protected Dev path may
    # itself be the documented junction, which need not be rejected.
    for other in protected_roots:
        other = Path(other).expanduser()
        if not other.is_absolute():
            raise RuntimeError("cannot verify a protected root identity")
        if not _no_overlap(requested, other):
            raise RuntimeError("release destination overlaps a protected root")
        if not _no_overlap(requested.resolve(strict=False),
                           other.resolve(strict=False)):
            raise RuntimeError("resolved release destination overlaps protected root")
    if requested.resolve(strict=False) != requested:
        raise RuntimeError("release destination resolves through an unsafe alias")
    return requested


def preflight_release(
    *,
    expected_sha: str | None,
    dev: Path,
    release_requested: Path,
    protected_roots: tuple[Path, ...],
    skip_tests: bool = False,
    allow_dirty_dev: bool = False,
) -> str:
    """Return approved source SHA or reject BEFORE all promotion side effects.

    A cached origin tracking ref is insufficient. An unambiguous live
    ls-remote response from origin is required; no fetch or Git state change.
    """
    if not isinstance(expected_sha, str) or not _HEX_SHA.fullmatch(expected_sha):
        raise RuntimeError("expected SHA must be a supplied exact 40-hex approved revision")
    if skip_tests or allow_dirty_dev:
        raise RuntimeError("promotion bypass flags not permitted: skip-tests/allow-dirty-dev")
    _validate_release_destination(release_requested, protected_roots)

    wt = gitutil.worktree_state(dev)
    if wt.branch != CANONICAL_BRANCH:
        raise RuntimeError("Dev branch not canonical; detached HEAD refused")
    if wt.dirty:
        raise RuntimeError("Dev dirty; source changes cannot be promoted")
    if wt.head != expected_sha:
        raise RuntimeError("Dev SHA differs from independently approved expected SHA")
    cached = gitutil.remote_ref_sha(dev, REMOTE_NAME, CANONICAL_BRANCH)
    if cached != expected_sha:
        raise RuntimeError("cached origin canonical SHA missing, stale or different")
    # This performs a READ-ONLY remote query. No access/error means BLOCKED,
    # not fallback to potentially stale sync-state metadata.
    remote_ref = f"refs/heads/{CANONICAL_BRANCH}"
    remote = gitutil.run_git(
        dev, ["ls-remote", "--exit-code", REMOTE_NAME, remote_ref], timeout=30.0
    )
    lines = [line.strip() for line in (remote.stdout or "").splitlines() if line.strip()]
    if len(lines) != 1 or lines[0] != f"{expected_sha}\t{remote_ref}":
        raise RuntimeError("live origin canonical SHA cannot be affirmed")
    # Checking an existing Release worktree's cleanliness here avoids backing
    # it up before discovering dirty/unidentified source. No checkout occurs.
    release = Path(release_requested)
    if release.is_dir():
        installed = gitutil.worktree_state(release)
        if installed.dirty:
            raise RuntimeError("release worktree dirty; refusing preflight")

    for path in _LAUNCHER_SOURCE:
        # Required files must be tracked regular blobs at the approved tip.
        item = dev / path
        if not item.is_file() or item.is_symlink():
            raise RuntimeError(f"missing or redirected target launcher source: {path}")
        tree = gitutil.run_git(dev, ["ls-tree", expected_sha, "--", path])
        records = [line for line in (tree.stdout or "").splitlines() if line.strip()]
        if len(records) != 1 or not re.fullmatch(
            rf"100644 blob [0-9a-f]{{40}}\t{re.escape(path)}", records[0]
        ):
            raise RuntimeError(f"missing tracked target launcher dependency: {path}")
    return expected_sha


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


def promote(
    *,
    skip_tests: bool,
    allow_dirty_dev: bool,
    expected_sha: str | None = None,
) -> dict:
    """Refuse unsafe promotions WITHOUT even creating a log or backup folder."""
    dev = dev_root()  # Reading path identity is side-effect-free.
    requested_release = _configured_release_path()
    result: dict = {
        "ok": False,
        "at_utc": utc_now(),
        "sha": None,
        "release_root": str(requested_release),
        "backup_release": None,
        "ops_manifest": None,
        "tests_ok": None,
        "error": None,
    }
    try:
        sha = preflight_release(
            expected_sha=expected_sha,
            dev=dev,
            release_requested=requested_release,
            protected_roots=_protected_release_roots(dev),
            skip_tests=skip_tests,
            allow_dirty_dev=allow_dirty_dev,
        )
    except (RuntimeError, gitutil.GitError, OSError, ValueError) as exc:
        result["error"] = f"promotion preflight BLOCKED: {exc}"
        # Intentionally no _append_log/state_root on preflight rejection.
        return result
    result["sha"] = sha

    findings = scan_repo_changed(dev)
    if findings:
        result["error"] = "secrets_scan_failed"
        result["secret_findings"] = findings
        _append_log(result)
        return result

    # Preflight has already pinned live canonical source; bypass flags denied.
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
    parser.add_argument("--skip-tests", action="store_true", help="legacy flag; rejected")
    parser.add_argument("--allow-dirty-dev", action="store_true", help="legacy flag; rejected")
    parser.add_argument("--expected-sha", help="required approved 40-hex canonical commit")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = promote(skip_tests=args.skip_tests, allow_dirty_dev=args.allow_dirty_dev,
                     expected_sha=args.expected_sha)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"ok={result['ok']} sha={result['sha']} release={result['release_root']}")
        if result.get("error"):
            print(f"error: {result['error']}", file=sys.stderr)
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
