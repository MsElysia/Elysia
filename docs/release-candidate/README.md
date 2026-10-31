# Elysia Windows Intelligence — Local Release Candidate

**Status:** Local integration candidate — not deployed, not approved for personal operator data.  
**Published draft PR:** [#178](https://github.com/MsElysia/Elysia/pull/178)  
**Exact published head (do not rewrite without authorization):** `2759ba43cf14ef9fb3be579d143183788f341af3`  
**Published branch:** `cursor/windows-dashboard-plan-progress-20261031`  
**Preserved pilot (untouched):** `4f69bd12eaa30f8aa83e3c731359d9c7ea626e50`  
**Base observed at publication:** `origin/main` @ `722d8e4fe85d7e42ac34066c2d651849d15e734c`

Historical checkpoints (not the PR #178 tip):

| Checkpoint | SHA | Role |
|------------|-----|------|
| Comparable-outcome learning tip | `f23280d9765759e1f97a96b9b9b786f0caa1760d` | Feature tip before RC docs / dashboard Plan & Progress |
| Pre-recon dashboard tip | `8d35e1455b34a7e3024cb8d5bda7c6139319e154` | Plan & Progress + RC disposable BAT |
| Local RC docs tip (pre-push) | superseded by `2759ba43…` | Do not cite as current published head |

Doc-only / CI repair work for review gaps lives on a **separate** branch (for example `cursor/pr178-rc-verify-docs-ci-20261031`) and must not silently replace the authorized PR #178 head.

## What this candidate is

One coherent Windows application that can:

- Launch through the normal contained entry used by `pilot/START_ELYSIA_VERIFIED_PILOT.bat` (and the isolated `START_ELYSIA_RC_DISPOSABLE.bat`)
- Serve the loopback dashboard
- Hold a real local Ollama (`llama3.2:3b`) conversation
- Teach / correct / retrieve durable restricted memory
- Discover capabilities (read-only)
- Run authorized document search, field/record extraction, labor calculation, composition, task receipts
- Evaluate insufficient results and propose a bounded replan (no inherited authorization)
- Rank capabilities from trusted outcome feedback
- Resume conversation/task state after restart

## Canonical startup

| Role | Path |
|------|------|
| Operator launcher (shared integration data) | `pilot\START_ELYSIA_VERIFIED_PILOT.bat` |
| Isolated RC launcher (disposable data root) | `pilot\START_ELYSIA_RC_DISPOSABLE.bat` |
| Python launcher | `pilot\launch_verified_pilot.py` |
| Runtime entry | `scripts\start_contained_browser_memory.py` |
| Stop (operator) | `pilot\STOP_ELYSIA_VERIFIED_PILOT.bat` |
| Stop (RC disposable) | `pilot\STOP_ELYSIA_RC_DISPOSABLE.bat` |

Preferred UI for the operator BAT: `http://127.0.0.1:5065/` (scans upward if busy; never kills unknown listeners).  
Default durable store for the operator BAT: `C:\Users\Owner\Elysia-Windows-Integration-Data` — **do not use for acceptance**.

### Isolated acceptance — two different evidence paths

| Path | What it proves | What it does **not** prove |
|------|----------------|----------------------------|
| `scripts\accept_windows_release_candidate_e2e.py` | Same-session contained Python entry, APIs, Ollama, memory, composition on a disposable store (default port **5084**) | Normal BAT startup, ownership marker, duplicate-start refusal, or STOP BAT behavior — even if a field is labeled `launcher_equivalent` |
| `pilot\START_ELYSIA_RC_DISPOSABLE.bat` + matching STOP | Normal launcher path with disposable `ELYSIA_PILOT_DATA_ROOT`, preferred unused port (default **5086**), ownership, duplicate refuse, clean stop/restart | Full browser Plan & Progress workflow unless separately exercised |

```powershell
# Python consolidator (API / contained entry) — not BAT evidence
$env:ELYSIA_LOCAL_MODEL = "llama3.2:3b"
& "C:\Users\Owner\Project guardian\.venv\Scripts\python.exe" `
  scripts\accept_windows_release_candidate_e2e.py

# Isolated BAT path (set an unused port + disposable root first)
$env:ELYSIA_PILOT_DATA_ROOT = "$env:TEMP\elysia-rc-bat-$(Get-Random)"
$env:ELYSIA_PREFERRED_UI_PORT = "5087"
$env:ELYSIA_LOCAL_MODEL = "llama3.2:3b"
.\pilot\START_ELYSIA_RC_DISPOSABLE.bat
```

## Dependencies

- Windows 10+
- Python 3.13.x at `C:\Users\Owner\Project guardian\.venv\Scripts\python.exe` (CI matrix may use 3.12)
- Ollama listening on `127.0.0.1:11434`
- Installed model: `llama3.2:3b` (do not download during RC verification)

## Test manifest

### RC-required focused regression (intel + contained + restricted)

These are the tests that must be green for Windows intelligence release-candidate claims:

```powershell
python -m pytest `
  tests/test_local_memory_chat_pilot.py `
  tests/test_capability_awareness.py `
  tests/test_capability_composition.py `
  tests/test_local_documents_search.py `
  tests/test_structured_field_extraction.py `
  tests/test_extract_records.py `
  tests/test_adaptive_replan.py `
  tests/test_composition_outcome_feedback.py `
  tests/test_comparable_outcome_learning.py `
  tests/test_conversation_continuity.py `
  tests/test_operator_task_state.py `
  tests/test_task_step_completion.py `
  tests/test_document_task_execution.py `
  tests/test_contained_startup.py `
  tests/test_restricted_runtime_adapter.py `
  tests/test_control_panel_restricted_runtime.py `
  tests/test_dashboard_plan_progress.py `
  -q
```

Reproducible CI entry (Linux + Windows): `.github/workflows/windows-intel-rc-slice.yml` → `scripts/run_windows_intel_rc_tests.py`.

### Known legacy / out-of-scope for RC green claims

| Test | Status relative to RC |
|------|------------------------|
| `tests/test_task_execution.py` | **Not** RC-required. Pre-existing GuardianCore singleton failures outside the Windows intel path. May be run for diagnosis; failures here do **not** alone block the Windows RC slice, and must not be narrated as RC-required green. |

### Same-session native Python E2E

```powershell
python scripts/accept_windows_release_candidate_e2e.py
```

Evidence artifact (when produced): `docs/evidence/windows-release-candidate-e2e.json`

## Backup / recovery

USB reconciliation folder (includes published tip lineage):  
`D:\ElysiaBackups\windows-github-reconciliation-20261031`

Older comparable-outcome USB checkpoint (historical only):  
`D:\ElysiaBackups\windows-intel-rc-comparable-outcome-20261031` → bundle for `f23280d…`

```powershell
git clone D:\ElysiaBackups\windows-github-reconciliation-20261031\elysia-authoritative-HEAD.bundle <dir>
git -C <dir> rev-parse HEAD
# expect the SHA recorded in that folder's MANIFEST.md (publication tip 2759ba43…)
```

## Operator controls (unchanged)

- Request-scoped authorize checkboxes for calculator / documents / compose tools
- Capabilities tab is **read-only** (cannot enable autonomy or cloud)
- Contained config keeps autonomy, providers, and background workers disabled
- Loopback-only Ollama; no cloud fallback

## Known limitations

- Two Windows symlink-privilege skips remain skips (not converted to passes)
- Legacy dashboard surfaces beyond the restricted/intel paths are not a full security boundary — keep loopback-only
- Operator BAT prefers port 5065 / shared integration data root — use RC disposable BAT or Python E2E for verification
- Email, web search, finance, calendar, autonomy remain unavailable / not authorized
- Outcome learning requires comparable strategy context (by design)
- Plan & Progress dashboard controls call composition propose/rank/evaluate/replan/apply. Compose tools still bind via conversation task steps (not chat scopes).
- Python RC E2E is not a substitute for BAT ownership / duplicate-start / stop verification
- Historical acceptance evidence must not be treated as re-proof of a newly modified SHA

## Inventory

See `INTEGRATION_INVENTORY.md` in this folder.
