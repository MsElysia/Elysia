# MutationEngine Specification

## Overview

MutationEngine is the **only** allowed surface for code mutations in Project Guardian. It enforces governance gating, review queue integration, and approval replay for all code changes, especially protected governance files.

**Task-Driven Execution:** MutationEngine can be invoked via `APPLY_MUTATION` task type, which loads mutation payloads from `MUTATIONS/` directory. This provides a controlled, deterministic way to execute mutations through the task system.

**Preflight Guarantee:** When invoked via `APPLY_MUTATION`, Core performs a preflight check that validates all paths and checks TrustMatrix **before any writes occur**. This ensures no partial mutation applies - either all files in the batch are allowed, or none are written. The preflight uses the same context format (sorted touched_paths, override_flag, caller, task_id) for TrustMatrix decisions and ApprovalStore replay matching.

## Design Principles

1. **Single point of control**: All code mutations go through MutationEngine
2. **Governance protection**: Protected paths require explicit override + TrustMatrix approval
3. **TrustMatrix gating**: Every governance mutation requires trust validation
4. **Review queue integration**: "review" decisions enqueue requests
5. **Approval replay**: Approved request_ids bypass review with context matching
6. **Structured outcomes**: Explicit exceptions + MutationResult (no string parsing)

## Protected Paths

### Protected Files

- `CONTROL.md`
- `SPEC.md`
- `CHANGELOG.md`
- `project_guardian/core.py`
- `project_guardian/trust.py`
- `project_guardian/mutation.py`
- `project_guardian/safety.py`
- `project_guardian/consensus.py`

### Protected Directories

- `TASKS/`
- `REPORTS/`
- `scripts/`
- `tests/`

**Policy:** Any file in protected paths requires `allow_governance_mutation=True` + TrustMatrix approval.

## Decision Semantics

### Deny Path

- Protected path without override → `MutationDeniedError` (reason: `PROTECTED_PATH_WITHOUT_OVERRIDE`)
- TrustMatrix decision = deny → `MutationDeniedError` (reason: `decision.reason_code`)
- Approval not found or context mismatch → `MutationDeniedError` (reason: `APPROVAL_NOT_FOUND_OR_CONTEXT_MISMATCH`)

### Review Path

- TrustMatrix decision = review → enqueue request, raise `MutationReviewRequiredError` (with `request_id`)
- If no ReviewQueue available → treat as deny

### Allow Path

- Non-protected path → proceed directly
- Protected path with override + TrustMatrix approval → proceed
- Approved request_id with matching context → bypass review, proceed

### Success Path

- Mutation applied → return `MutationResult(ok=True, changed_files=[...], backup_paths=[...], summary=...)`

### Failure Path

- Unexpected error during apply → raise `MutationApplyError` (with error details)

## Exception Types

### MutationDeniedError

Raised when mutation is denied (protected path without override, trust denied, approval not found/context mismatch).

**Attributes:**
- `filename`: Target file
- `reason`: Machine-readable reason code
- `context`: Additional context dict

### MutationReviewRequiredError

Raised when mutation requires review before proceeding.

**Attributes:**
- `request_id`: Review request ID (for approval)
- `filename`: Target file
- `summary`: Human-readable summary
- `context`: Additional context dict

### MutationApplyError

Raised when mutation application fails unexpectedly (IO errors, etc.).

**Attributes:**
- `filename`: Target file
- `error`: Error message
- `context`: Additional context dict

## MutationResult

Structured result from successful mutation application.

**Attributes:**
- `ok`: bool (always True for successful mutations)
- `changed_files`: List[str] (paths of modified files)
- `backup_paths`: List[str] (paths of backup files created)
- `summary`: str (human-readable summary)

## Context Stored in Review Requests

For governance mutations, context includes:
- `component`: "MutationEngine"
- `action`: `GOVERNANCE_MUTATION` constant
- `touched_paths`: List[str] (sorted for deterministic hashing)
- `override_flag`: True
- `caller_identity`: Caller identifier
- `task_id`: Task identifier

**Important:** `touched_paths` must be sorted for deterministic hashing in ApprovalStore.

## Replay Matching

Approval replay requires:
1. `request_id` provided in `apply()` call
2. `approval_store.is_approved(request_id, context=gate_context)` returns True
3. Context must match exactly (hash comparison)

