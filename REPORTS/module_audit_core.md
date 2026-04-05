# GuardianCore Audit Report

**Date:** 2024-01-XX  
**Task:** TASK-0020  
**Auditor:** Cursor Agent

## Executive Summary

GuardianCore has been **audited** for completeness and correct integration with TrustMatrix, ReviewQueue, ApprovalStore, Gateways, and MutationEngine. A critical initialization order bug was fixed (TrustMatrix must be initialized before MutationEngine). A `run_once()` method was added for deterministic testing. All components are properly wired, and Core correctly propagates deny/review/allow decisions.

## What Exists

### Core Structure

1. **GuardianCore** (`project_guardian/core.py`)
   - Main orchestrator class
   - Initializes all components
   - Provides entrypoints for mutations, web fetching, system status
   - ~1140 lines of code

2. **Component Initialization**
   - Memory (MemoryCore or EnhancedMemoryCore)
   - TrustMatrix (initialized first)
   - ReviewQueue + ApprovalStore
   - MutationEngine (with TrustMatrix, ReviewQueue, ApprovalStore)
   - Safety, Rollback, Tasks, Consensus
   - WebReader (with TrustMatrix, ReviewQueue, ApprovalStore)
   - Advanced components (DreamEngine, MissionDirector, etc.)

3. **Entrypoints**
   - `propose_mutation()`: Code mutation with governance gating
   - `fetch_web_content()`: Web content fetching via WebReader
   - `get_system_status()`: System health and status
   - `run_safety_check()`: Safety validation
   - `run_security_audit()`: Security audit
   - `run_once()`: **NEW** - Single deterministic iteration

## What Was Fixed

### 1) Initialization Order Bug ✅

**Before:**
- MutationEngine initialized with `trust_matrix=self.trust` before `self.trust` was created
- Would cause `AttributeError` or `NameError` at runtime

**After:**
- TrustMatrix initialized first
- MutationEngine initialized after TrustMatrix
- All components that depend on TrustMatrix are initialized after it

**Status:** ✅ Fixed

### 2) Added `run_once()` Method ✅

**Before:**
- No deterministic single-step entrypoint for testing
- Tests would need to run full initialization or mock complex loop structures

**After:**
- Added `run_once()` method that:
  - Runs one deterministic iteration
  - Performs safety check
  - Processes one high-priority task (if available)
  - Applies minimal trust decay
  - Returns structured result dict

**Status:** ✅ Added

### 3) WebReader Integration ✅

**Before:**
- WebReader initialized without ReviewQueue/ApprovalStore
- Review/replay workflows would not work for network access

**After:**
- WebReader initialized with TrustMatrix, ReviewQueue, ApprovalStore
- Review/replay workflows work correctly

**Status:** ✅ Fixed

## Behavioral Verification

### ✅ Construction Wiring

**Test:** `test_core_construction_wires_components_correctly()`

**Result:** PASS
- `core.trust` exists and is TrustMatrix
- `core.mutation.trust_matrix is core.trust` (same instance)
- `core.web_reader.trust_matrix is core.trust` (same instance)
- MutationEngine has ReviewQueue and ApprovalStore
- WebReader has ReviewQueue and ApprovalStore

**Status:** ✅ Correct

### ✅ Review Propagation

**Test:** `test_review_decision_propagates_to_review_queue()`

**Result:** PASS
- Review decision enqueues request
- `TrustReviewRequiredError` raised with request_id
- ReviewQueue receives entry

**Status:** ✅ Correct

### ✅ Deny Propagation

**Test:** `test_deny_decision_propagates_explicitly()`

**Result:** PASS
- Deny decision raises `TrustDeniedError`
- Exception includes reason_code
- Core does not proceed

**Status:** ✅ Correct

### ✅ No Direct External Actions

**Test:** `test_core_does_not_call_external_primitives_directly()`

**Result:** PASS
- `run_once()` does not call external primitives directly
- Core uses gateways for external actions
- Result structure is correct

**Status:** ✅ Correct (Core uses gateways, not direct calls)

### ✅ Mutation Integration

**Tests:**
- `test_governance_mutation_without_override_raises_exception()` - PASS
- `test_governance_mutation_with_review_enqueues_request()` - PASS
- `test_governance_mutation_approval_replay_succeeds()` - PASS

**Result:** All mutation integration tests pass
- Without override → `MutationDeniedError`
- With review → enqueues request, returns message with request_id
- With approval replay → mutation succeeds

**Status:** ✅ Correct

### ✅ RunOnce Method

**Test:** `test_run_once_exists_and_returns_result()`

**Result:** PASS
- `run_once()` exists and returns dict
- Result has required fields (timestamp, status, tasks_processed, health_checks)
- Method is deterministic (can be called multiple times)

**Status:** ✅ Correct

## Critical Issues

### None Found ✅

All critical issues have been fixed:
- ✅ Initialization order bug fixed
- ✅ `run_once()` method added
- ✅ WebReader integration fixed
- ✅ Component wiring verified
- ✅ Decision propagation verified

## Gaps and Limitations

### 1. No CONTROL.md Integration ✅ **FIXED**

**Before:** Core did not read CONTROL.md or automatically route tasks.

**After:** Core reads CONTROL.md and routes tasks deterministically.

