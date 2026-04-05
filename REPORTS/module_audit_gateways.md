# External Action Gateways Audit Report

**Date:** 2024-01-XX  
**Task:** TASK-0018  
**Auditor:** Cursor Agent

## Executive Summary

All three gateways (WebReader, FileWriter, SubprocessRunner) are **functionally correct** and properly enforce TrustMatrix gating, review queue integration, and approval replay. Context safety is good (only safe data stored), and forbidden patterns are avoided.

## What Exists

### Core Gateways

1. **WebReader** (`project_guardian/external.py`)
   - Network access gateway
   - Uses `NETWORK_ACCESS` constant
   - Context: domain only (not full URL)
   - Timeout: 10 seconds

2. **FileWriter** (`project_guardian/file_writer.py`)
   - Filesystem write gateway
   - Uses `FILE_WRITE` constant
   - Context: filename only (not full path)
   - Modes: "w", "a", "wb", "ab" only

3. **SubprocessRunner** (`project_guardian/subprocess_runner.py`)
   - Subprocess execution gateway
   - Uses `SUBPROCESS_EXECUTION` constant
   - Context: command name + arg count (not arguments)
   - Timeout: 30 seconds
   - **No shell=True** (verified safe)

### Integration Points

- All gateways call `TrustMatrix.validate_trust_for_action()` with action constants
- All gateways call `review_queue.enqueue()` when `decision == "review"`
- All gateways call `approval_store.is_approved()` for replay checks
- All gateways raise explicit exceptions (`TrustDeniedError`, `TrustReviewRequiredError`)

## Behavioral Verification

### ✅ WebReader Deny Path

**Test:** `test_deny_raises_exception_no_network_call()`

**Result:** PASS
- Deny decision raises `TrustDeniedError`
- Network call (requests.Session.get) is NOT made
- Exception includes correct reason_code and action constant

**Status:** ✅ Correct

### ✅ WebReader Review Path

**Test:** `test_review_enqueues_request_and_raises_exception()`

**Result:** PASS
- Review decision enqueues request to ReviewQueue
- Raises `TrustReviewRequiredError` with request_id
- Network call is NOT made
- Stored context contains only domain (not full URL)

**Status:** ✅ Correct

### ✅ WebReader Approval Replay

**Test:** `test_approved_replay_bypasses_review()`

**Result:** PASS
- Approved request_id bypasses review
- Network call is made (mocked, not real internet)
- Context matching works correctly

**Status:** ✅ Correct

### ✅ WebReader Context Safety

**Test:** `test_context_contains_only_domain_not_full_url()`

**Result:** PASS
- Context contains only domain ("example.com")
- Query strings NOT stored
- Sensitive data (token, api_key) NOT stored
- URL path NOT stored

**Status:** ✅ Correct

### ✅ FileWriter Deny Path

**Test:** `test_deny_raises_exception_no_write()`

**Result:** PASS
- Deny decision raises `TrustDeniedError`
- File write does NOT occur
- Exception includes correct reason_code and action constant

**Status:** ✅ Correct

### ✅ FileWriter Review Path

**Test:** `test_review_enqueues_request_and_raises_exception()`

**Result:** PASS
- Review decision enqueues request
- Raises `TrustReviewRequiredError` with request_id
- File write does NOT occur

**Status:** ✅ Correct

### ✅ FileWriter Approval Replay

**Test:** `test_approved_replay_allows_write()`

**Result:** PASS
- Approved request_id allows write to temp file
- File content matches
- Result message confirms success

**Status:** ✅ Correct

### ✅ FileWriter Mode Restrictions

**Test:** `test_allowed_modes_work()`, `test_invalid_mode_raises_error()`

**Result:** PASS
- Allowed modes ("w", "a", "wb", "ab") work correctly
- Invalid mode ("x") raises `ValueError`

**Status:** ✅ Correct

### ✅ SubprocessRunner Deny Path

**Test:** `test_deny_raises_exception_no_subprocess()`

**Result:** PASS
- Deny decision raises `TrustDeniedError`
- Subprocess.run is NOT called
- Exception includes correct reason_code and action constant

**Status:** ✅ Correct

### ✅ SubprocessRunner Review Path

**Test:** `test_review_enqueues_request_and_raises_exception()`

