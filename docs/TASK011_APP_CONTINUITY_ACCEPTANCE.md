# Task 011 | Elysia application-level synthetic memory continuity

**STATUS: DRAFT SOURCE ONLY. NO TEST WAS EXECUTED. NO OWNER-PC ACCESS OR LOCAL USER DATA.**

Canonical starting point: `MsElysia/Elysia`, `integration/windows-canonical` at exact SHA `f286722736c58b8d626f07e841b29e800efe2d8b`. The packet is one new file: `tools/windows_sync/task011_app_continuity_acceptance.py` on an isolated draft branch. It is not merged, installed, scheduled, deployed or included in GitHub Actions.

## Why this work, after Task 010?

Task 010's original Cursor receipts reported 11/11 PASS on the actual owner's Windows machine for manually requested synthetic stopped-pilot snapshot, verification, and isolated restore. They did **not** run Elysia after restoring and did not prove memory and conversation recall.

Canonical source already provides: `scripts/start_contained_browser_memory.py` (real contained `GuardianCore` plus loopback UI), `project_guardian/restricted_runtime_adapter.py` (authenticated teach/correct/retrieve), `project_guardian/ui_control_panel.py` (`/api/chat` deterministic restricted-memory reply plus conversation APIs), `pilot/pilot_identity.py` (scoped cooperative shutdown request), `project_guardian/conversation_continuity.py` (persisted checkpoints), and `tools/windows_sync/ops_recovery.py` (offline synthetic snapshot and fresh isolated restore). **Adopt and adapt these, do not build a new MemoryCore, API, backup or launcher.**

Existing source tests were inspected: `scripts/accept_memory_write_verification_windows.py`, `scripts/accept_conversation_continuity_windows.py`, `scripts/accept_windows_release_candidate_e2e.py`, `scripts/accept_windows_documents_http.py`, `tests/test_control_panel_restricted_runtime.py`, `tests/test_contained_startup.py`, `tests/test_conversation_continuity.py`, `project_guardian/tests/test_integration_memory_persistence.py` and `tests/test_windows_ops_recovery.py`. They show useful coverage, but some old acceptance scripts use fixed ports/paths, forced process termination, evidence output under the source tree, or PASS labels representing other tests rather than actual assertions. Task 011 does not silently reuse those claims.

## Acceptance: one ordinary restart plus one fresh recovered app

All operations are deferred until a separately authorized bounded owner-Windows session. Driver must run from a **verified staged copy OUTSIDE** the original repo, its detached test worktree, operational memory, and scratch root. Require non-elevated Windows Python 3.12+ (3.13 is acceptable), the clean physical source root exactly at pinned canonical SHA, pinned Git file blobs, a new empty local fixed-disk scratch directory named `Elysia-Task011-Disposable`, no reparse/junction path, and an unused loopback port 5078. Never use Task010's existing run folder or touch its previous receipts.

| Gate | Required observable acceptance |
|---|---|
| A00 | Read-only preflight proves exact physical Git worktree, clean SHA, pinned source blobs, suitable scratch and port |
| A01 | Real contained `GuardianCore`/UI process started under a disposable root; authenticated `/api/restricted/v1/memory-store` identifies the exact synthetic MemoryCore JSON path |
| A02 | Unauthenticated fact write returns 401; valid principal cannot enable restricted autonomy (403); factual teach and correction both report `persistence_verified=true` |
| A03 | Same `fact_id` has exactly two ordered revisions, old value preserved as history and new value marked current; `POST /api/chat` using `use_local_model=false` supplies matching corrected fact through `restricted-memory` |
| A04 | Real conversation API creates a fictional objective, stores next step and writes a checkpoint |
| A05 | Original owned child exits cleanly via its matching `runtime/shutdown.request` token/marker, without force kill or unrelated PID kill |
| A06 | Restart a **new** real contained `GuardianCore` process against the SAME synthetic root; retrieve the same corrected fact, original history and checkpoint/next step; no authorization inherited |
| A07 | Stop again cooperatively and prove test port is released before snapshot |
| A08 | Existing `ops_recovery` makes, verifies and publishes an offline snapshot only with `--ack-stopped`; rejects unsafe stop state |
| A09 | Restore into a previously nonexistent second synthetic root, compare primary memory SHA-256 against the original and snapshot; do not overwrite live/real roots |
| A10 | Start a **third** actual contained runtime using ONLY the restored root. HTTP chat, restricted history and conversation resume all retrieve the original corrected synthetic fact and next step, with fresh process-local auth |
| A11 | Final cooperative stop succeeds, the original synthetic memory bytes are unchanged by recovery, and pinned source Git SHA/blobs/clean state survive |

A full PASS requires exact result status `PASS_SYNTHETIC_APPLICATION_RESTART_AND_RECOVERY` with all ELEVEN named `PASS_...` entries. The source script itself is **not** counted as proof until independently reviewed and later executed on Windows.

All positive claims require actual API fields, exact fact ID/revisions, corrected statement, checkpoint identity and hashes, not merely HTTP 200, a running port, test-loop count or a self-reported summary. The local chat response is deterministic, with `use_local_model=false`, not an Ollama answer. No cloud model/provider is invoked deliberately.

