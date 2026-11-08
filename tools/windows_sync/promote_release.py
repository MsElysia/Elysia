#!/usr/bin/env python3
"""Promote a tested development SHA into the stable Windows release install.

Never copies operational memory/credentials. Backs up the previous release tree
(source only) before updating. Requires a clean, exact-verified delivery tip and
passing intel-slice tests. An explicit verified --expected-sha is mandatory.
This preflight is NOT a restorable backup or installed-runtime certification.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
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
    DEFAULT_RELEASE_ROOT,
    DEFAULT_RELEASE_BACKUP_ROOT,
    DEFAULT_STATE_ROOT,
    GITHUB_REPO,
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


_PINNED_SHA = re.compile(r"[0-9a-f]{40}\Z")
_STABLE_LAUNCHERS = (
    "pilot/START_ELYSIA1.bat",
    "pilot/START_ELYSIA_VERIFIED_PILOT.bat",
    "pilot/launch_verified_pilot.py",
)


def _git_preflight(repo: Path, *args: str) -> str:
    """Bounded read-only Git query immune to inherited GIT_DIR/WORK_TREE/etc.

    Do not call fetch/checkout or update Git references as part of preflight.
    A failed/offline remote check is a hard release stop, not cached success.
    """
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    env.update({"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"})
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=25,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise gitutil.GitError("canonical Git preflight unavailable") from exc
    if result.returncode != 0:
        # Never echo remote URLs, credential helpers or environment values.
        raise gitutil.GitError(f"canonical Git preflight failed: {args[0]}")
    return result.stdout.strip()


def _raw_release_destination() -> Path:
    raw = (os.environ.get("ELYSIA_RELEASE_ROOT") or str(DEFAULT_RELEASE_ROOT)).strip()
    path = Path(raw).expanduser()
    if not path.is_absolute() or ".." in path.parts:
        raise RuntimeError("unsafe release destination: absolute unaliased path required")
    # release_root() resolves reparse points, so inspect the raw path FIRST.
    for node in (path, *path.parents):
        if node.is_symlink():
            raise RuntimeError("unsafe release destination: symlink ancestor")
        if os.name == "nt":
            junction = getattr(node, "is_junction", None)
            if not callable(junction):
                raise RuntimeError("cannot verify Windows junction safety")
            if junction():
                raise RuntimeError("unsafe release destination: junction ancestor")
            try:
                attributes = node.lstat().st_file_attributes
            except FileNotFoundError:
                continue
            if attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise RuntimeError("unsafe release destination: reparse ancestor")
    return path.resolve(strict=False)


def _protected_path(key: str, default: Path) -> Path:
    raw = (os.environ.get(key) or str(default)).strip()
    path = Path(raw).expanduser()
    if not path.is_absolute() or ".." in path.parts:
        raise RuntimeError("unsafe protected destination configuration")
    return path.resolve(strict=False)


def _safe_release_destination(dev: Path) -> Path:
    dest = _raw_release_destination()
    if dest != release_root():
        raise RuntimeError("release destination changed while validating")
    protected = (
        dev,
        OPERATIONAL_DATA_ROOT,
        PRESERVED_PILOT_ROOT,
        PRESERVED_PILOT_DATA,
        _protected_path("ELYSIA_SYNC_STATE_ROOT", DEFAULT_STATE_ROOT),
        _protected_path("ELYSIA_RELEASE_BACKUP_ROOT", DEFAULT_RELEASE_BACKUP_ROOT),
    )
    for root in protected:
        candidate = root.resolve(strict=False)
        # Reject either containment direction, including an ancestor that
        # would capture data, pilot, Dev, sync state or backup destinations.
        if dest == candidate or candidate in dest.parents or dest in candidate.parents:
            raise RuntimeError("release destination overlaps protected source/data/storage")
    return dest


def _canonical_origin(url: str) -> bool:
    expected = GITHUB_REPO.lower()
    allowed = {
        f"https://github.com/{expected}",
        f"https://github.com/{expected}.git",
        f"git@github.com:{expected}.git",
        f"git@github.com:{expected}",
        f"ssh://git@github.com/{expected}.git",
        f"ssh://git@github.com/{expected}",
    }
    return url.strip().rstrip("/").lower() in allowed


def _release_preflight(
    *, expected_sha: str | None, skip_tests: bool, allow_dirty_dev: bool
) -> tuple[Path, Path, str]:
    """Pure validation: no local writes, backup, fetch, checkout or test launch."""
    if skip_tests or allow_dirty_dev:
        raise RuntimeError("deprecated unsafe --skip-tests/--allow-dirty-dev flag refused")
    if not isinstance(expected_sha, str) or not _PINNED_SHA.fullmatch(expected_sha):
        raise RuntimeError("explicit pinned 40-hex --expected-sha required")
    dev = dev_root()
    release = _safe_release_destination(dev)
    if _git_preflight(dev, "rev-parse", "--verify", "HEAD") != expected_sha:
        raise RuntimeError("Dev HEAD differs from independently approved SHA")
    if _git_preflight(dev, "symbolic-ref", "--quiet", "--short", "HEAD") != CANONICAL_BRANCH:
        raise RuntimeError("Dev is detached or not on canonical branch")
    if _git_preflight(dev, "status", "--porcelain=v1", "-z", "--untracked-files=all"):
        raise RuntimeError("Dev worktree dirty; refusing promotion")
    if not _canonical_origin(_git_preflight(dev, "remote", "get-url", "origin")):
        raise RuntimeError("origin does not identify the authoritative GitHub repository")
    tracking = f"refs/remotes/origin/{CANONICAL_BRANCH}"
    if _git_preflight(dev, "rev-parse", "--verify", tracking) != expected_sha:
        raise RuntimeError("locally tracked canonical target differs from approved SHA")
    # Read-only LIVE remote query; stale tracking refs are not release evidence.
    remote_branch = f"refs/heads/{CANONICAL_BRANCH}"
    live = _git_preflight(dev, "ls-remote", "--exit-code", "origin", remote_branch)
    if live.split() != [expected_sha, remote_branch]:
        raise RuntimeError("live authoritative canonical branch differs or is unverified")
    for path in _STABLE_LAUNCHERS:
        line = _git_preflight(dev, "ls-tree", "--full-tree", expected_sha, "--", path)
        if not re.fullmatch(r"100644 blob [0-9a-f]{40}\t" + re.escape(path), line):
            raise RuntimeError("required tracked stable launcher/dependency absent: " + path)
    return dev, release, expected_sha


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


def promote(*, expected_sha: str | None = None, skip_tests: bool, allow_dirty_dev: bool) -> dict:
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
    # Fail closed BEFORE tests, backup/manifests, state logs or any checkout.
    # No implicit local fetch: the live remote must validate the pinned tip.
    try:
        dev, release, sha = _release_preflight(
            expected_sha=expected_sha,
            skip_tests=skip_tests,
            allow_dirty_dev=allow_dirty_dev,
        )
    except (RuntimeError, OSError, gitutil.GitError) as exc:
        result["error"] = f"release preflight BLOCKED: {exc}"
        return result

    result["sha"] = sha
    findings = scan_repo_changed(dev)
    if findings:
        result["error"] = "secrets_scan_failed"
        result["secret_findings"] = findings
        _append_log(result)
        return result

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
    result["ops_manifest"] = str(backup_operational_data_manifest() or "")
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
    parser.add_argument("--expected-sha", help="explicit approved canonical 40-hex commit (required for promotion)")
    parser.add_argument("--skip-tests", action="store_true", help="deprecated: always refused")
    parser.add_argument("--allow-dirty-dev", action="store_true", help="deprecated: always refused")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = promote(expected_sha=args.expected_sha, skip_tests=args.skip_tests, allow_dirty_dev=args.allow_dirty_dev)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"ok={result['ok']} sha={result['sha']} release={result['release_root']}")
        if result.get("error"):
            print(f"error: {result['error']}", file=sys.stderr)
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
