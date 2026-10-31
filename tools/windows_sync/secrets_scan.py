"""Lightweight pre-commit secret / private-data scan for sync commits."""
from __future__ import annotations

import re
from pathlib import Path

# Pattern-based; intentionally conservative. Does not print matched secret values.
_BLOCK_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"api[_-]?key\s*[:=]\s*['\"][^'\"]{12,}['\"]", re.I),
]

_SKIP_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".venv",
    "node_modules",
    "Elysia-Windows-Integration-Data",
    "Elysia-Verified-Pilot-Data",
    "memory",
}


def scan_paths(paths: list[Path]) -> list[str]:
    """Return human-readable findings (paths + pattern names only)."""
    findings: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append(f"unreadable:{path}:{exc}")
            continue
        for pat in _BLOCK_PATTERNS:
            if pat.search(text):
                findings.append(f"{path.as_posix()}: matched {pat.pattern[:40]}…")
                break
    return findings


def scan_repo_changed(repo: Path, base: str = "HEAD") -> list[str]:
    from .gitutil import run_git

    proc = run_git(repo, ["diff", "--name-only", "--diff-filter=ACMR", base], check=False)
    names = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    # Also unstaged + untracked product files already in the index area via status
    status = run_git(repo, ["status", "--porcelain=v1"]).stdout
    for ln in status.splitlines():
        if len(ln) < 4:
            continue
        name = ln[3:].strip().split(" -> ")[-1]
        if name and name not in names:
            names.append(name)
    return scan_paths([repo / n for n in names])
