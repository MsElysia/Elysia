# TrustMatrix Module Specification

## Overview

TrustMatrix is the core trust management and gating system for Project Guardian. It evaluates component trust levels against action requirements and returns structured decisions (allow/deny/review).

## Decision Semantics

### TrustDecision Structure

```python
@dataclass
class TrustDecision:
    allowed: bool          # Whether action is allowed (see invariant below)
    decision: str          # "allow" | "deny" | "review"
    reason_code: str       # Machine-readable reason code
    message: str           # Human-readable message
    risk_score: float      # Risk score [0.0, 1.0], optional
```

### Decision Invariant

**Critical invariant:** The `allowed` field must match decision semantics:

- `decision == "allow"` => `allowed == True`
- `decision in {"deny", "review"}` => `allowed == False`

**Rationale:**
- "allow" means action can proceed immediately
- "deny" means action is blocked
- "review" means action is **NOT allowed** until human approval (gateways enqueue and raise `TrustReviewRequiredError`)

**Important:** Callers should check `decision`, not `allowed`, for clarity. The `allowed` field exists for backward compatibility but `decision` is the source of truth.

### Decision Flow

1. **allow**: Trust level >= (required + margin). Action proceeds immediately.
2. **review**: Trust level in [required, required + margin). Action blocked, enqueued for human approval.
3. **deny**: Trust level < required. Action blocked permanently.

Where `margin = 0.1` (hardcoded in `validate_trust_for_action`).

## Action Naming Policy

### Action Constants (Required for New Code)

All new code **MUST** use action constants from `trust.py`:

```python
NETWORK_ACCESS = "network_access"
FILE_WRITE = "file_write"
SUBPROCESS_EXECUTION = "subprocess_execution"
GOVERNANCE_MUTATION = "governance_mutation"
```

### Legacy Actions (Deprecated)

Legacy action strings are supported for backward compatibility but should be migrated:

- `"mutation"` → use `GOVERNANCE_MUTATION`
- `"data_access"` → (no constant yet, but should be added)
- `"system_change"` → use `SUBPROCESS_EXECUTION`
- `"file_operation"` → use `FILE_WRITE`

### Adding New Actions

1. Define constant in `trust.py`: `NEW_ACTION = "new_action"`
2. Add to `trust_requirements` dict in `validate_trust_for_action()`
3. Update `LEGACY_ACTIONS` if providing backward compatibility
4. Update gateways to use the constant
5. Add tests in `test_trust_smoke.py`

## Trust Thresholds

Default trust requirements (defined in `validate_trust_for_action`):

- `NETWORK_ACCESS`: 0.7
- `FILE_WRITE`: 0.5
- `SUBPROCESS_EXECUTION`: 0.9
- `GOVERNANCE_MUTATION`: 0.9
- Legacy `"mutation"`: 0.8
- Legacy `"data_access"`: 0.6
- Default (unknown actions): 0.5

## Review Queue Integration

**Important:** TrustMatrix does **NOT** directly enqueue review requests.

- TrustMatrix returns `TrustDecision(decision="review", ...)`
- **Gateways** (WebReader, FileWriter, SubprocessRunner) check the decision
- If `decision == "review"`, gateways call `review_queue.enqueue()` and raise `TrustReviewRequiredError`
- TrustMatrix is policy-only; gateways handle workflow

## Context Redaction

TrustMatrix redacts sensitive fields from context before logging to memory:

**Redacted fields:**
- `sensitive`, `content`, `body`
- `token`, `key`, `secret`, `password`
- `api_key`, `auth_token`

**Safe fields (logged):**
- `target`, `method`, `caller_identity`, `task_id`
- Other non-sensitive metadata

**Gap:** Redaction is keyword-based (checks if field name contains sensitive keywords). This may miss edge cases. For production, consider explicit allowlist of safe fields.

## Default Behavior

- Unknown components start with trust level 0.5 (default)
- Unknown actions use default threshold 0.5 and trigger warning
- Trust decay rate: 0.01 per `decay_all()` call
- Trust range: [0.0, 1.0] (clamped)

## Memory Integration

TrustMatrix logs all decisions to `MemoryCore` with:
- Category: `"trust"` or `"governance"` (for warnings)
- Priority: 0.5-0.9 (based on decision severity)
- Context: Redacted (no sensitive fields)

## Extracted Modules

TrustMatrix optionally integrates with:
- `TrustConsultationSystem` (if available in `extracted_modules/`)
- `AdversarialAISelfImprovement` (if available in `extracted_modules/`)

These are optional and do not affect core gating behavior.