**Result:** PASS
- Review decision enqueues request
- Raises `TrustReviewRequiredError` with request_id
- Subprocess.run is NOT called

**Status:** ✅ Correct

### ✅ SubprocessRunner Approval Replay

**Test:** `test_approved_replay_allows_subprocess()`

**Result:** PASS
- Approved request_id allows subprocess.run to be called (mocked)
- Command and timeout verified
- Result structure correct

**Status:** ✅ Correct

### ✅ SubprocessRunner Timeout

**Test:** `test_timeout_raises_trust_denied_error()`

**Result:** PASS
- Timeout raises `TrustDeniedError`
- Uses `SUBPROCESS_EXECUTION` constant (not hardcoded string)
- Reason code is "COMMAND_TIMEOUT"

**Status:** ✅ Correct

### ✅ SubprocessRunner Forbidden Patterns

**Test:** `test_shell_true_not_allowed()`

**Result:** PASS
- `subprocess.run()` is called WITHOUT `shell=True` (forbidden pattern avoided)
- Timeout is enforced (30 seconds)
- Command list format used (not shell string)

**Status:** ✅ Correct (no shell=True found)

## Critical Issues

### None Found ✅

All gateways correctly:
- Enforce TrustMatrix gating
- Integrate with review queue
- Support approval replay
- Store safe context only
- Avoid forbidden patterns

## Gaps and Limitations

### 1. WebReader: SSRF Safety Floor (TASK-0038) ✅

**Current:** WebReader enforces SSRF safety floor:
- Scheme validation: Only `http://` and `https://` allowed
- Internal target blocking: Loopback, private IPs, link-local, localhost, `.local` hostnames blocked by default
- Override path: `allow_internal=True` requires TrustMatrix review/approval (cannot auto-allow)

**Status:** ✅ Implemented in TASK-0038

**Remaining Limitations:**
- No DNS resolution: Hostname validation only checks patterns (localhost, .local), not actual IP resolution
- Hostname bypass: If a hostname resolves to an internal IP but is not in the blocklist patterns, it may pass (DNS resolution not performed)
- IPv6 support: Full IPv6 range checking implemented, but no DNS resolution for IPv6 hostnames

**Recommendation:** Consider DNS resolution for hostnames in future (requires async networking or blocking DNS lookup)

### 2. FileWriter: No Path Traversal Protection

**Status:** ✅ Implemented in TASK-0041

**Current:** FileWriter now enforces strict path safety:
- Absolute paths rejected
- Traversal (`..`) blocked
- Repo root enforcement (all paths must resolve within repo root)
- Directory writes blocked
- Path validation occurs before TrustMatrix gating (defense-in-depth)
- Symlink protection via resolve() + relative_to() check

**Risk Reduction:**
- Path traversal attacks (../../../etc/passwd) are now blocked
- Arbitrary file writes outside repo root are prevented
- Safety checks occur before trust gating (defense-in-depth)

### 3. SubprocessRunner: No Command Validation

**Current:** Command list is passed directly to `subprocess.run()`.

**Gap:** Dangerous commands (rm -rf, format, etc.) are not blocked at gateway level.

**Recommendation:** Add command allowlist or blocklist (or rely on TrustMatrix trust levels).

**Status:** ⚠️ Documented, acceptable for current scope (TrustMatrix provides policy layer)

### 4. Context Storage: No Explicit Redaction

**Current:** Gateways manually construct context with safe fields only.

**Gap:** If caller passes sensitive data in context, it may leak (though current implementation avoids this).

**Recommendation:** Add explicit context redaction function (shared across gateways).

**Status:** ⚠️ Documented, acceptable for current scope (current implementation is safe)

## Test Coverage

### Smoke Tests Added (`tests/test_gateways_smoke.py`)

✅ **WebReader:**
- Deny path (no network call)
- Review path (enqueue + exception)
- Approval replay (bypass + network call)
- Context safety (domain only)

✅ **FileWriter:**
- Deny path (no write)
- Review path (enqueue + exception)
- Approval replay (bypass + write)
- Mode restrictions (allowed modes only)

✅ **SubprocessRunner:**
- Deny path (no subprocess)
- Review path (enqueue + exception)
- Approval replay (bypass + subprocess)
- Timeout behavior (TrustDeniedError with constant)
- Forbidden patterns (no shell=True)

### Existing Tests (`tests/test_invariants.py`)

