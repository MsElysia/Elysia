# TASK-0005 & TASK-0006 Complete ✅

## Summary

Both tasks completed successfully. Governance invariants are now **enforced in code**, not just tested.

---

## TASK-0005: Trust Gating in WebReader.fetch()

### Changes Made

1. **project_guardian/external.py:**
   - Added `trust_matrix` parameter to `WebReader.__init__()`
   - Added trust gating in `WebReader.fetch()` before network calls
   - Gate uses `TrustMatrix.validate_trust_for_action("WebReader", "network_access")`
   - Returns `None` if gate denies (no network call made)

2. **project_guardian/core.py:**
   - Updated `GuardianCore.__init__()` to pass `self.trust` to `WebReader()`

3. **tests/test_invariants.py:**
   - Updated test to verify actual trust gating implementation
   - Tests that WebReader has trust_matrix attribute and gates through it

### Trust Gate Flow

```
WebReader.fetch(url)
  ↓
Check if trust_matrix is None → DENY if missing
  ↓
Call trust_matrix.validate_trust_for_action("WebReader", "network_access")
  ↓
If False → Return None, log denial
If True → Proceed with network request
```

### Result

✅ **WebReader.fetch() now gates through TrustMatrix**  
✅ **Invariant test passes**  
✅ **No network calls without trust approval**

---

## TASK-0006: Governance Protection in MutationEngine.apply()

### Changes Made

1. **project_guardian/mutation.py:**
   - Added `PROTECTED_GOVERNANCE_PATHS` constant (CONTROL.md, SPEC.md, core modules)
   - Added `PROTECTED_DIRECTORIES` constant (TASKS/, REPORTS/, scripts/, tests/)
   - Added `_is_protected_path()` method to check if file is protected
   - Added `trust_matrix` parameter to `MutationEngine.__init__()`
   - Added `allow_governance_mutation` parameter to `apply()`
   - Added governance protection logic in `apply()`:
     - Rejects protected files if no override
     - Requires TrustMatrix approval if override present
     - Override requires 0.9+ trust for "system_change" action

2. **project_guardian/core.py:**
   - Updated `GuardianCore.__init__()` to pass `self.trust` to `MutationEngine()`

3. **tests/test_invariants.py:**
   - Updated test to verify actual governance protection
   - Tests rejection without override flag

### Protected Paths

**Files:**
- CONTROL.md, SPEC.md, CHANGELOG.md
- project_guardian/core.py, trust.py, mutation.py, safety.py, consensus.py

**Directories:**
- TASKS/, REPORTS/, scripts/, tests/

### Governance Protection Flow

```
MutationEngine.apply(filename, allow_governance_mutation=False)
  ↓
Check if filename is protected
  ↓
If protected and no override → REJECT, return error
  ↓
If protected and override=True:
  ↓
  Check TrustMatrix.validate_trust_for_action("MutationEngine", "system_change")
  ↓
  If trust < 0.9 → REJECT, return error
  If trust >= 0.9 → APPROVE, proceed with mutation
```

### Result

✅ **MutationEngine.apply() protects governance files**  
✅ **Invariant test passes**  
✅ **Governance files cannot be mutated without override + TrustMatrix approval**

---

## Verification

### Test WebReader Gating

```python
from project_guardian.external import WebReader
from project_guardian.memory import MemoryCore
from project_guardian.trust import TrustMatrix

memory = MemoryCore()
trust = TrustMatrix(memory)
reader = WebReader(memory, trust_matrix=trust)

# If trust < 0.7 for network_access:
result = reader.fetch("https://example.com")
# Returns None, no network call made
```

### Test MutationEngine Protection

```python
from project_guardian.mutation import MutationEngine
from project_guardian.memory import MemoryCore

memory = MemoryCore()
mutation = MutationEngine(memory)

# Without override:
result = mutation.apply("CONTROL.md", "# test", allow_governance_mutation=False)
# Returns: "[Guardian Mutation] REJECTED: CONTROL.md is a protected governance file..."

# With override but insufficient trust:
result = mutation.apply("CONTROL.md", "# test", allow_governance_mutation=True)
# Returns: "[Guardian Mutation] REJECTED: ... insufficient trust for system_change"
```

---

## Files Modified

1. `project_guardian/external.py` - Trust gating in WebReader
2. `project_guardian/mutation.py` - Governance protection in MutationEngine
3. `project_guardian/core.py` - Pass TrustMatrix to WebReader and MutationEngine
4. `tests/test_invariants.py` - Updated behavioral tests
5. `CHANGELOG.md` - Updated with both tasks
6. `REPORTS/AGENT_REPORT.md` - Complete execution reports
7. `CONTROL.md` - Set to NONE after completion

---

## Acceptance Criteria Met

### TASK-0005:
- ✅ WebReader.fetch() gates through TrustMatrix
- ✅ Invariant test passes
- ✅ acceptance.ps1 passes
- ✅ CONTROL.md set to NONE

### TASK-0006:
- ✅ MutationEngine.apply() protects governance files
- ✅ Invariant test passes
- ✅ acceptance.ps1 passes
- ✅ CONTROL.md set to NONE

---

**Both tasks completed! Governance is now enforced in code, not just tested.** ✅
