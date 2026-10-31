# Agent instructions — Elysia Windows permanent sync

Read and follow [docs/WINDOWS_PERMANENT_SYNC.md](docs/WINDOWS_PERMANENT_SYNC.md).

## Non-negotiable

- Canonical branch: `integration/windows-canonical` (not ad-hoc worktree-only tips).
- After each completed local development task: test → secrets review → commit → push → record SHA/evidence.
- Never force-push protected branches, never `reset --hard` away uncommitted work, never auto-merge `main`.
- Never activate cloud providers or autonomy; never replace operational data with repo copies.
- Do not invent a second Windows app or duplicate authorization / memory / execution / registry frameworks.
- Promote to `C:\Users\Owner\Elysia-Windows-Release` only after tests; keep `elysia1` pointed at that release launcher.

## Commands

```bat
python tools\windows_sync\sync_check.py
python tools\windows_sync\status_report.py --fetch --write
python tools\windows_sync\sync_integrate.py
python tools\windows_sync\promote_release.py
python scripts\run_windows_intel_rc_tests.py
```
