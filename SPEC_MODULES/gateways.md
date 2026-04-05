# External Action Gateways Specification

## Overview

Gateways are the **only** allowed surfaces for external actions (network, filesystem writes, subprocess execution). All external actions must go through these gateways, which enforce TrustMatrix gating, review queue integration, and approval replay.

## Design Principles

1. **Single point of control**: All external actions go through gateways
2. **TrustMatrix gating**: Every action requires trust validation
3. **Review queue integration**: "review" decisions enqueue requests
4. **Approval replay**: Approved request_ids bypass review with context matching
5. **Context safety**: Only safe, non-sensitive data stored in context

## Gateway Contracts

### WebReader (Network Access)

**Location:** `project_guardian/external.py`

**Action Constant:** `NETWORK_ACCESS`

**Methods:**
- `fetch(url, max_length, caller_identity, task_id, request_id, allow_internal) -> Optional[str]` - GET requests returning text
- `request_json(method, url, json_body, headers, timeout_s, caller_identity, task_id, request_id, allow_internal) -> Dict[str, Any]` - POST/PUT/PATCH/DELETE with JSON support

**SSRF Safety Floor:**

WebReader enforces a minimum SSRF safety floor before TrustMatrix gating:

1. **Scheme Validation**: Only `http://` and `https://` schemes allowed. Other schemes (e.g., `file://`, `ftp://`) raise `TrustDeniedError` with reason_code `UNSUPPORTED_URL_SCHEME`.

2. **Internal Target Blocking**: By default, blocks access to:
   - Loopback IPs: `127.0.0.0/8`, `::1`
   - Link-local IPs: `169.254.0.0/16` (includes cloud metadata IP `169.254.169.254`)
   - Private RFC1918 IPs: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
   - IPv6 ULA: `fc00::/7`
   - IPv6 link-local: `fe80::/10`
   - Hostnames: `localhost`, any hostname ending with `.local`, empty host

   Blocked targets raise `TrustDeniedError` with reason_code `TARGET_BLOCKED_INTERNAL`.

3. **Override Path (`allow_internal=True`)**: 
   - If `allow_internal=True` is set, internal targets are not immediately blocked
   - However, they still require TrustMatrix review/approval (cannot auto-allow)
   - Even with `allow_internal=True`, scheme validation still applies (http/https only)
   - Context includes `allow_internal=True` and `blocked_reason="TARGET_BLOCKED_INTERNAL"` for audit

**Method: `fetch()` (GET requests)**

**Parameters:**
- `url`: URL to fetch
- `max_length`: Maximum content length to return
- `caller_identity`: Identity of the caller (for audit)
- `task_id`: Task ID if available (for audit)
- `request_id`: Optional request ID for replay approval
- `allow_internal`: If True, allow internal targets (requires TrustMatrix review/approval)

**Context Stored:**
- `component`: "WebReader"
- `action`: `NETWORK_ACCESS`
- `target`: host only (e.g., "example.com") - **NOT full URL, NOT query string**
- `scheme`: URL scheme ("http" or "https")
- `method`: "GET"
- `allow_internal`: boolean
- `blocked_reason`: reason code if target is internal (e.g., "TARGET_BLOCKED_INTERNAL")
- `caller_identity`: caller identifier
- `task_id`: task identifier

**Method: `request_json()` (POST/PUT/PATCH/DELETE with JSON)**

**Parameters:**
- `method`: HTTP method (GET, POST, PUT, PATCH, DELETE)
- `url`: URL to request
- `json_body`: Optional JSON body (dict or list)
- `headers`: Optional custom headers (will be redacted in logs)
- `timeout_s`: Request timeout in seconds
- `caller_identity`: Identity of the caller (for audit)
- `task_id`: Task ID if available (for audit)
- `request_id`: Optional request ID for replay approval
- `allow_internal`: If True, allow internal targets (requires TrustMatrix review/approval)

**Context Stored:**
- `component`: "WebReader"
- `action`: `NETWORK_ACCESS`
- `target`: host only (e.g., "example.com") - **NOT full URL, NOT query string**
- `scheme`: URL scheme ("http" or "https")
- `method`: HTTP method ("GET", "POST", "PUT", "PATCH", "DELETE")
- `has_body`: boolean (True if json_body is not None)
- `content_type`: "json" if json_body is not None, else None
- `allow_internal`: boolean
- `blocked_reason`: reason code if target is internal (e.g., "TARGET_BLOCKED_INTERNAL")
- `caller_identity`: caller identifier
- `task_id`: task identifier

