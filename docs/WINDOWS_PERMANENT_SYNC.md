# Windows ↔ GitHub permanent synchronization

## Goal

One authoritative Elysia codebase on the canonical GitHub branch, one development workspace on Windows, and one verified operational release install. Completed work is not left stranded on a single machine or in disconnected draft branches.

## Canonical identities

| Role | Path / ref |
|------|------------|
| Canonical GitHub branch | `integration/windows-canonical` on `MsElysia/Elysia` |
| Development workspace | `C:\Users\Owner\Elysia-Dev` (junction → integration worktree) |
| Verified release install | `C:\Users\Owner\Elysia-Windows-Release` |
| Sync state (not memory) | `C:\Users\Owner\Elysia-Sync-State` |
| Operational data | `C:\Users\Owner\Elysia-Windows-Integration-Data` (**never** replaced by git sync) |
| Preserved pilot | `C:\Users\Owner\Elysia-Verified-Pilot` + `Elysia-Verified-Pilot-Data` |
| Desktop shortcut | `elysia1` → release `pilot\START_ELYSIA1.bat` |

GitHub `main` remains protected. This workflow **does not** auto-merge `main`.

## Agent workflow (mandatory after each completed local task)

1. Run relevant tests (`scripts/run_windows_intel_rc_tests.py` and/or focused pytest).
2. Run secrets scan: `python -m tools.windows_sync.secrets_scan` via promote or manual review of changed files.
3. Commit on `integration/windows-canonical` with a clear message.
4. Push to `origin integration/windows-canonical`.
5. Record exact SHA + test evidence under `C:\Users\Owner\Elysia-Sync-State\` (status JSON / promote logs).
6. Only after tests pass, promote to the release install (`promote_release.py`).
7. Do **not** create competing “master” apps or duplicate authorization/memory/execution frameworks.

## Sync tooling

```text
tools/windows_sync/sync_check.py       # fetch + status (startup / hourly)
tools/windows_sync/sync_integrate.py   # FF (or --merge) into Dev; refuses dirty trees
tools/windows_sync/promote_release.py  # backup + tested promote to release install
tools/windows_sync/status_report.py    # operator-facing report
tools/windows_sync/install_hourly_task.ps1
```

Safety rules encoded in tooling:

- Fetch is automatic; **never** `reset --hard` or discard uncommitted work.
- Integrate refuses dirty worktrees.
- Promote refuses secret-scan hits and failed intel-slice tests (unless explicitly skipped).
- Operational memory/credentials/settings/databases are never overwritten with repository copies.
- Previous release source tree is copied under `guardian_backups\elysia-release-versions` before update.

## Operator status fields

`status_report.py` / `Elysia-Sync-State\sync_status.json` expose:

- GitHub SHA, local development SHA, installed runtime SHA
- synchronization status, last successful check, pending updates
- release verification status, divergence (identical / local_ahead / remote_ahead / diverged)

## Hourly + startup checks

- Launchers call `sync_check.py` on startup unless `ELYSIA_SYNC_ON_LAUNCH=0`.
- Install hourly task: `powershell -File tools\windows_sync\install_hourly_task.ps1`

## Deliberately excluded duplicate frameworks

PRs that introduce parallel GuardianCore task/calculator stacks (historically #173–#176) must not be blind-merged into this branch. Document gaps and port missing *behaviors* into the existing Windows composition / restricted paths instead.

## Round-trip verification checklist

1. Local commit on Dev → push → GitHub SHA visible via `sync_check --json`
2. Fresh fetch on Dev → SHAs match
3. `promote_release.py` → installed runtime SHA equals GitHub/Dev SHA
4. `elysia1` launches release install; restart recovers; ops data untouched