**Implementation:**
- `_read_control_task()` reads and parses CONTROL.md
- `load_task_contract()` loads task contracts from TASKS/
- `run_once()` returns structured results (idle/ready/error)

**Status:** ✅ Fixed in TASK-0021

### 2. No FileWriter/SubprocessRunner Initialization

**Current:** Core initializes WebReader but not FileWriter or SubprocessRunner.

**Gap:** FileWriter and SubprocessRunner may be created on demand (not verified).

**Recommendation:** Either:
- Initialize FileWriter/SubprocessRunner in Core (like WebReader), or
- Document that they are created on demand and verify they receive TrustMatrix/ReviewQueue/ApprovalStore

**Status:** ⚠️ Documented, acceptable for current scope (WebReader is the primary gateway used by Core)

### 3. Exception Handling Returns Strings

**Current:** Core catches exceptions and returns string messages (for backward compatibility).

**Gap:** No structured result objects (like MutationResult for mutations).

**Recommendation:** Consider returning structured results in future (not required for current scope).

**Status:** ⚠️ Documented, acceptable for current scope (backward compatibility)

### 4. No Task Router

**Current:** Core has `propose_mutation()` but no automatic task routing.

**Gap:** No method to read CONTROL.md and route to appropriate handler.

**Recommendation:** Add task router in future (TASK-0021).

**Status:** ⚠️ Documented, acceptable for current scope

## Test Coverage

### Smoke Tests Added (`tests/test_core_smoke.py`)

✅ **Construction wiring** - PASS
✅ **Review propagation** - PASS
✅ **Deny propagation** - PASS
✅ **No direct external actions** - PASS
✅ **Mutation integration** (3 tests) - PASS
✅ **RunOnce method** - PASS

### Existing Tests (`tests/test_invariants.py`)

✅ Core governance protection (verifies Core uses gateways)

## Recommendations

### Immediate (TASK-0020)

1. ✅ Fix initialization order bug (DONE)
2. ✅ Add `run_once()` method (DONE)
3. ✅ Fix WebReader integration (DONE)
4. ✅ Add smoke tests (DONE)
5. ✅ Create spec and audit report (DONE)

### Future Enhancements

1. ✅ **CONTROL.md integration**: Implemented in TASK-0021
2. **FileWriter/SubprocessRunner initialization**: Initialize in Core (like WebReader) or document on-demand creation
3. **Structured results**: Return structured result objects instead of strings (for mutations, web fetching, etc.) - Note: run_once() now returns structured results
4. ✅ **Task router**: Implemented in TASK-0021
5. ✅ **Task execution engine**: Implemented in TASK-0022 (whitelisted task types only)
6. **Mutation execution as task**: Add task type for executing mutations (future enhancement)

## TASK-0022 Updates

### Task Execution Engine ✅

**Status:** ✅ Implemented

Core now executes whitelisted task types deterministically.

**Whitelisted Task Types:**
- `RUN_ACCEPTANCE`: Executes acceptance script (known safe subprocess path)
- `CLEAR_CURRENT_TASK`: Atomically sets CONTROL.md to NONE
- `APPLY_MUTATION`: Executes mutations via MutationEngine using payload files from `MUTATIONS/` ✅

**APPLY_MUTATION Preflight (TASK-0024):**
- Preflight phase validates all paths and checks TrustMatrix BEFORE any writes
- Prevents partial mutation applies (all-or-nothing guarantee)
- If `ALLOW_GOVERNANCE_MUTATION=false` and any path protected → deny immediately
- If `ALLOW_GOVERNANCE_MUTATION=true` → check TrustMatrix once for entire batch
- Replay handling: Check ApprovalStore first if `REQUEST_ID` provided
- **Guarantee**: No file writes unless entire batch is allowed/replay approved

**Safety:**
- No arbitrary command execution
- No markdown interpretation beyond single directive
- No string error returns (dict only)
- No network calls
- Path safety validation for mutation payloads (no .., no absolute paths, no outside repo root)
- **No partial applies**: Preflight ensures all-or-nothing mutation application

**Status:** ✅ Task execution complete (all whitelisted types implemented, preflight added)

**Subprocess Surface Unification (TASK-0025):**
- Core no longer calls `subprocess.run` directly
- All subprocess execution (including acceptance) goes through SubprocessRunner gateway
- SubprocessRunner initialized in Core with shared TrustMatrix, ReviewQueue, ApprovalStore
- Acceptance execution uses fixed command list and 300-second timeout
- Tests updated to mock SubprocessRunner instead of subprocess.run

## Conclusion

GuardianCore has been **audited** and **hardened**. All critical issues fixed (initialization order, WebReader integration). `run_once()` method added for deterministic testing. CONTROL.md integration and task execution engine implemented. All components properly wired, and Core correctly propagates deny/review/allow decisions. Remaining gaps are documented and acceptable for current scope.

**Status:** ✅ Audit complete, all critical issues fixed, task execution implemented

**Next Tasks Recommended:**
1. **TASK-0023:** Add mutation execution as task type
2. **TASK-0024:** Initialize FileWriter/SubprocessRunner in Core (or document on-demand creation)
3. **TASK-0025:** End-to-end workflow test (task → mutation → review → approval → replay)
