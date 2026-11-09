"""Safe git helpers — never force-reset, never discard uncommitted work."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


class GitError(RuntimeError):
    pass


def isolated_git_environment() -> dict[str, str]:
    """Use Git -C target without ambient GIT_DIR/WORK_TREE/CONFIG overrides.

    Git must retain its usual file locking for fetch/checkout/worktree writes,
    so do NOT set GIT_OPTIONAL_LOCKS=0 for this environment.
    """
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith("GIT_")}
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def run_git(
    repo: Path,
    args: Sequence[str],
    *,
    check: bool = True,
    timeout: float = 120.0,
    isolated_env: bool = False,
) -> subprocess.CompletedProcess[str]:
    cmd = ["git", "-C", str(repo), *args]
    try:
        proc = subprocess.run(
            cmd,
            env=isolated_git_environment() if isolated_env else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git timeout: {' '.join(args)}") from exc
    except OSError as exc:
        raise GitError(f"git unavailable: {exc}") from exc
    if check and proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise GitError(f"git {' '.join(args)} failed ({proc.returncode}): {err}")
    return proc


def rev_parse(repo: Path, ref: str = "HEAD", *, isolated_env: bool = False) -> str:
    out = run_git(repo, ["rev-parse", ref], isolated_env=isolated_env).stdout.strip()
    if len(out) != 40:
        raise GitError(f"unexpected rev-parse output for {ref!r}: {out!r}")
    return out


def is_ancestor(repo: Path, maybe_ancestor: str, tip: str) -> bool:
    proc = run_git(
        repo,
        ["merge-base", "--is-ancestor", maybe_ancestor, tip],
        check=False,
    )
    return proc.returncode == 0


@dataclass(frozen=True)
class WorktreeState:
    head: str
    branch: str | None
    dirty: bool
    staged: bool
    unstaged: bool
    untracked: bool
    porcelain: str


def worktree_state(repo: Path, *, isolated_env: bool = False) -> WorktreeState:
    head = rev_parse(repo, "HEAD", isolated_env=isolated_env)
    branch_proc = run_git(repo, ["branch", "--show-current"], check=False,
                          isolated_env=isolated_env)
    branch = (branch_proc.stdout or "").strip() or None
    porcelain = run_git(repo, ["status", "--porcelain=v1"],
                        isolated_env=isolated_env).stdout
    lines = [ln for ln in porcelain.splitlines() if ln.strip()]
    staged = any(not ln.startswith("?") and ln[:1] not in (" ", "?") for ln in lines) or any(
        len(ln) >= 2 and ln[0] not in (" ", "?") for ln in lines
    )
    unstaged = any(len(ln) >= 2 and ln[1] not in (" ", "?") for ln in lines)
    untracked = any(ln.startswith("??") for ln in lines)
    dirty = bool(lines)
    return WorktreeState(
        head=head,
        branch=branch,
        dirty=dirty,
        staged=staged,
        unstaged=unstaged,
        untracked=untracked,
        porcelain=porcelain,
    )


def fetch(repo: Path, remote: str = "origin") -> None:
    """Fetch only — never reset, never prune aggressively of local work."""
    run_git(repo, ["fetch", remote, "--prune"], timeout=180.0)


def remote_ref_sha(repo: Path, remote: str, branch: str) -> str | None:
    ref = f"refs/remotes/{remote}/{branch}"
    proc = run_git(repo, ["rev-parse", "--verify", ref], check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def ahead_behind(repo: Path, local: str, remote: str) -> tuple[int, int]:
    """Return (ahead, behind) counts for local vs remote."""
    left = run_git(repo, ["rev-list", "--count", f"{remote}..{local}"], check=False)
    right = run_git(repo, ["rev-list", "--count", f"{local}..{remote}"], check=False)
    ahead = int((left.stdout or "0").strip() or "0") if left.returncode == 0 else -1
    behind = int((right.stdout or "0").strip() or "0") if right.returncode == 0 else -1
    return ahead, behind
