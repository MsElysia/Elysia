# Control Panel UI Audit Report

**Date:** 2024-01-XX  
**Task:** TASK-0026  
**Auditor:** Cursor Agent

## Executive Summary

The Control Panel UI has been **expanded** to support task creation, mutation payload creation, and run_once() execution. All operations remain local-only and enforce strict validation. No arbitrary execution or new external action surfaces introduced.

## What Exists

### Core Features

1. **Status Dashboard** (`GET /`)
   - Shows current task, pending reviews, last acceptance, last run_once
   - Provides buttons for quick actions
   - ✅ Implemented

2. **Review Queue Management**
   - List reviews (`GET /reviews`)
   - View detail (`GET /reviews/{request_id}`)
   - Approve/deny (`POST /reviews/{request_id}/approve|deny`)
   - ✅ Implemented (from TASK-0013)

3. **Task Creation** (NEW in TASK-0026)
   - Task builder form (`GET /tasks/new`)
   - Create task endpoint (`POST /tasks/create`)
   - Supports RUN_ACCEPTANCE, CLEAR_CURRENT_TASK, APPLY_MUTATION
   - ✅ Implemented

4. **Mutation Payload Creation** (NEW in TASK-0026)
   - Mutation builder form (`GET /mutations/new`)
   - Create mutation endpoint (`POST /mutations/create`)
   - Validates paths and schema
   - ✅ Implemented

5. **Run Once Execution** (NEW in TASK-0026)
   - Run once endpoint (`POST /control/run-once`)
   - Creates artifact: REPORTS/run_once_last.json
   - ✅ Implemented

6. **Acceptance Execution**
   - Run acceptance endpoint (`POST /control/run-acceptance`)
   - ✅ Implemented (from TASK-0013)

### Validation

