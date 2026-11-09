# Elysia Task 010 | Owner-Windows native disposable recovery acceptance

**State: PREPARED DRAFT ONLY. NOT EXECUTED. NO OWNER-PC AUTHORIZATION.**
Source baseline: `integration/windows-canonical` at exact merge `f286722736c58b8d626f07e841b29e800efe2d8b` (Task 009, PR #219).
Packet: `tools/windows_sync/task010_native_acceptance.py` on the isolated Task 010 draft branch. This file is intentionally NOT merged into canonical, packaged as an installer, or added to any test runner.

## Objective and proof boundary

Exercise the *existing* `tools/windows_sync/ops_recovery.py` CLI on the owner's Windows machine **without reading, copying, opening, restoring or modifying real Elysia/Guardian memory**. Prove the real Windows filesystem operations, genuine named-mutex exclusion and non-mocked PowerShell listener probe can support a bounded manual snapshot of a synthetic *stopped* contained-pilot data root, verify it and restore it into a never-existing separate directory.

This test uses the existing `ELYSIA_PILOT_DATA_ROOT` override in `pilot/pilot_paths.py` to redirect the real implementation into an isolated synthetic root for the **child processes only**. No system-wide environment changes. No cloud, network use by this packet, extra models, GitHub Actions, dependency installation, release promotion, dashboard bind, background service, task scheduler, or desktop shortcut mutation. Git reads are local/read-only. The test does **not** start a real Elysia server, nor certify its boot, application-level recall or installed release rollback.

**Not proved even on PASS:** native process startup and restart, live operational memory backup/restoration, noncooperating writers, transactional multi-file consistency under power loss, Windows ACL and all junction/privilege cases, real file repair, external Guardian roots, encrypted/tamper-authenticated backup, automatic promotion/rollback. `promote_release.py` still makes a manifest-only operational-data inventory, not a restorable backup.

## Source inspection and evidence

- `pilot/pilot_paths.py` supports `ELYSIA_PILOT_DATA_ROOT`; default remains `C:\Users\Owner\Elysia-Windows-Integration-Data` and must never be used by this test.
- `ops_recovery.create_snapshot` requires `--ack-stopped`, exact configured pilot root, real `pilot_exclusion.writer_exclusion_status` on Windows, fresh destination, and bounded integrity verification.
- `ops_recovery.restore_isolated` verifies SHA-256/SQLite, restores only to a new root, publishes without replacing an existing destination, and removes its own partial staging on failure.
- `tests/test_windows_ops_recovery.py` exercised 32 synthetic cases on hosted Windows for Task 009, but native PowerShell and mutex acquisition were *mocked* in the six Windows-specific guard cases. Task 010 explicitly tests those OS calls on the owner machine with a synthetic root only.
- Original hosted evidence: `https://github.com/MsElysia/Elysia/actions/runs/42680996905` and independent 4 VERIFY `https://github.com/MsElysia/Elysia/issues/212#issuecomment-6752774137`.

The packet hard-pins `f2867227...` as the **existing source checkout** and checks exact Git blobs for recovery, listener exclusion, test module and RC selection. It refuses a dirty checkout or unexpected source SHA rather than fetching, resetting, switching branches or modifying any installed files.

## Conditions before any owner-PC run

**All actions below are FUTURE ONLY, subject to separate explicit operator authorization.**

1. Operator separately approves a single owner-native synthetic run. The owner-PC agent must first inspect current repo/worktree, running processes and executable paths **without opening real data**. This packet does not require stopping the real Elysia installation because it uses a different root/mutex, but the operator may elect a maintenance window.
2. A clean, existing local checkout at exactly `f286722736c58b8d626f07e841b29e800efe2d8b` is available, with Git and Python **3.12 or later**. No `git fetch`, `checkout`, `reset`, installs or repairs are allowed by this packet. If local source is not at the pinned SHA, **STOP and report**; do not alter it.
3. The operator creates an **empty** dedicated local fixed-disk folder whose final name is exactly `Elysia-Task010-Disposable`, with no junction, symlink or reparse-point ancestry, and not overlapping source, release, operational memory or preserved pilot roots. Example: `C:\Elysia-Task010-Disposable`. Creation itself is deferred pending approval.
4. The packet Python file is separately staged OUTSIDE that empty scratch folder and OUTSIDE the canonical Git worktree, e.g. `C:\Elysia-Task010-Packet\task010_native_acceptance.py`. This preserves the source checksum/cleanliness gate. Stage only after approval; do not browse or alter personal files.
5. Use non-elevated Windows execution unless the operator explicitly approves otherwise. No administrator/UAC bypass, firewall edits, antivirus exemptions, credentials, cloud providers or connectivity checks. The packet is Python stdlib-only, and no pip command is included.

## Future exact commands (DO NOT RUN YET)

The operator/approved local agent substitutes only the two preexisting fixed paths. Paths shown are **examples**, not claims about what presently exists on the PC.

```powershell
$Repo = 'C:\Users\Owner\Elysia-Dev'
$Packet = 'C:\Elysia-Task010-Packet\task010_native_acceptance.py'
$Scratch = 'C:\Elysia-Task010-Disposable'

# Step A: READ-ONLY. Must report PASS_READ_ONLY_PREFLIGHT.
py -3.12 -B $Packet --source-root $Repo --scratch-parent $Scratch --preflight

# Step B: ONE synthetic write run, ONLY after separate approval.
# Stop after a single attempt; do not repeat automatically.
py -3.12 -B $Packet --source-root $Repo --scratch-parent $Scratch --execute-synthetic
```

**Important:** The scratch parent must already exist and be empty; the packet itself never creates the parent. The script creates one uniquely named `run-*` child and all permitted synthetic inputs, outputs and receipts stay under it. It intentionally keeps that run folder for inspection and does not delete it automatically. No command is executed through this document.

## Tests and expected outcome

| Gate | Real operation or fault | PASS required |
| --- | --- | --- |
| P00 | Read-only source/SHA/Git blob, Windows Python, dedicated empty fixed-disk scratch preflight | `PASS_READ_ONLY_PREFLIGHT` before any write |
| P01 | Call real snapshot CLI without `--ack-stopped` | Fails closed, no snapshot created |
| P02 | Try snapshot from a root different from the temporary `ELYSIA_PILOT_DATA_ROOT` | Fails closed, no snapshot created |
| P03 | Child process acquires actual Windows named mutex for synthetic root, parent tries snapshot while held, releases holder | Snapshot rejected; holder remains alive during check and releases cleanly |
| P04 | Call actual snapshot CLI with the synthetic root and no mutex held | `SNAPSHOT_CREATED_OFFLINE` plus `VERIFIED_OFFLINE_SNAPSHOT`; actual strict PowerShell listener query succeeds |
| P05 | Verify published snapshot using the real CLI | `VERIFIED_OFFLINE_SNAPSHOT`; exact hashes, inventory and SQLite accepted |
| P06 | Restore only to never-existing sibling root; reopen SQLite and read known synthetic record | `RESTORED_TO_ISOLATED_ROOT`; all five files SHA-256 identical; empty directory retained; test SQLite row and synthetic JSON match |
| P07 | Attempt restore to existing target containing a sentinel | Blocked; sentinel and directory unchanged |
| P08 | Tamper with synthetic *copy* of snapshot and attempt restore | Blocked; no corrupt restore published |
| P09 | Introduce synthetic SQLite `-wal` file and attempt snapshot | Blocked; no inconsistent snapshot published; test-created WAL removed |
| P10 | Inspect own transient staging names under new run root | No leftover `.elysia-ops-stage-*` or `.elysia-restore-stage-*` |
| P11 | Confirm original synthetic source bytes remain unchanged | SHA-256 equality; no real data consulted |
| P12 | Recheck Git HEAD, clean worktree and pinned recovery-module blobs after the test | Source still exactly pinned; no repository changes |

On all successful steps the script writes `TASK010_RESULT.json` with `status=PASS_SYNTHETIC_NATIVE_SNAPSHOT_RESTORE_ONLY`, source SHA, named checks and `synthetic_only=true`. The JSON explicitly has `operational_runtime_tested=false` and `cleanup_performed=false`. The other marker, `TASK010_SYNTHETIC_ONLY.json`, identifies the disposable run.

**No result is accepted by counting loops or looking only at exit code.** Reviewer must inspect the JSON receipt and confirm expected original code identity, all named checks, byte matches, no unexpected files, and no scope violation. No real app-level recall or successful installed release may be inferred.

## Stop rules, evidence and recovery

Immediately STOP after the first unexpected exit, timeout, unknown source identity, absent or incorrect strict PowerShell result, missing cmdlet/permission, mutex ambiguity, source mutation, non-empty scratch parent, path alias/junction, any existing destination changing, hash/SQLite mismatch, stage residue, extra file, or evidence of attempted access beyond the synthetic root. No fallbacks to mocked mutex/PowerShell, no disabling guard checks, no UAC/ACL changes, and **no retries** under this scope.

On failure the script records `status=STOP` and an error code where possible, retains its new synthetic workspace for evidence, and returns nonzero. A failure to create a receipt is itself a STOP, not permission to run again. The approved agent reports the unique `run-*` name, marker and receipt statuses, source SHA, counts, gate that failed and whether any synthetic child process remains. Review and securely stop only the test's own child process if necessary. Never kill a preexisting Elysia/Guardian process based on a guessed PID.

All processing is local. Do not upload synthetic output unless separately authorized; no private paths, stderr, environment variables, passwords, memory contents or real operational hashes should enter an Issue comment. Prefer a compact report (PASS/PARTIAL/FAIL, named gate, source SHA, synthetic marker, cleanup state). Evidence to remain on the owner's machine until separately approved cleanup or archive.

## Cleanup, distinctly gated

**No automatic cleanup.** The test only removes the synthetic WAL file it creates as part of the negative WAL case; all other synthetic artifacts are preserved for inspection. Once the owner separately approves cleanup, inspect `TASK010_SYNTHETIC_ONLY.json` and `TASK010_RESULT.json` under the exact single generated `run-*` directory. Confirm it is an immediate child of the dedicated scratch folder, contains no non-synthetic files or symlinks/junctions, and does not point into operational data.

Dry-run deletion with `Remove-Item -LiteralPath $ExactRun -Recurse -Force -WhatIf` first. Only then, under explicit cleanup authority, repeat without `-WhatIf` for **that exact run directory only**. Never wildcard/delete the scratch parent, release, operational data, repository, or anything outside the one marked run. If identity or contents are uncertain, leave it intact and report.

## Acceptance / next unlock

- **Task 010 prepared** means a versioned, separately reviewable, source-pinned executable packet exists with bounded synthetic inputs, positive/negative tests, receipts and stop/cleanup procedure. **Preparation is not execution.**
- **Task 010 native PASS** would establish on-device use of the existing recovery CLI against a disposable synthetic pilot root only.
- **Not yet operational**: a separately approved milestone must prove installed-runtime startup, durable retrieval after restart, actual storage-root coverage, live-to-stopped backup, safe restore with owner consent, permissions, recovery, encryption/privacy policies and transactionally reversible promotion before any real Elysia memory is touched.

**STOP remains in force for installation, release, real memory, provider/autonomy, credentials, main/protected gate changes and any additional CI.**