✅ AST-based bypass detection (verifies all external actions go through gateways)
✅ Trust gating verification
✅ Review workflow tests

## Recommendations

### Immediate (TASK-0018)

1. ✅ Verify deny paths (DONE)
2. ✅ Verify review paths (DONE)
3. ✅ Verify approval replay (DONE)
4. ✅ Verify context safety (DONE)
5. ✅ Verify forbidden patterns (DONE)

### Future Enhancements

1. ✅ **URL validation:** Implemented in TASK-0038 (SSRF safety floor)
2. **DNS resolution:** Add DNS resolution for hostnames to detect internal IPs (requires async networking or blocking DNS lookup)
3. ✅ **Path sanitization:** Implemented in TASK-0041 (path traversal protection for FileWriter)
4. **Command validation:** Add command allowlist/blocklist for SubprocessRunner
5. **Context redaction:** Add shared context redaction function
6. **Rate limiting:** Add rate limits per component/action type

## TASK-0025 Update: Subprocess Surface Unification

**Status:** ✅ Core now uses SubprocessRunner for all subprocess execution

**Changes:**
- Core no longer calls `subprocess.run` directly
- Acceptance execution (`RUN_ACCEPTANCE` task) now goes through SubprocessRunner
- SubprocessRunner initialized in Core with shared TrustMatrix, ReviewQueue, ApprovalStore
- SubprocessRunner supports configurable timeout (default: 30s, acceptance: 300s)
- Tests updated to mock SubprocessRunner instead of subprocess.run

**Impact:**
- Single subprocess surface enforced (no drift)
- All subprocess execution gated through TrustMatrix
- Review/approval workflow applies to acceptance execution (if policy dictates)

## TASK-0039 Update: Background Subprocess Audit Trail

**Status:** ✅ Background subprocess launches are now auditable via append-only JSONL

**Changes:**
- Added audit log at `REPORTS/subprocess_background.jsonl` (append-only JSONL format)
- Each successful background launch appends one JSON line with:
  - Timestamp, PID, command (redacted), CWD, caller_identity, task_id, request_id, action, decision, notes
- Command argument redaction: Sensitive keywords (token, key, secret, password, api_key, auth) trigger redaction
- Audit write failures do not crash subprocess calls (best-effort)
- Deny/review paths do not write audit lines (only successful launches)

**Risk Reduction:**
- Background processes are now observable and attributable
- Reduces "fire-and-forget" risk
- Provides audit trail for security analysis

**Impact:**
- All background subprocess launches are logged
- Audit log is append-only (durable, tamper-evident)
- Redaction prevents sensitive data leakage in audit logs

## TASK-0038 Update: SSRF Safety Floor

**Status:** ✅ WebReader now enforces SSRF safety floor

**Changes:**
- Scheme validation: Only `http://` and `https://` allowed (raises `TrustDeniedError` with `UNSUPPORTED_URL_SCHEME`)
- Internal target blocking: Blocks loopback, private IPs, link-local, localhost, `.local` hostnames by default
- Override path: `allow_internal=True` parameter added to `fetch()` and `request_json()`
- Override still requires TrustMatrix review/approval (cannot auto-allow internal targets)
- Context includes `scheme`, `allow_internal`, and `blocked_reason` for audit

**Risk Reduction:**
- Prevents obvious SSRF attacks (file://, loopback, private IPs)
- Defense-in-depth: Even if TrustMatrix misconfigured, internal targets blocked by default
- Override path requires explicit opt-in AND TrustMatrix approval

**Known Limitations:**
- No DNS resolution: Hostname validation only checks patterns, not actual IP resolution
- Hostname bypass possible: If hostname resolves to internal IP but not in blocklist patterns, may pass

**Impact:**
- Significant SSRF risk reduction
- Internal targets require explicit opt-in AND review/approval
- All network requests validated before TrustMatrix gating

## Conclusion

All three gateways are **functionally correct** and properly enforce TrustMatrix gating, review queue integration, and approval replay. Context safety is good (only safe data stored), and forbidden patterns are avoided. WebReader now includes SSRF safety floor (TASK-0038). No critical issues found.

**Status:** ✅ Audit complete, minor gaps documented

**Next Tasks Recommended:**
1. **TASK-0019:** MutationEngine audit
2. **TASK-0020:** Core system audit (GuardianCore integration)