**Context mismatch scenarios:**
- Different file path → no match
- Different caller → no match
- Different task_id → no match

## Integration Points

### With TrustMatrix

- All governance mutations call `TrustMatrix.validate_trust_for_action()` with `GOVERNANCE_MUTATION` constant
- Gateways pass rich context (touched_paths, caller, task_id)
- Gateways handle `TrustDecision` objects (check `decision` field, not `allowed`)

### With ReviewQueue

- Gateways call `review_queue.enqueue()` when `decision == "review"`
- Gateways pass component, action constant, and context
- Gateways raise `MutationReviewRequiredError` with request_id

### With ApprovalStore

- Gateways call `approval_store.is_approved(request_id, context=gate_context)` for replay
- Context must match exactly (hash comparison)
- Gateways bypass trust gate if approved with matching context

## What MutationEngine Must Never Do

### Forbidden Patterns

1. **Direct network calls**: MutationEngine must NOT perform direct network calls (e.g., OpenAI API). If GPT review is needed, it must route through WebReader gateway.
2. **Bypass gateways**: All external actions must go through gateways (WebReader, FileWriter, SubprocessRunner).
3. **String-return outcomes**: Do NOT return plain strings for success/denial/failure. Use exceptions + MutationResult.

### Deprecated Methods

- `review_with_gpt()`: **DISABLED** - Always returns "reject". Bypasses governance. If GPT review is needed, route through WebReader gateway.
- `approve_last()`: **LEGACY** - Mutations are now approved via ReviewQueue/ApprovalStore.

## Error Handling

All mutations raise explicit exceptions:
- `MutationDeniedError`: Mutation denied (with reason_code)
- `MutationReviewRequiredError`: Mutation requires review (with request_id)
- `MutationApplyError`: Unexpected failure (with error details)

**No silent failures**: All denials are explicit exceptions.

## Backup Strategy

- Backups created in `guardian_backups/` directory
- Backup filename format: `{original_path}.bak.{timestamp}`
- Backup created before mutation applied
- Backup paths returned in `MutationResult.backup_paths`

## Performance Characteristics

- **Path check**: O(n) where n = number of protected paths (small, constant)
- **Trust gate**: O(1) (trust lookup + decision)
- **Review enqueue**: O(1) append (fast)
- **Approval check**: O(1) hash lookup (fast)
- **File write**: O(1) write (fast)

## Path Safety Rules

**Path Validation (TASK-0042):**
- **Absolute paths rejected**: All absolute paths are blocked (raises `MutationDeniedError` with `PATH_TRAVERSAL_BLOCKED`)
- **Traversal blocked**: Paths containing `..` are rejected (raises `MutationDeniedError` with `PATH_TRAVERSAL_BLOCKED`)
- **Repo root enforcement**: All paths must resolve within the repository root directory
  - Repo root is determined from `MutationEngine.__init__()` (defaults to `Path(__file__).resolve().parent.parent`)
  - Can be overridden via `repo_root` parameter for testing
  - Resolved path must be relative to repo root (checked via `Path.relative_to()`)
- **Directory writes blocked**: Writing directly to a directory (path that exists and is a directory) is rejected (raises `MutationDeniedError` with `PATH_IS_DIRECTORY`)
- **Symlink protection**: Paths that escape via symlinks are blocked by resolve() + relative_to() check
- **Validation order**: Path safety validation occurs **before** governance/protection checks (defense-in-depth)
- **Preflight guarantee**: When invoked via `APPLY_MUTATION`, Core's preflight validates all paths **before any writes occur**, ensuring no partial mutation applies

**Path Normalization:**
- All paths are normalized to relative paths from repo root
- Normalized paths are used in context for TrustMatrix and ApprovalStore
- This ensures consistent hashing and replay matching

## Security Constraints

- **No arbitrary mutations**: All mutations gated through TrustMatrix
- **Protected path enforcement**: Protected paths cannot be mutated without override + approval
- **Path traversal prevention**: Absolute paths, traversal (`..`), and paths outside repo root are blocked
- **Context safety**: Only safe, non-sensitive data stored in context (normalized relative paths)
- **Replay protection**: Context matching prevents approval token reuse
- **Preflight no-write guarantee**: Invalid paths cause denial before any writes/backups occur
