# TASKS 0010 & 0011 Complete ✅

## Summary

Bypass detection hardened with AST-based scanning and scoped gateway allowlists. Explicit gateway modules created for filesystem and subprocess operations.

---

## TASK-0010: AST-Based Bypass Detection

### What Changed

**Before (Regex-Based):**
- Scanned text for patterns like `r"import requests"`
- Missed aliased imports (`import requests as r`)
- Missed indirect calls (`__import__("requests")`)
- File-level allowlist (entire files approved)

**After (AST-Based):**
- Uses `ast.parse()` and `ast.NodeVisitor` to parse Python files
- Detects aliased imports, indirect calls, wrapper functions
- Function-level allowlist (specific gateway functions only)
- Reports violations with file:line:symbol precision

### Gateway Allowlists

**Network Gateways:**
- `project_guardian/external.py::WebReader.fetch()`

**File Write Gateways:**
- `project_guardian/mutation.py::MutationEngine.apply()`
- `project_guardian/file_writer.py::FileWriter.write_file()` (added in TASK-0011)

**Subprocess Gateways:**
- `project_guardian/subprocess_runner.py::SubprocessRunner.run_command()` (added in TASK-0011)

### Violation Reporting

Example output:
```
INVARIANT VIOLATION: Found ungated network calls:
  project_guardian/some_module.py:42 - import requests (network_import)
  project_guardian/other.py:15 - requests.get() (network_call)

All network calls must be within approved gateway functions:
  - project_guardian/external.py::WebReader.fetch
```

### Result

✅ **Robust bypass detection** - catches aliased imports, indirect calls  
✅ **Scoped allowlist** - prevents dumping code into approved files  
✅ **Precise reporting** - file:line:symbol for each violation

---

## TASK-0011: External Action Gateway Interfaces

### What Was Created

**1. FileWriter Gateway (`project_guardian/file_writer.py`):**
```python
class FileWriter:
    def write_file(
        self,
        file_path: str,
        content: str,
        mode: str = "w",
        caller_identity: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> str:
        # Gates through TrustMatrix
        # Raises TrustDeniedError on denial/review
```

**2. SubprocessRunner Gateway (`project_guardian/subprocess_runner.py`):**
```python
class SubprocessRunner:
    def run_command(
        self,
        command: List[str],
        caller_identity: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        # Gates through TrustMatrix (system_change action)
        # Denies by default unless explicitly approved
        # Includes safety timeout (30 seconds)
```

### Gateway Contracts

Both gateways:
- Require TrustMatrix instance
- Build context (target, caller, task_id)
- Call `validate_trust_for_action()` with context
- Raise `TrustDeniedError` on deny/review
- Log operations to memory
- Return structured results

### Updated Allowlist

Bypass detection now permits:
- File writes in `FileWriter.write_file()`
- Subprocess calls in `SubprocessRunner.run_command()`

### Result

✅ **Centralized policy enforcement** - all external actions go through gateways  
✅ **Consistent gating** - same TrustMatrix contract everywhere  
✅ **Future-proof** - easy to add new gateways

---

## Files Modified

1. `tests/test_invariants.py` - AST-based scanning, scoped allowlists
2. `project_guardian/file_writer.py` - New gateway module
3. `project_guardian/subprocess_runner.py` - New gateway module
4. `CHANGELOG.md` - Updated
5. `REPORTS/AGENT_REPORT.md` - Complete reports
6. `CONTROL.md` - Set to NONE

---

## Verification

### Test AST-Based Detection

```python
# Create a test file with ungated network call
# test_bypass.py:
import requests  # Should be detected

# Run bypass detection
pytest tests/test_invariants.py::TestInvariant5_BypassDetection -v
# Should FAIL with file:line:symbol
```

### Test Gateway Modules

```python
from project_guardian.file_writer import FileWriter
from project_guardian.subprocess_runner import SubprocessRunner
from project_guardian.memory import MemoryCore
from project_guardian.trust import TrustMatrix

memory = MemoryCore()
trust = TrustMatrix(memory)

# FileWriter
writer = FileWriter(memory, trust_matrix=trust)
# Will gate through TrustMatrix

# SubprocessRunner
runner = SubprocessRunner(memory, trust_matrix=trust)
# Will gate through TrustMatrix (denies by default)
```

---

## Acceptance Criteria Met

### TASK-0010:
- ✅ AST-based scanning (no regex)
- ✅ Detects aliased imports, indirect calls
- ✅ Scoped allowlist (function-level, not file-level)
- ✅ Precise violation reporting (file:line:symbol)
- ✅ acceptance.ps1 fails on bypass

### TASK-0011:
- ✅ FileWriter gateway defined
- ✅ SubprocessRunner gateway defined
- ✅ Both gate through TrustMatrix
- ✅ Bypass detection allowlist updated
- ✅ Tests pass

---

## Note on "review" Decision Handling

**Current Implementation:**
- Raises `TrustDeniedError` with `requires_review: True` flag
- Halts execution (strict)

**Future Option (Autonomy-Friendly):**
- Queue human review task in request queue
- Continue with degraded permissions or wait for review
- Enables meaningful autonomy without babysitting

**Recommendation:**
- Implement queue-based review after gateway surface is tight
- Gateway surface is now tight (TASK-0010/0011 complete)
- Ready for queue-based review implementation

---

**Both tasks completed! Bypass detection is robust and gateway surface is tight.** ✅
