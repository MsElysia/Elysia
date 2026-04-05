# TASK-0012 Complete ✅

## Summary

Review queue system implemented. "Review" decisions now create durable review requests instead of hard halting, enabling forward motion while maintaining veto power.

---

## What Was Created

### 1. ReviewQueue (`project_guardian/review_queue.py`)
- File-backed append-only JSONL queue
- Stores: `REPORTS/review_queue.jsonl`
- Methods:
  - `enqueue(component, action, context)` → request_id
  - `list_pending()` → List[ReviewRequest]
  - `get_request(request_id)` → ReviewRequest
  - `update_status(request_id, status)` → bool

### 2. ApprovalStore (`project_guardian/approval_store.py`)
- File-backed JSON map
- Stores: `REPORTS/approval_store.json`
- Maps: request_id → ApprovalRecord
- Methods:
  - `approve(request_id, context, approver, notes)` → bool
  - `deny(request_id, approver, notes)` → bool
  - `is_approved(request_id, context)` → bool (with context matching)
  - `get_approval(request_id)` → ApprovalRecord

### 3. ReviewRequest Schema
```python
@dataclass
class ReviewRequest:
    request_id: str  # UUID
    component: str
    action: str
    context: Dict[str, Any]
    created_at: str
    status: str  # "pending", "approved", "denied"
```

### 4. TrustReviewRequiredError
- New exception for "review" decisions
- Includes: request_id, component, action, target, summary, context
- Gateways raise this instead of TrustDeniedError on "review"

---

## Gateway Behavior Changes

### Before:
- "review" → Raise TrustDeniedError (hard halt)

### After:
- "review" → Enqueue request, raise TrustReviewRequiredError (with request_id)
- Replay: If `request_id` provided and approved with matching context → bypass review

### Flow:
```
1. Gateway called
2. Check for approved request_id (replay)
   - If approved + context matches → proceed
   - If approved + context mismatch → deny
3. Normal gate check
   - "deny" → TrustDeniedError
   - "review" → Enqueue, TrustReviewRequiredError
   - "allow" → proceed
```

---

## Context Matching (Prevents Token Reuse)

**Problem:** Approve request A, reuse token for action B

**Solution:**
- Approval includes context hash (SHA256 of sorted context JSON)
- Replay verifies context matches approved context
- Mismatch → denial

**Example:**
```python
# Approve for example.com
approval_store.approve("req-123", context={"target": "example.com"})

# Replay with same context → succeeds
reader.fetch("https://example.com", request_id="req-123")

# Replay with different context → fails
reader.fetch("https://malicious.com", request_id="req-123")
# Raises: APPROVAL_NOT_FOUND_OR_CONTEXT_MISMATCH
```

---

## Files Modified

1. `project_guardian/review_queue.py` - New module
2. `project_guardian/approval_store.py` - New module
3. `project_guardian/external.py` - Review queue integration
4. `project_guardian/file_writer.py` - Review queue integration
5. `project_guardian/subprocess_runner.py` - Review queue integration
6. `tests/test_review_queue.py` - New test file
7. `tests/test_invariants.py` - Review workflow tests
8. `CHANGELOG.md` - Updated
9. `REPORTS/AGENT_REPORT.md` - Complete report
10. `CONTROL.md` - Set to NONE

---

## Demo Workflow

```python
from project_guardian.external import WebReader, TrustReviewRequiredError
from project_guardian.memory import MemoryCore
from project_guardian.trust import TrustMatrix
from project_guardian.review_queue import ReviewQueue
from project_guardian.approval_store import ApprovalStore

memory = MemoryCore()
trust = TrustMatrix(memory)
queue = ReviewQueue()
store = ApprovalStore()

reader = WebReader(memory, trust_matrix=trust, review_queue=queue, approval_store=store)

# Step 1: Review request created
try:
    reader.fetch("https://example.com")
except TrustReviewRequiredError as e:
    request_id = e.request_id
    print(f"Review required: {request_id}")
    # request_id = "abc-123-def-456"

# Step 2: Human approves
original_context = {"target": "example.com", "method": "GET", "caller": "test"}
store.approve(request_id, context=original_context, approver="human", notes="Approved for testing")

# Step 3: Replay with approved request_id
result = reader.fetch("https://example.com", request_id=request_id)
# Succeeds - bypasses review
```

---

## Acceptance Criteria Met

- ✅ Review decision enqueues request and raises TrustReviewRequiredError
- ✅ Approval allows replay with matching context
- ✅ Approval denies modified context (context mismatch)
- ✅ Tests cover complete workflow
- ✅ acceptance.ps1 passes
- ✅ CONTROL.md set to NONE

---

## Policy Decision

**Current:** Human-only approvals (strict, safest)

**Future:** Hybrid (auto-approve low-risk categories, human for high-risk)

**Implementation:** Start with human-only, gradually move categories to auto-approve as trust builds.

---

**TASK-0012 complete! "Review" decisions now enable forward motion instead of hard halting.** ✅