**Parameters:**
- `method`: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
- `url`: Full URL (domain extracted for context)
- `json_body`: Optional dict or list (JSON payload)
- `headers`: Optional dict (sensitive headers redacted in logs)
- `timeout_s`: Request timeout in seconds (default: 30)
- `caller_identity`: Identity of caller (for audit)
- `task_id`: Task ID if available (for audit)
- `request_id`: Optional request ID for approval replay

**Returns:**
- Dict with keys: `status_code`, `json` (parsed JSON if available), `text` (raw text if not JSON), `headers` (response headers)

**Header Redaction:**
- Sensitive headers (authorization, token, key, secret, api-key, x-api-key, cookie) are redacted in logs
- Headers are passed to the request but logged as "[REDACTED]"

**JSON Parsing:**
- Attempts to parse JSON if `Content-Type` indicates JSON or response body starts with `{`/`[`
- Falls back to text if JSON parsing fails

**Forbidden:**
- Full URLs in context (only domain)
- Query strings in context
- Request/response bodies in context
- Authentication tokens in context (redacted in logs)

**Replay Matching:**
- Context hash must match exactly (domain, method, has_body, content_type, caller, task_id)
- Different domain → no match
- Different method → no match
- Different has_body/content_type → no match

**Exceptions:**
- `TrustDeniedError`: On deny decision or approval not found/context mismatch
- `TrustReviewRequiredError`: On review decision (with request_id)

### FileWriter (Filesystem Writes)

**Location:** `project_guardian/file_writer.py`

**Path Safety Rules:**
- **Absolute paths rejected**: All absolute paths are blocked (raises `TrustDeniedError` with `PATH_TRAVERSAL_BLOCKED`)
- **Traversal blocked**: Paths containing `..` are rejected (raises `TrustDeniedError` with `PATH_TRAVERSAL_BLOCKED`)
- **Repo root enforcement**: All paths must resolve within the repository root directory
  - Repo root is determined from `FileWriter.__init__()` (defaults to `Path(__file__).resolve().parent.parent`)
  - Can be overridden via `repo_root` parameter for testing
  - Resolved path must be relative to repo root (checked via `Path.relative_to()`)
- **Directory writes blocked**: Writing directly to a directory (path that exists and is a directory) is rejected
- **Validation order**: Path safety validation occurs **before** TrustMatrix gating (defense-in-depth)
- **Symlink protection**: Paths that escape via symlinks are blocked by resolve() + relative_to() check

**Action Constant:** `FILE_WRITE`

**Method:** `write_file(file_path, content, mode, caller_identity, task_id, request_id) -> str`

**Context Stored:**
- `component`: "FileWriter"
- `action`: `FILE_WRITE`
- `target`: relative path from repo root (e.g., "REPORTS/test.txt") - **NOT absolute path**
- `mode`: write mode ("w", "a", "wb", "ab")
- `bytes`: length of content in bytes
- `allow_overwrite`: boolean (True if file exists)
- `caller_identity`: caller identifier
- `task_id`: task identifier

**Allowed Modes:**
- `"w"`: Text write (overwrite)
- `"a"`: Text append
- `"wb"`: Binary write (overwrite)
- `"ab"`: Binary append

**Forbidden:**
- Full paths in context (only filename)
- Other modes (e.g., "x", "r+", "w+")
- `shell=True` in subprocess calls (if any)
- Arbitrary file locations without governance approval

**Replay Matching:**
- Context hash must match exactly (filename, mode, caller, task_id)
- Different filename → no match
- Different mode → no match

**Exceptions:**
- `TrustDeniedError`: On deny decision or approval not found/context mismatch
- `TrustReviewRequiredError`: On review decision (with request_id)
- `ValueError`: On invalid mode

### SubprocessRunner (Subprocess Execution)

**Location:** `project_guardian/subprocess_runner.py`

**Action Constant:** `SUBPROCESS_EXECUTION`

**Method:** `run_command(command, caller_identity, task_id, request_id, timeout) -> Dict[str, Any]`

**Context Stored:**
- `component`: "SubprocessRunner"
- `action`: `SUBPROCESS_EXECUTION`
- `target`: command name only (e.g., "echo") - **NOT full command, NOT arguments**
- `args`: number of arguments (not the arguments themselves)
- `caller_identity`: caller identifier
- `task_id`: task identifier

**Forbidden:**
- `shell=True` in subprocess.run() (STRICTLY FORBIDDEN)
- Arbitrary command execution without approval
- Commands with sensitive arguments in context

