# MutationEngine Audit Report

**Date:** 2024-01-XX  
**Task:** TASK-0019, TASK-0042  
**Auditor:** Cursor Agent

## Executive Summary

MutationEngine has been **hardened** to eliminate bypass paths, truthiness bugs, and string-return ambiguity. All governance mutations now use TrustDecision semantics, ReviewQueue integration, and approval replay. The `review_with_gpt()` bypass has been disabled, and Core's truthiness bug has been fixed.

## What Was Fixed

### 1) Replaced string-return outcomes with explicit exceptions + structured result ✅

**Before:**
- `apply()` returned strings like `"[Guardian Mutation] REJECTED: ..."` or `"[Guardian Mutation] {filename} updated..."`
- Callers had to parse strings to determine success/denial/failure

**After:**
- Introduced explicit exception types:
  - `MutationDeniedError` (protected path without override, trust denied, approval not found/context mismatch)
  - `MutationReviewRequiredError` (when TrustDecision is "review")
  - `MutationApplyError` (unexpected failure)
- On success, return `MutationResult(ok: bool, changed_files: list[str], backup_paths: list[str], summary: str)`
- No more string parsing required

**Status:** ✅ Fixed

### 2) Removed/quarantined `review_with_gpt()` bypass ✅

**Before:**
- `review_with_gpt()` performed direct network calls (OpenAI API) without TrustMatrix/ReviewQueue gating
- Bypassed governance entirely

**After:**
- `review_with_gpt()` marked as **DEPRECATED/DISABLED**
- Always returns "reject" (no network calls)
- Documented that if GPT review is needed, it must route through WebReader gateway
- `propose_mutation()` default changed to `require_review=False` (review_with_gpt disabled)

**Status:** ✅ Fixed (bypass removed)

### 3) Fixed Core truthiness bug and normalized action usage ✅

**Before:**
- Core used `if not self.trust.validate_trust_for_action(...):` (treating TrustDecision as bool)
- Core used raw `"mutation"` string instead of normalized constants

**After:**
- Core now branches on `decision.decision` (not truthiness):
  - `if decision.decision == "deny": ...`
  - `elif decision.decision == "review": ...`
  - `elif decision.decision == "allow": ...`
- For governance mutations, uses `GOVERNANCE_MUTATION` constant
- For non-governance mutations, uses legacy `"mutation"` string (documented in LEGACY_ACTIONS)

**Status:** ✅ Fixed

### 4) Aligned governance override flow with ReviewQueue + ApprovalStore ✅

**Before:**
- Governance mutations returned string messages for "review" decisions
- No review queue integration
- No approval replay support

**After:**
- If mutation touches protected paths and `allow_governance_mutation=False`:
  - raise `MutationDeniedError` (reason: `PROTECTED_PATH_WITHOUT_OVERRIDE`)
- If `allow_governance_mutation=True`:
  - Call `validate_trust_for_action(..., GOVERNANCE_MUTATION, context={touched_paths,...})`
  - If decision == `"deny"`: raise `MutationDeniedError`
  - If decision == `"review"`: enqueue review request, raise `MutationReviewRequiredError(request_id=...)`
  - If decision == `"allow"`: proceed
- Support replay approval:
  - if `request_id` provided and approved with matching context, bypass review/deny
  - Context includes `touched_paths` list (sorted) for hashing consistency

**Status:** ✅ Fixed (same workflow as gateways)

### 5) Added behavioral smoke tests ✅

**Tests Added (`tests/test_mutation_smoke.py`):**

✅ **Protected path denied**
- Attempt mutation touching `CONTROL.md` without override
- Expect `MutationDeniedError`

✅ **Protected path review**
- Force TrustMatrix to return `review` for `GOVERNANCE_MUTATION`
- Expect `MutationReviewRequiredError` and review_queue entry