✅ **Task ID validation**: `^TASK-[A-Za-z0-9_-]{1,32}$`  
✅ **Task type whitelist**: RUN_ACCEPTANCE, CLEAR_CURRENT_TASK, APPLY_MUTATION only  
✅ **Mutation file validation**: Must be MUTATIONS/*.json  
✅ **Path safety**: No .., no absolute paths, within repo root  
✅ **Schema validation**: touched_paths matches changes[].path set  
✅ **Payload name validation**: `^[A-Za-z0-9_-]{1,64}\.json$`

### Atomic Writes

✅ All file writes use tmp + os.replace() pattern:
- Task files (TASKS/{task_id}.md)
- Mutation payloads (MUTATIONS/{name}.json)
- run_once artifact (REPORTS/run_once_last.json)
- CONTROL.md updates

### Context Redaction

✅ Sensitive fields redacted from review context display  
✅ Acceptance log output redacted for sensitive patterns

## Behavioral Verification

### ✅ Dashboard Loads
**Test:** `test_dashboard_returns_200()`  
**Result:** PASS
- Dashboard returns 200
- Shows current task, pending reviews, last acceptance, last run_once

### ✅ Run Once Creates Artifact
**Test:** `test_run_once_creates_artifact()`  
**Result:** PASS
- run_once() executes
- Artifact created with timestamp and result
- Redirects to dashboard

### ✅ Task Creation Validation
**Test:** `test_create_task_invalid_id()`, `test_create_task_valid()`  
**Result:** PASS
- Invalid task_id returns 400
- Valid task creates file atomically
- APPLY_MUTATION task includes mutation file directive

### ✅ Mutation Creation Validation
**Test:** `test_create_mutation_invalid_path()`, `test_create_mutation_valid()`, `test_create_mutation_path_mismatch()`  
**Result:** PASS
- Invalid paths (.., absolute) return 400
- Valid mutation creates file with correct schema
- Path mismatch returns 400

## What's Missing

### 1. Authentication (If Exposed Beyond Localhost)

**Current:** No authentication (local-only binding assumed)  
**Gap:** If UI is exposed beyond 127.0.0.1, authentication becomes mandatory  
**Status:** ⚠️ Documented, acceptable for current scope (local-only)

### 2. Task File Editing

**Current:** Can create tasks, but cannot edit existing task files  
**Gap:** No edit endpoint for existing tasks  
**Status:** ⚠️ Documented, acceptable for current scope (create-only workflow)

### 3. Mutation Payload Editing

**Current:** Can create mutation payloads, but cannot edit existing ones  
**Gap:** No edit endpoint for existing mutations  
**Status:** ⚠️ Documented, acceptable for current scope (create-only workflow)

### 4. Bulk Operations

**Current:** Single task/mutation creation only  
**Gap:** No bulk create or batch operations  
**Status:** ⚠️ Documented, acceptable for current scope

### 5. Task Execution History

**Current:** Shows last run_once result, but no history  
**Gap:** No historical view of past run_once executions  
**Status:** ⚠️ Documented, acceptable for current scope

## Security Assessment

### ✅ Strengths

1. **Local-only binding**: Binds to 127.0.0.1 only
2. **Application-layer enforcement**: FastAPI middleware rejects non-loopback client hosts with HTTP 403
3. **Loopback guard**: Only allows `127.0.0.1`, `::1`, and `localhost` client addresses
4. **No trust in forwarded headers**: Uses `request.client.host` only; does NOT trust `X-Forwarded-For`
5. **Misbind warning**: Dashboard shows warning if `UI_BIND_HOST` env var is set to non-loopback
6. **Strict validation**: All inputs validated before processing
7. **No arbitrary execution**: Only whitelisted operations
8. **Atomic writes**: Prevents partial file corruption
9. **Path safety**: Prevents path traversal attacks
10. **Context redaction**: Sensitive data not exposed in UI

### ⚠️ Remaining Risks

1. **No authentication**: If somehow exposed (e.g., via misconfiguration), anyone with network access can control system
2. **No rate limiting**: Could be abused for DoS (mitigated by local-only enforcement)
3. **No CSRF protection**: Forms vulnerable to CSRF if exposed (mitigated by local-only enforcement)
4. **No input sanitization for display**: XSS possible if user-controlled data displayed (currently minimal, most output is escaped)

**Mitigation:** 
- Application-layer local-only enforcement provides defense-in-depth
- Start script enforces loopback binding
- Dashboard warns if bind host misconfigured
- If exposed beyond localhost, add authentication + CSRF protection + rate limiting

## Test Coverage

### Smoke Tests (`tests/test_ui_smoke.py`)

✅ Dashboard loads (200)  
✅ Run once creates artifact  
✅ Task creation validation (invalid ID, valid task, APPLY_MUTATION)  
✅ Mutation creation validation (invalid path, valid mutation, path mismatch)

**Coverage:** Core endpoints covered. Edge cases documented.

## Integration Correctness

### ✅ With GuardianCore
- Instantiates Core correctly for run_once()
- Uses same config pattern as other Core usage

### ✅ With ReviewQueue
- Reads pending reviews correctly
- Updates status on approve/deny

### ✅ With ApprovalStore
- Records approvals/denials correctly
- Context matching works

### ✅ With File System
- Atomic writes implemented correctly
- Path validation prevents traversal
- Schema validation prevents invalid payloads

## Performance Characteristics

- **Dashboard load**: Fast (O(1) file reads + O(n) review scan)
- **Task creation**: Fast (O(1) file write)
- **Mutation creation**: Fast (O(n) path validation + O(1) file write)
- **Run once**: Depends on Core.run_once() execution time

## Next Recommended Tasks

1. **TASK-0027:** Add authentication if UI needs to be exposed beyond localhost
2. **TASK-0028:** Add task/mutation editing capabilities
3. **TASK-0029:** Add run_once execution history view
4. **TASK-0030:** Add bulk operations for task/mutation creation

## TASK-0027 Update: Observability Features

**Status:** ✅ Read-only observability features added

**New Features:**
- Execution history (run_once and acceptance) with timestamped files
- Review history with status filtering (pending/approved/denied/all)
- Mutation payload browser (list + detail views)
- Diff viewer for mutation changes vs current files
- History retention directories created automatically

**History Retention:**
- Run once history: `REPORTS/run_once_history/YYYYMMDD_HHMMSS_<status>_<task>.json`
- Acceptance history: `REPORTS/acceptance_history/YYYYMMDD_HHMMSS_<status>_<exit_code>.json` (+ optional .log)
- All history writes are atomic

**Security:**
- All file reads validated (no .., no arbitrary paths)
- Diff viewer validates path is in mutation touched_paths
- Diff output HTML escaped (no injection)
- Diff size limited (2000 lines max)

## TASK-0028 Update: History Retention Policy

**Status:** ✅ Retention policy implemented

**Retention Limits:**
- Run once history: Keep newest 200 files (pruned after each write)
- Acceptance history: Keep newest 200 files (pruned after each write)
- Age-based: Also prune files older than 30 days
- Log copy cap: Only copy acceptance logs if size <= 1MB

**Safety:**
- Only deletes files in history directories
- Only deletes files matching expected patterns (*.json, *.log)
- Never deletes `REPORTS/*_last.*` files
- Best-effort: Pruning failures don't crash UI

**Log Copy Behavior:**
- If log > 1MB: JSON includes `log_copied: false`, `log_too_large: true`, `log_size_bytes: <size>`
- If log <= 1MB: Log is copied, JSON includes `log_copied: true`
- No truncation (either copy full or skip with marker)

## TASK-0029 Update: Mutation Payload Base Hashing

**Status:** ✅ Base hashing and mismatch warnings implemented

**Base Hashing:**
- Mutation payload creation now computes SHA256 hash of each touched file at creation time
- Base info stored in payload: `{"base": {path: {"sha256": "...", "bytes": N, "captured_at": "ISO8601"}}}`
- Missing files marked as "MISSING" in base info
- Backward compatible: Legacy payloads without base info are handled gracefully

**Diff Viewer Enhancements:**
- Computes current file SHA256 and compares with base hash
- Shows mismatch warning banner when file changed since payload creation
- Warning includes base SHA256, current SHA256, and captured_at timestamp
- Legacy payloads show "No base recorded" message

**Mutation Detail Enhancements:**
- Shows base hash and current hash for each touched path
- Status indicators: MATCH / MISMATCH / MISSING / NEW_FILE / DELETED / LEGACY / ERROR
- Visual indicators with color-coded badges

**Remaining Risks:**
- **Base content not stored**: Only hashes are stored, not file content. Cannot show "diff vs base" mode without storing base content (not implemented, acceptable for current scope)
- **Hash collisions**: SHA256 collisions are extremely unlikely but theoretically possible (acceptable risk)

## TASK-0030 Update: Local-Only Access Enforcement

**Status:** ✅ Local-only enforcement implemented

**Application-Layer Enforcement:**
- FastAPI middleware rejects non-loopback client hosts with HTTP 403
- Loopback guard function: `is_loopback()` checks for `127.0.0.1`, `::1`, `localhost`
- Uses `request.client.host` only (does NOT trust `X-Forwarded-For` headers)
- Error page rendered for blocked requests

**Misbind Warning:**
- Dashboard shows local-only banner: "Local-only UI is enforced. Ensure server is bound to 127.0.0.1."
- If `UI_BIND_HOST` env var is set to non-loopback, shows red warning banner
- `/api/status` includes `local_only_enforced: true` and `bind_host_warning` flags

**Start Script:**
- `start_control_panel.ps1` enforces `--host 127.0.0.1 --port 8000`
- Shows security warnings about not modifying host parameter

**Risks Reduced:**
- **Accidental exposure**: Application-layer guard prevents remote access even if server is misconfigured
- **Defense-in-depth**: Multiple layers (binding + middleware) prevent exposure
- **Visibility**: Dashboard warnings alert operators to misconfiguration

**Remaining Risks:**
- **No authentication**: If somehow exposed (e.g., via proxy), no authentication (acceptable for local-only use case)
- **No rate limiting**: Could be abused for DoS (mitigated by local-only enforcement)
- **No CSRF protection**: Forms vulnerable to CSRF if exposed (mitigated by local-only enforcement)

## Conclusion

The Control Panel UI has been **successfully expanded** with task creation, mutation payload creation, run_once() execution, and read-only observability features. All operations enforce strict validation, use atomic writes, and remain local-only. No arbitrary execution or new external action surfaces introduced. Remaining gaps are documented and acceptable for current scope.
