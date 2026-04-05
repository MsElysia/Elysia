# ApprovalStore Module Specification

## Overview

ApprovalStore is a file-backed JSON map that stores approval records for review requests. It uses context hashing to prevent replay attacks (token reuse).

## Design Principles

1. **Atomic writes**: tmp + os.replace() pattern (crash-safe)
2. **Context matching**: Exact context match required (prevents token reuse)
3. **Deterministic hashing**: Hash independent of dict key order
4. **Single-writer assumption**: No file locking (acceptable for current scope)

## Data Structure

### ApprovalRecord Schema

```python
@dataclass
class ApprovalRecord:
    request_id: str      # UUID string (matches ReviewRequest.request_id)
    approved: bool       # True if approved, False if denied
    timestamp: str       # ISO timestamp
    approver: str        # Who approved/denied (e.g., "human")
    notes: str          # Optional notes
    context_hash: str    # SHA256 hash of context (first 16 chars) - prevents reuse
```

## File Format

**JSON map**: `{request_id: ApprovalRecord_dict, ...}`

Example:
```json
{
  "abc-123": {
    "request_id": "abc-123",
    "approved": true,
    "timestamp": "2024-01-01T00:00:00",
    "approver": "human",
    "notes": "Approved for testing",
    "context_hash": "a1b2c3d4e5f6g7h8"
  }
}
```

## Context Hashing

**Purpose:** Prevent approval token reuse (replay attacks).

**Algorithm:**
1. Sort context dict keys (ensures deterministic hash)
2. JSON serialize sorted dict
3. SHA256 hash
4. Take first 16 hex characters

**Properties:**
- Deterministic: Same context → same hash (regardless of key order)
- Collision-resistant: Different contexts → different hashes (with high probability)
- Short: 16 chars sufficient for current scale

## Methods

### `approve(request_id, approver, notes, context) -> bool`

Approve a review request with context.

- **Atomic write**: Uses tmp + os.replace() pattern
- **Context hash**: Computed and stored for matching
- **Returns**: True if approved, False if already exists
- **Side effect**: Creates file if it doesn't exist

### `deny(request_id, approver, notes) -> bool`

Deny a review request.

- **Atomic write**: Uses tmp + os.replace() pattern
- **Context hash**: Empty string (denials don't need context matching)
- **Returns**: True if denied, False if already exists

### `is_approved(request_id, context) -> bool`

Check if request is approved and context matches.

- **Exact match required**: Context hash must match exactly
- **Returns**: True only if approved AND context matches, False otherwise
- **Denials**: Always returns False (even if context matches)

### `get_approval(request_id) -> Optional[ApprovalRecord]`

Get approval record for a request.

- **Returns**: ApprovalRecord or None if not found
- **Use case**: UI display, audit logs

## Context Matching Rules

**Strict matching:** Exact context hash match required.

- Same keys, same values → match
- Different key order → match (hash is deterministic)
- Missing key → no match
- Extra key → no match
- Different value → no match

**Examples:**
```python
# Approve with context A
context_a = {"target": "example.com", "method": "GET"}
store.approve("req-123", context=context_a)

# Match: exact same context
assert store.is_approved("req-123", context={"target": "example.com", "method": "GET"}) == True

# Match: same context, different key order
assert store.is_approved("req-123", context={"method": "GET", "target": "example.com"}) == True

# No match: missing key
assert store.is_approved("req-123", context={"target": "example.com"}) == False

# No match: extra key
assert store.is_approved("req-123", context={"target": "example.com", "method": "GET", "extra": "field"}) == False

# No match: different value
assert store.is_approved("req-123", context={"target": "malicious.com", "method": "GET"}) == False
```

## Replay Attack Prevention

**Threat:** Approve request A, reuse approval token for request B.

**Defense:** Context hash matching.

**Example:**
1. Approve `request_id="abc-123"` with `context={"target": "example.com", "action": NETWORK_ACCESS}`
2. Attempt replay: `is_approved("abc-123", context={"target": "malicious.com", "action": NETWORK_ACCESS})`
3. Result: False (context hash mismatch)

**Gap:** If context is None during approval, context_hash is empty string. Replay with any context will fail (safe, but may be too strict).

## Atomic Write Pattern

**Implementation:**
```python
tmp_file = store_file.with_suffix('.tmp')
with open(tmp_file, 'w') as f:
    json.dump(store, f)
os.replace(tmp_file, store_file)  # Atomic on POSIX and Windows
```

**Guarantee:** No partial files on crash.

**Limitation:** Single-writer assumption (no file locking).

## Duplicate Prevention

**Policy:** Once approved/denied, cannot be changed.

- `approve()` returns False if request_id already exists
- `deny()` returns False if request_id already exists
- **Gap:** No explicit check for approve-after-deny or deny-after-approve (handled by duplicate check)

## File Location

**Default:** `REPORTS/approval_store.json`

**Custom:** Pass `store_file` parameter to `ApprovalStore()` constructor.

## Integration with Gateways

**Who checks approvals:** Gateways (WebReader, FileWriter, SubprocessRunner).

**Flow:**
1. Gateway receives `request_id` in context (from approved review)
2. Gateway calls `approval_store.is_approved(request_id, context=gate_context)`
3. If True → proceed with action (bypass trust gate)
4. If False → raise `TrustDeniedError` (context mismatch or not approved)

## Performance Characteristics

- **approve/deny**: O(1) dict update + O(1) atomic write (fast)
- **is_approved**: O(1) dict lookup + O(1) hash computation (fast)
- **get_approval**: O(1) dict lookup (fast)

**Scaling:** Excellent (O(1) operations). File size grows linearly with approvals, but JSON parsing is fast for < 10k records.

## Thread Safety

**Current:** Not thread-safe (single-writer assumption).

**For multi-writer:** Add file locking (fcntl on Unix, msvcrt on Windows) or use database.
