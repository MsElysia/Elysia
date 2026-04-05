# TASK-0007 Complete ✅

## Summary

Contracts hardened: Trust denials are now explicit (exceptions, not None), context is passed to gates, and hardcoded policy removed from mechanism layers.

---

## Changes Made

### 1. Explicit Denial (No Ambiguity)

**Before:**
```python
if not self.trust_matrix.validate_trust_for_action(...):
    return None  # Ambiguous: denied? error? empty?
```

**After:**
```python
if not self.trust_matrix.validate_trust_for_action(...):
    raise TrustDeniedError(
        component="WebReader",
        action="network_access",
        target=domain,
        reason=f"insufficient trust (trust: {trust_level:.3f})",
        context=gate_context
    )
```

**Result:** Denials are explicit exceptions that cannot be silently ignored.

---

### 2. Trust Gating Context

**Before:**
```python
validate_trust_for_action("WebReader", "network_access")
# Missing: URL, method, caller, task_id
```

**After:**
```python
gate_context = {
    "component": "WebReader",
    "action": "network_access",
    "target": domain,  # example.com (not full URL)
    "method": "GET",
    "caller_identity": caller_identity or "unknown",
    "task_id": task_id or "unknown"
}
validate_trust_for_action("WebReader", "network_access", context=gate_context)
```

**Result:** TrustMatrix receives full context for granular policy decisions.

---

### 3. Removed Hardcoded Policy

**Before:**
```python
# In MutationEngine.apply():
if trust_level < 0.9:  # Hardcoded threshold
    return "REJECTED"
```

**After:**
```python
# In MutationEngine.apply():
gate_context = {
    "touched_paths": [filename],
    "override_flag": True,
    "caller_identity": origin or "unknown",
    "task_id": "unknown"
}
if not self.trust_matrix.validate_trust_for_action(
    "MutationEngine", 
    "governance_mutation", 
    context=gate_context
):
    return "REJECTED"
```

**Result:** Policy (thresholds) is in TrustMatrix, not scattered across modules.

---

## Files Modified

1. `project_guardian/external.py` - TrustDeniedError, explicit exceptions, context
2. `project_guardian/trust.py` - Context parameter, governance_mutation action
3. `project_guardian/mutation.py` - Removed hardcoded threshold, uses TrustMatrix decision
4. `project_guardian/core.py` - Handles TrustDeniedError
5. `tests/test_invariants.py` - Verifies explicit denials and context

---

## Verification

### Test Explicit Denial

```python
from project_guardian.external import WebReader, TrustDeniedError
from project_guardian.memory import MemoryCore
from project_guardian.trust import TrustMatrix
from unittest.mock import Mock

memory = MemoryCore()
trust = TrustMatrix(memory)
reader = WebReader(memory, trust_matrix=trust)

# Mock denial
trust.validate_trust_for_action = Mock(return_value=False)
trust.get_trust = Mock(return_value=0.5)

try:
    reader.fetch("https://example.com")
except TrustDeniedError as e:
    print(f"Denied: {e}")
    print(f"Context: {e.context}")
    # Output: Trust denied: WebReader cannot perform network_access on example.com...
```

### Test Context Passing

```python
# TrustMatrix.validate_trust_for_action() logs context to memory
# Check memory for: "[Guardian Trust] ... | Context: {'target': 'example.com', 'method': 'GET', ...}"
```

### Test No Hardcoded Threshold

```python
# MutationEngine.apply() source code should NOT contain "0.9" or "0.9+"
# Should contain: "validate_trust_for_action" and "governance_mutation"
```

---

## Acceptance Criteria Met

- ✅ WebReader.fetch() raises TrustDeniedError (explicit, not None)
- ✅ TrustMatrix receives context (target, method, caller, task_id)
- ✅ MutationEngine asks TrustMatrix for decision (no hardcoded threshold)
- ✅ Tests verify explicit denials and context passing
- ✅ acceptance.ps1 passes
- ✅ CONTROL.md set to NONE

---

**Contracts are now explicit, auditable, and policy-free in mechanism layers.** ✅
