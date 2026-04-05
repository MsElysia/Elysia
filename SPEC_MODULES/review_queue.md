# ReviewQueue Module Specification

## Overview

ReviewQueue is a file-backed, append-only JSONL queue for storing review requests from TrustMatrix "review" decisions. It provides durability across restarts and supports status updates via append-only semantics.

## Design Principles

1. **Append-only**: Never modify existing lines in JSONL file
2. **Latest-state semantics**: `get_request()` returns the latest occurrence (last line with matching request_id)
3. **Corruption tolerance**: Invalid JSON lines are skipped, not fatal
4. **Restart-safe**: Re-instantiation preserves all state

## Data Structure

### ReviewRequest Schema

```python
@dataclass
class ReviewRequest:
    request_id: str        # UUID string
    component: str         # Component name (e.g., "WebReader")
    action: str           # Action type (e.g., NETWORK_ACCESS constant)
    context: Dict[str, Any]  # Context dict (target, method, caller, task_id, etc.)
    created_at: str        # ISO timestamp
    status: str           # "pending" | "approved" | "denied"
```

## File Format

**JSONL (JSON Lines)**: One JSON object per line, newline-delimited.

Example:
```jsonl
{"request_id": "abc-123", "component": "WebReader", "action": "network_access", "context": {"target": "example.com"}, "created_at": "2024-01-01T00:00:00", "status": "pending"}
{"request_id": "abc-123", "component": "WebReader", "action": "network_access", "context": {"target": "example.com"}, "created_at": "2024-01-01T00:00:00", "status": "approved", "approver": "human", "notes": "Approved", "updated_at": "2024-01-01T00:01:00"}
```

## Status Transition Policy

**Current Implementation:** Allows status reversals (approved → denied, denied → approved). Last update wins.

**Recommended Policy:** Monotonic transitions (pending → approved/denied only, no reversals).

**Enforcement:** Currently not enforced. To enforce monotonic transitions, add check in `update_status()`:
```python
if request.status in ["approved", "denied"]:
    return False  # Already finalized
```

## Methods

### `enqueue(component, action, context) -> request_id`

Appends a new review request to JSONL file.

- **Atomicity**: Single `f.write()` call is atomic at OS level
- **Returns**: UUID string (request_id)
- **Side effect**: Creates file if it doesn't exist

### `list_pending() -> List[ReviewRequest]`

Returns all requests with `status="pending"`.

- **Behavior**: Reads entire file, filters by status
- **Corruption handling**: Skips invalid JSON lines (logs warning, continues)
- **Performance**: O(n) where n = number of lines (acceptable for small queues)

### `get_request(request_id) -> Optional[ReviewRequest]`

Returns the **latest** matching request (last occurrence in JSONL).

- **Semantics**: Last line with matching request_id wins (handles status updates)
- **Corruption handling**: Skips invalid JSON lines
- **Performance**: O(n) scan (acceptable for small queues)

### `update_status(request_id, status, approver, notes) -> bool`

Appends a new line with updated status (append-only design).

- **Atomicity**: Single `f.write()` call is atomic at OS level
- **Status transitions**: Currently allows reversals (see policy above)
- **Returns**: True if updated, False if request not found

## Corruption Handling

**Policy:** Skip invalid lines, don't crash.

- Invalid JSON: Skipped silently (logged to stderr if logging enabled)
- Empty lines: Skipped
- Missing fields: Raises `ValueError` (caught by caller)

**Gap:** No explicit warning/logging for corruption. Consider adding logging in production.

## Restart Tolerance

**Guarantee:** Re-instantiation preserves all state.

- File is append-only, so all history is preserved
- `get_request()` reads entire file, so latest state is always correct
- `list_pending()` filters by status, so pending set is correct

**Test:** Instantiate → enqueue → re-instantiate → verify state preserved.

## Integration with Gateways

**Who enqueues:** Gateways (WebReader, FileWriter, SubprocessRunner), not TrustMatrix.

**Flow:**
1. Gateway calls `TrustMatrix.validate_trust_for_action()`
2. If `decision == "review"`, gateway calls `review_queue.enqueue()`
3. Gateway raises `TrustReviewRequiredError` with request_id
4. Human approves/denies via UI → `update_status()` called
5. Gateway replays with `request_id` → checks `approval_store.is_approved()`

## Performance Characteristics

- **Enqueue**: O(1) append (fast)
- **list_pending**: O(n) scan (acceptable for < 1000 requests)
- **get_request**: O(n) scan (acceptable for < 1000 requests)
- **update_status**: O(1) append + O(n) get_request (acceptable for small queues)

**Scaling:** For > 1000 requests, consider:
- Index file (request_id → line number)
- Database backend
- Periodic compaction (remove old finalized requests)

## File Location

**Default:** `REPORTS/review_queue.jsonl`

**Custom:** Pass `queue_file` parameter to `ReviewQueue()` constructor.

## Thread Safety

**Current:** Not thread-safe (single-writer assumption).

**For multi-writer:** Add file locking (fcntl on Unix, msvcrt on Windows) or use database.