## Containment and authority

- The child process environment is built from a minimal OS allowlist, not by copying secrets, cloud/provider variables or Git overrides; it pins `ELYSIA_DISPOSABLE_ROOT` and `ELYSIA_PILOT_DATA_ROOT` separately for each synthetic root, disables auto learning, sync and local-model requests, redirects child home/appdata/temp/cache to the synthetic root, binds UI to literal `127.0.0.1:5078`, and generates process-local tokens. No password or token is published in receipt JSON.
- The driver has no general Git write command. Git preflight removes inherited `GIT_*` overrides, disallows lazy fetch/network protocols and checks the source's physical toplevel, pinned SHA, clean worktree and critical blobs **before any import** from source.
- There is no GitHub Actions, new runtime implementation, new durable-memory format, source checkout/reset, public endpoint, application installation, cloud API, credential change or escalation. Actual operator network isolation is *not* certified by this packet. A real Windows session must be separately approved, including review of local outbound/network boundaries; provider-disabled configuration alone is not an OS firewall.
- The standalone code calls only existing Elysia endpoints and the existing ops-recovery CLI. It does not call installed launcher BATs, alter existing shortcuts, use real Elysia memory, or require Ollama.
- Each test-created child is owned as a `subprocess.Popen` handle. Stop is a cooperative signed request to that child's exact synthetic runtime root. On timeout, record STOP, preserve artifacts and never terminate an arbitrary PID or retry. If a child remains alive, do not assume safe recovery or continue to a second launch.
- Original synthetic root is preserved. A separate restore into fresh root demonstrates recoverability and app behavior; it **does not** simulate real power loss or certify rollback of the installed release. The driver neither corrupts nor deletes even its synthetic original.
- Native logs, snapshot, restored tree, marker and result receipt are retained in the new unique `run-*` directory for inspection. No automatic cleanup; subsequent cleanup of run and temporary source worktrees requires separate owner permission.

## Future local invocation (NOT authorized yet)

After independent static 2 TEST review and separate owner permission, stage **only** the reviewed script by its exact immutable GitHub commit and verify its Git blob. Use an already existing clean physical worktree at `f286722...`, not a junction, and a fresh scratch parent. On Windows, use Python 3.13 already present if it has the runtime dependencies. Missing dependencies => STOP; **no pip install** under this scope.

```powershell
$Repo = '<EXISTING PHYSICAL PINNED WORKTREE>'
$Packet = '<VERIFIED STAGED TASK011 SCRIPT OUTSIDE SOURCE>'
$Scratch = '<NEW EMPTY FIXED-DISK Elysia-Task011-Disposable FOLDER>'

# Read-only gate: exactly once.
py -3.13 -B $Packet --source-root $Repo --scratch-parent $Scratch --preflight
# Require: PASS_READ_ONLY_TASK011_PREFLIGHT; NOTHING_EXECUTED and exit 0.

# Later, only if separately approved AND preflight passed, exactly once:
py -3.13 -B $Packet --source-root $Repo --scratch-parent $Scratch --execute-synthetic
# Require exit 0 AND full on-disk TASK011_RESULT.json evidence.
```

## Stop, reporting and recovery

On a failed initial Git identity or staging check, do not run preflight. On failed preflight, do not start Elysia. On any failed live gate, stop the owned synthetic child via its token once if that shutdown has not already been attempted; no force kill, no retries, no automatic "fix" of app code, source, environment, dependency or OS settings. Preserve the entire new synthetic run and report `STOP`, exact gate, source SHA, script blob, child-alive flag, whether the port is available, retained artifact names and whether any real data or provider network boundary was crossed. Do not print local operator paths, credentials, tokens or app logs into GitHub or ChatGPT.

Receipt contract:
- `TASK011_SYNTHETIC_ONLY.json`: `type=task011.disposable.application-continuity`, `source_sha=f286722...`, `real_data_used=false`, `auto_cleanup=false`.
- `TASK011_RESULT.json`: `status`, `source_sha`, `synthetic_only=true`, list of actual named checks, `operational_runtime_tested=false`, `installed_release_tested=false`, `cleanup_performed=false` and `test_child_still_running`. STOP adds a non-sensitive failure code.
- In a successful run, record three distinct child process starts, three cooperative shutdowns, one source-root restart, one existing-tool snapshot/verify, one isolated restore, exact memory hashes and post-restore fact plus conversation resume.
- Reviewer must independently inspect both JSON receipts and compare with the reviewed source, not accept PASS from a summary alone.

**Future proof ceiling:** A synthetic PASS supports actual application-level continuity under deliberate cooperative shutdown and separate restored-root boot. It does not prove recovering personal data, installed UI/desktop launcher behavior, noncooperating writers, full Guardian storage coverage, protection against corrupted backup hashes, encrypted backups, power-loss tolerance, OS-native firewall isolation, rollback of release promotion or public-facing security.

**Governance:** Task010 remains completed within its native synthetic scope. Task011 is PREPARED DRAFT ONLY and requires independent 2 TEST falsification. Protected `main`, canonical `integration/windows-canonical`, production memory and release remain unchanged; release **STOP**.