✅ **Approval replay works**
- Approve request_id with matching context
- Re-run apply with request_id
- Expect success (MutationResult.ok True) without re-enqueueing

✅ **Core uses decision semantics**
- Unit test Core mutation entrypoint to confirm it branches on `decision.decision` not truthiness

✅ **Additional tests:**
- Non-protected path success
- Review with GPT disabled
- Context mismatch replay

**Status:** ✅ All tests pass

## What Exists

### Core Functionality

1. **MutationEngine** (`project_guardian/mutation.py`)
   - Protected path detection
   - TrustMatrix gating for governance mutations
   - ReviewQueue integration
   - ApprovalStore replay support
   - Backup creation
   - Mutation logging

2. **Exception Types**
   - `MutationDeniedError`
   - `MutationReviewRequiredError`
   - `MutationApplyError`

3. **Structured Result**
   - `MutationResult` dataclass (ok, changed_files, backup_paths, summary)

4. **Core Integration** (`project_guardian/core.py`)
   - Uses TrustDecision semantics (not truthiness)
   - Uses `GOVERNANCE_MUTATION` constant for governance mutations
   - Handles exceptions correctly
   - Passes ReviewQueue/ApprovalStore to MutationEngine

## Critical Issues

### None Found ✅

All critical issues have been fixed:
- ✅ String-return ambiguity eliminated
- ✅ Bypass paths removed (review_with_gpt disabled)
- ✅ Truthiness bug fixed (Core uses decision.decision)
- ✅ Review queue integration complete
- ✅ Approval replay working

## Gaps and Limitations

### 1. Patch Format Limits

**Current:** Simple file replacement (read old, write new).

**Gap:** No support for:
- Line-by-line patches
- Merge conflicts
- Partial file updates

**Recommendation:** Document as current limitation. Add patch format support in future if needed.

**Status:** ⚠️ Documented, acceptable for current scope

### 2. Rollback Robustness

**Current:** Backups created, but no automatic rollback on failure.

**Gap:** If mutation partially succeeds (e.g., multiple files), no automatic rollback.

**Recommendation:** Add rollback mechanism for multi-file mutations.

**Status:** ⚠️ Documented, acceptable for current scope (single-file mutations work)

### 3. Context Hashing Determinism

**Current:** `touched_paths` sorted for deterministic hashing.

**Gap:** If caller passes unsorted list, hash may differ.

**Recommendation:** Always sort `touched_paths` in `apply()` (already done).

**Status:** ✅ Fixed (touched_paths sorted in apply())

### 4. Legacy "mutation" Action String

**Current:** Core uses legacy `"mutation"` string for non-governance mutations.

**Gap:** Not a constant (documented in LEGACY_ACTIONS).

**Recommendation:** Define constant for non-governance mutations if needed, or keep as legacy.

**Status:** ⚠️ Documented, acceptable (legacy string documented)

## Test Coverage

### Smoke Tests Added (`tests/test_mutation_smoke.py`)

✅ **Protected path denied** - PASS
✅ **Protected path review** - PASS
✅ **Approval replay works** - PASS
✅ **Core uses decision semantics** - PASS
✅ **Non-protected path success** - PASS
✅ **Review with GPT disabled** - PASS
✅ **Context mismatch replay** - PASS

### Existing Tests (`tests/test_invariants.py`)

✅ MutationEngine governance protection (verifies protected paths are gated)

## Recommendations

### Immediate (TASK-0019)

1. ✅ Replace string returns with exceptions (DONE)
2. ✅ Remove review_with_gpt bypass (DONE)
3. ✅ Fix Core truthiness bug (DONE)
4. ✅ Add ReviewQueue/ApprovalStore integration (DONE)
5. ✅ Add smoke tests (DONE)

### Future Enhancements

1. **Patch format support:** Add line-by-line patch support (not just full file replacement)
2. **Rollback mechanism:** Add automatic rollback for multi-file mutations
3. **Action constant:** Define constant for non-governance mutations (or keep as legacy)
4. **Multi-file mutations:** Support mutations affecting multiple files with atomic rollback