**Replay Matching:**
- Context hash must match exactly (command name, args count, caller, task_id)
- Different command → no match
- Different argument count → no match

**Timeout Behavior:**
- Configurable timeout parameter (default: 30 seconds)
- Acceptance execution uses 300 seconds (5 minutes)
- `TimeoutExpired` → raises `TrustDeniedError` with `SUBPROCESS_EXECUTION` constant

**Exceptions:**
- `TrustDeniedError`: On deny decision, approval not found/context mismatch, or timeout
- `TrustReviewRequiredError`: On review decision (with request_id)

## Decision Flow

### Allow Path

1. Gateway checks for approved `request_id` (if provided)
2. If approved with matching context → proceed directly
3. If no `request_id` or not approved → call `TrustMatrix.validate_trust_for_action()`
4. If `decision == "allow"` → proceed with action
5. Action executed (network call, file write, subprocess)

### Deny Path

1. `TrustMatrix.validate_trust_for_action()` returns `decision == "deny"`
2. Gateway raises `TrustDeniedError` with reason_code
3. **No external action occurs**

### Review Path

1. `TrustMatrix.validate_trust_for_action()` returns `decision == "review"`
2. Gateway calls `review_queue.enqueue()` with context
3. Gateway raises `TrustReviewRequiredError` with request_id
4. **No external action occurs** (waits for human approval)

### Replay Path (After Approval)

1. Human approves review request via UI
2. Gateway called with `request_id` in context
3. Gateway checks `approval_store.is_approved(request_id, context=gate_context)`
4. If approved and context matches → proceed directly (bypass trust gate)
5. If not approved or context mismatch → raise `TrustDeniedError`

## Context Safety Rules

### What IS Stored in Context

- Component name
- Action constant
- Target (domain/filename/command name only)
- Method (for network: GET, POST, PUT, etc.)
- Has body (for network: boolean indicating if request has body)
- Content type (for network: "json" if JSON body)
- Mode (for file writes)
- Argument count (for subprocess, not the arguments)
- Background flag (for subprocess: True if background execution)
- Caller identity
- Task ID

### What is NOT Stored in Context

- Full URLs (only domain)
- Query strings
- Request/response bodies
- File paths (only filename)
- Command arguments (only count)
- Authentication tokens
- API keys
- Passwords
- Any sensitive data

## Integration Points

### With TrustMatrix

- All gateways call `TrustMatrix.validate_trust_for_action()` with action constants
- Gateways pass rich context (target, method, caller, task_id)
- Gateways handle `TrustDecision` objects (check `decision` field, not `allowed`)

### With ReviewQueue

- Gateways call `review_queue.enqueue()` when `decision == "review"`
- Gateways pass component, action constant, and context
- Gateways raise `TrustReviewRequiredError` with request_id

### With ApprovalStore

- Gateways call `approval_store.is_approved(request_id, context=gate_context)` for replay
- Context must match exactly (hash comparison)
- Gateways bypass trust gate if approved with matching context

## Security Constraints

### WebReader

- **No shell injection**: URL is validated, not executed
- **No credential leakage**: Only domain stored in context
- **Timeout enforced**: 10-second timeout on network calls

### FileWriter

- **Mode restrictions**: Only "w/a/wb/ab" allowed
- **Path sanitization**: Only filename in context (not full path)
- **No arbitrary writes**: All writes gated through TrustMatrix

### SubprocessRunner

- **No shell=True**: STRICTLY FORBIDDEN (prevents shell injection)
- **Timeout enforced**: Configurable timeout (default: 30 seconds, acceptance: 300 seconds)
- **Command restrictions**: Only command name in context (not arguments)
- **No arbitrary execution**: All commands gated through TrustMatrix
- **Single subprocess surface**: All subprocess execution (including acceptance) goes through SubprocessRunner

## Performance Characteristics

- **Gate check**: O(1) (trust lookup + decision)
- **Review enqueue**: O(1) append (fast)
- **Approval check**: O(1) hash lookup (fast)
- **Network call**: Depends on network (external)
- **File write**: O(1) write (fast)
- **Subprocess**: Depends on command (external, but timeout-limited)

## Error Handling

All gateways raise explicit exceptions:
- `TrustDeniedError`: Action denied (with reason_code)
- `TrustReviewRequiredError`: Action requires review (with request_id)
- `ValueError`: Invalid parameters (e.g., invalid file mode)

**No silent failures**: All denials are explicit exceptions.
