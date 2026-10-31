# Elysia Windows Intelligence — Local Release Candidate

**Status:** Local integration candidate — not deployed, not approved for personal operator data.  
**Source tip (pre-RC docs commit):** `f23280d9765759e1f97a96b9b9b786f0caa1760d`  
**Branch base:** `cursor/windows-comparable-outcome-learning-20261031`  
**RC branch:** `cursor/windows-release-candidate-20261031`  
**Preserved pilot (untouched):** `4f69bd12eaa30f8aa83e3c731359d9c7ea626e50`

## What this candidate is

One coherent Windows application that can:

- Launch through the normal contained entry used by `pilot/START_ELYSIA_VERIFIED_PILOT.bat`
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
| Operator launcher | `pilot\START_ELYSIA_VERIFIED_PILOT.bat` |
| Python launcher | `pilot\launch_verified_pilot.py` |
| Runtime entry | `scripts\start_contained_browser_memory.py` |
| Stop | `pilot\STOP_ELYSIA_VERIFIED_PILOT.bat` |

Preferred UI: `http://127.0.0.1:5065/` (scans upward if busy; never kills unknown listeners).  
Default durable store for the BAT launcher: `C:\Users\Owner\Elysia-Windows-Integration-Data` — **do not use for acceptance**.

### Isolated acceptance / disposable run

```powershell
$env:ELYSIA_LOCAL_MODEL = "llama3.2:3b"
& "C:\Users\Owner\Project guardian\.venv\Scripts\python.exe" `
  scripts\accept_windows_release_candidate_e2e.py
```

This uses port **5084** and a tempfile disposable store. Avoids 5065/5066.

## Dependencies

- Windows 10+
- Python 3.13.x at `C:\Users\Owner\Project guardian\.venv\Scripts\python.exe`
- Ollama 0.40.x listening on `127.0.0.1:11434`
- Installed model: `llama3.2:3b` (do not download during RC verification)

## Verified test commands

```powershell
# Focused regression slice (intel + contained + restricted)
python -m pytest tests/test_local_memory_chat_pilot.py tests/test_capability_awareness.py `
  tests/test_capability_composition.py tests/test_local_documents_search.py `
  tests/test_structured_field_extraction.py tests/test_extract_records.py `
  tests/test_adaptive_replan.py tests/test_composition_outcome_feedback.py `
  tests/test_comparable_outcome_learning.py tests/test_conversation_continuity.py `
  tests/test_operator_task_state.py tests/test_task_execution.py `
  tests/test_task_step_completion.py tests/test_document_task_execution.py `
  tests/test_contained_startup.py tests/test_restricted_runtime_adapter.py `
  tests/test_control_panel_restricted_runtime.py -q

# Same-session native E2E
python scripts/accept_windows_release_candidate_e2e.py
```

Evidence: `docs/evidence/windows-release-candidate-e2e.json`

## Backup / recovery

USB folder: `D:\ElysiaBackups\windows-intel-rc-comparable-outcome-20261031`

- Bundle: `elysia-windows-intel-f23280d.bundle`
- SHA256: `71CC69ACE1A8A02B8A31CFF690B737DF5063301568B49A4E1DA0DA6A9607AB69`
- Restore:

```powershell
git clone D:\ElysiaBackups\windows-intel-rc-comparable-outcome-20261031\elysia-windows-intel-f23280d.bundle <dir>
git -C <dir> checkout -B cursor/windows-comparable-outcome-learning-20261031 `
  origin/cursor/windows-comparable-outcome-learning-20261031
git -C <dir> rev-parse HEAD
# expect f23280d9765759e1f97a96b9b9b786f0caa1760d
```

Older USB checkpoints under `D:\ElysiaBackups\` are preserved.

## Operator controls (unchanged)

- Request-scoped authorize checkboxes for calculator / documents / compose tools
- Capabilities tab is **read-only** (cannot enable autonomy or cloud)
- Contained config keeps autonomy, providers, and background workers disabled
- Loopback-only Ollama; no cloud fallback

## Known limitations

- Two Windows symlink-privilege skips remain skips (not converted to passes)
- Legacy dashboard surfaces beyond the restricted/intel paths are not a full security boundary — keep loopback-only
- Pilot BAT prefers port 5065 / shared integration data root — use disposable E2E for verification
- Email, web search, finance, calendar, autonomy remain unavailable / not authorized
- Outcome learning requires comparable strategy context (by design)
- Plan & Progress dashboard controls now call composition propose/rank/evaluate/replan/apply. Compose tools still bind via conversation task steps (not chat scopes). Use START_ELYSIA_RC_DISPOSABLE.bat for isolated BAT-path testing.
- Legacy `tests/test_task_execution.py` has pre-existing GuardianCore singleton failures outside the Windows intel path

## Inventory

See `INTEGRATION_INVENTORY.md` in this folder.