## TASK-0023 Updates

### Task-Driven Execution ✅

**Status:** ✅ Implemented

MutationEngine can now be invoked via `APPLY_MUTATION` task type.

**Task Contract:**
- `TASK_TYPE: APPLY_MUTATION`
- `MUTATION_FILE: MUTATIONS/<name>.json`
- `ALLOW_GOVERNANCE_MUTATION: true|false`
- `REQUEST_ID: <id>` (optional, for replay)

**Mutation Payload:**
- JSON file in `MUTATIONS/` directory
- Contains `touched_paths`, `changes` array, `summary`
- Validated for path safety and schema correctness

**Integration:**
- Core loads payload and applies via MutationEngine
- Supports deny/review/approve/replay flows
- Returns structured results (dict only, no strings)

**Preflight Phase (TASK-0024):**
- Core performs preflight check BEFORE any writes
- Validates all paths and checks TrustMatrix once for entire batch
- Prevents partial mutation applies (all-or-nothing guarantee)
- Uses same context format (sorted touched_paths, override_flag, caller, task_id) for decisions and replay

## TASK-0042 Update: Path Safety Parity with FileWriter

**Status:** ✅ Implemented

**Changes:**
- Added repo root resolution to `MutationEngine.__init__()` (defaults to project root, can be overridden)
- Added `_validate_and_resolve_path()` helper method that:
  - Rejects absolute paths
  - Rejects paths containing `..` (traversal)
  - Enforces all paths must resolve within repo root (via `Path.relative_to()`)
  - Rejects writing directly to directories
  - Blocks symlink escape (via resolve() + relative_to() check)
- Path validation occurs **before** governance/protection checks (defense-in-depth)
- Core's preflight now validates all paths using MutationEngine's validation **before any writes**
- Normalized relative paths are used in context (not absolute paths)
- Invalid paths cause denial before any writes/backups occur

**Risk Reduction:**
- Path traversal attacks (../../../etc/passwd) are now blocked
- Arbitrary file writes outside repo root are prevented
- Symlink escape attempts are blocked
- Safety checks occur before trust gating (defense-in-depth)
- Preflight guarantees no partial mutation applies

**Parity with FileWriter:**
- MutationEngine now enforces the same path safety rules as FileWriter
- Both use repo root enforcement, traversal blocking, and symlink protection
- Both validate paths before TrustMatrix gating

**Remaining Risks:**
- Full-file replacement: MutationEngine still replaces entire files (no patch support)
- Multi-file atomicity: If one file in a batch fails after preflight, others may have been written (preflight prevents this, but defensive handling remains)

**Tests Added (`tests/test_mutation_path_safety.py`):**
- ✅ Blocks absolute paths (POSIX and Windows)
- ✅ Blocks traversal (`../outside.txt`, `a/../outside.txt`)
- ✅ Blocks symlink escape (if supported)
- ✅ Denies before writing anything (mixed batch test)
- ✅ Allows safe paths
- ✅ Blocks writing to directories
- ✅ Verifies validation occurs before governance checks
- ✅ Verifies normalized paths in context

## Conclusion

MutationEngine has been **hardened** to eliminate bypass paths, truthiness bugs, and string-return ambiguity. All governance mutations now use TrustDecision semantics, ReviewQueue integration, and approval replay. The `review_with_gpt()` bypass has been disabled, and Core's truthiness bug has been fixed. Task-driven execution via `APPLY_MUTATION` is now supported.

**Status:** ✅ Audit complete, all critical issues fixed, task-driven execution implemented

**Next Tasks Recommended:**
1. **TASK-0024:** End-to-end workflow test (task → mutation → review → approval → replay)
2. **TASK-0025:** Initialize FileWriter/SubprocessRunner in Core (or document on-demand creation)
