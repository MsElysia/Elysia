# Operator confirmation context plan

**Status:** Planning + **data-only confirmation store** — **do not enable live execution from this document.**  
**Date:** 2026-05-18 (updated)  
**Related:** [`LIVE_EXECUTION_GOVERNANCE_PLAN.md`](LIVE_EXECUTION_GOVERNANCE_PLAN.md), `project_guardian/governance/live_execution_guard.py`, `project_guardian/governance/operator_confirmation_store.py`, `project_guardian/brain/live_execution_runtime.py`

This document defines how a future operator-approved live execution request would supply enough context for the fail-closed live-execution guard to make a decision. A **JSONL confirmation store** exists for persistence; **`live_execution_runtime.py` validates** confirmations when `operator_confirmation_id` is present (validation-only — confirmations are **not consumed** and live execution remains disabled by config). No confirmation UI/API yet.

---

## A. Purpose

Operator confirmation context exists so that **live execution is never implied** by chat text, config drift, or a prior dry-run alone. A human operator (or an explicit API client acting on their behalf) must:

1. Review a **dry-run Brain trace** that shows what would run.
2. Approve a **specific structured action** (capability, action type, risk, rollback plan).
3. Pass a **durable confirmation record** (ID + metadata) into the runtime request.

The guard uses this context to **fail closed**: missing, stale, mismatched, or reused confirmations deny live execution even if `operator_chat_live_execution` is later enabled in config.

---

## B. Current state

### What the guard receives today

`apply_live_execution_guard_to_context` in `project_guardian/brain/live_execution_runtime.py` builds a `LiveExecutionRequest` from the Brain **merge context** dict (and config). Fields already mapped when present in `merge`:

| Merge key (examples) | Guard field | Notes |
|----------------------|-------------|--------|
| `operator_confirmed`, `operator_confirmation` | `operator_confirmed` | Set from store when `operator_confirmation_id` validates |
| `operator_confirmation_id` | (validation metadata) | Loads JSONL record; sets `operator_confirmation_validation` |
| `operator_confirmation_store_path` | store override | Defaults to `data/runtime/operator_confirmations.jsonl` |
| `dry_run_trace_id`, `prior_dry_run_trace_id` | `dry_run_trace_id` | ID string only |
| `dry_run_trace_completed_at`, `now`, `dry_run_trace_ttl_seconds` | trace freshness | TTL default 900s in adapter |
| `live_execution_risk_level`, `risk_level` | `risk_level` | Defaults to `"blocked"` if missing |
| `live_execution_action_type`, `action_type` | `action_type` | |
| `live_execution_executor`, `executor_name` | `executor_name` | Must appear in allowlist |
| `executor_allowlist`, `live_execution_executor_allowlist` | `executor_allowlist` | Tuple of allowed names |
| `explicit_medium_risk_approval`, `medium_risk_approved` | `explicit_medium_risk_approval` | |
| `rollback_available`, `rollback_plan_id` | rollback gates | For file/code mutation flags |
| `is_self_modification`, `self_modification` | `is_self_modification` | |
| `is_autonomy_context`, `autonomy_context` | `is_autonomy_context` | Always denied for live |
| Observation text / `raw_command_present` | raw command detection | Shell-like text denied |

Guard output is attached as `merge["live_execution_guard"]` and surfaced in operator chat metadata as `brain_live_execution_guard_*` (Runtime API and control panel).

### What is missing

| Gap | Impact |
|-----|--------|
| **No confirmation UI/API** | Records must be created via library/tests; chat does not issue confirmations |
| **Confirmations not consumed** | Validation-only: `mark_operator_confirmation_used` is not called from runtime |
| **No operator UI/API payload** | Chat `POST` bodies do not include `live_execution_request` |
| **No `requested_action_summary`** | Operators cannot see a stable human-readable action line in guard/audit |
| **Prompt contract not wired into merge** | `prompt_contract_valid` not populated from validation results on chat path |
| **Risk not copied from dry-run trace** | `risk_level` must be passed manually in merge; not auto-filled from `brain_last_pipeline.json` |
| **Config still off** | Even a fully allowed guard decision forces `dry_run=True` unless `operator_chat_live_execution` and `dry_run` are both false |

### Current call path (unchanged behavior)

```text
POST /api/chat or control panel chat
  → run_operator_chat_turn (dry_run=True on helper)
  → brain_trace_callback → run_brain_pipeline_for_operator_event
  → apply_live_execution_guard_to_context(merge, …)
      → if operator_confirmation_id: load store, validate, merge guard fields, set operator_confirmation_validation
  → BrainPipeline.run (dry_run)
```

No live execution is enabled; denied live **attempts** may append to `data/runtime/live_execution_guard_audit.jsonl`.

---

## C. Proposed context schema

Canonical object: **`OperatorLiveExecutionContext`** (future; not implemented).

All string fields are bounded (≤240 chars unless noted). Timestamps are ISO-8601 UTC.

| Field | Type | Example | Required for live (future) |
|-------|------|---------|---------------------------|
| `operator_confirmation_id` | string (uuid) | `"conf_8f2a…"` | Yes |
| `operator_confirmed` | bool | `true` | Yes (must be true) |
| `dry_run_trace_id` | string | `"brain_pipeline_id from trace"` | Yes |
| `dry_run_trace_created_at` | string (ISO) | `"2026-05-18T12:00:00Z"` | Yes (or supply age) |
| `dry_run_trace_age_seconds` | number | `42.5` | Alternative to created_at |
| `confirmed_action_id` | string | `"act_9b1c…"` | Yes — binds confirmation to one action |
| `requested_action_summary` | string | `"Invoke capability brain:noop for operator chat"` | Yes (display + audit) |
| `requested_tool_name` | string | `"brain:noop"` | Yes — maps to `executor_name` |
| `requested_action_type` | string | `"capability_invoke"` | Yes |
| `executor_allowlisted` | bool | `true` | Derived: `executor_name ∈ allowlist` |
| `executor_allowlist` | string[] | `["brain:noop"]` | Yes — from config/registry |
| `risk_level` | enum | `"low"` \| `"medium"` \| `"high"` \| `"blocked"` | Yes — from dry-run trace |
| `medium_risk_approved` | bool | `false` | Required when `risk_level=medium` |
| `prompt_contract_valid` | bool | `true` | Per config mode |
| `prompt_contract_mode` | string | `"off"` \| `"warn"` \| `"strict"` | From brain config |
| `rollback_available` | bool | `true` | Required for file/code mutations |
| `rollback_plan_id` | string | `"rb_plan_…"` | Optional ID |
| `self_modification` | bool | `false` | If true → separate workflow only |
| `autonomy_context` | bool | `false` | Must be false for operator chat |
| `raw_command_present` | bool | `false` | Must be false unless allowlisted |
| `conversation_id` | string | `"control_panel"` | For audit correlation |
| `source_entrypoint` | string | `"operator_chat"` | |

**Mapping into today’s merge dict** (for incremental implementation):

```text
live_execution_request.*  →  merge["operator_confirmation_id"], merge["dry_run_trace_id"], …
requested_tool_name     →  merge["live_execution_executor"]
requested_action_type   →  merge["live_execution_action_type"]
requested_action_summary→  merge["live_execution_target"] or merge["requested_action_summary"]
```

---

## D. Source of each field

| Field | Primary source |
|-------|----------------|
| `dry_run_trace_id` | Dry-run trace — `brain_pipeline_id` / `data/runtime/brain_last_pipeline.json` |
| `dry_run_trace_created_at` | Dry-run trace `started_at` or persist timestamp |
| `dry_run_trace_age_seconds` | Computed: `now - dry_run_trace_created_at` |
| `requested_action_summary` | Dry-run trace (`tool_selected`, `plan_goal`, sanitized TDA summary) + operator UI |
| `requested_tool_name` | Dry-run trace `tool_selected` / structured command `capability_ref` |
| `requested_action_type` | TDA proposal / Brain structured command |
| `risk_level` | Dry-run trace `risk` / risk_checker output |
| `medium_risk_approved` | Operator UI / API — explicit second checkbox |
| `prompt_contract_valid` | Prompt-contract validation on dry-run path (`prompt_contract_validation` in trace) |
| `prompt_contract_mode` | Config `brain_pipeline.prompt_contract_validation.mode` |
| `executor_allowlist` | Config + executor registry (canonical capability refs) |
| `executor_allowlisted` | Guard/runtime derived: name ∈ allowlist |
| `rollback_available` | Rollback planner / implementer preview metadata |
| `rollback_plan_id` | Rollback planner |
| `operator_confirmation_id` | **Operator confirmation record** (new store) |
| `operator_confirmed` | Operator UI / API |
| `confirmed_action_id` | Confirmation record — hash of action fingerprint |
| `self_modification` | Proposal queue / action classifier |
| `autonomy_context` | Must be false; set by entrypoint, not operator chat |
| `raw_command_present` | Guard heuristic on message + explicit flag |
| `conversation_id` | ConversationStore / request body |
| `config` | `config/brain_pipeline.json` — gates live flag, TTL, prompt contracts |

---

## E. Flow (target)

```text
1. Operator sends chat message (normal path, dry_run=true)
      → BrainPipeline runs dry_run
      → Trace persisted (brain_last_pipeline.json + brain_pipeline_id)

2. UI/API shows Brain Trace + proposed action summary + risk label

3. Operator clicks "Review" / explicit confirm (future UI)
      → Server creates OperatorConfirmationRecord:
            confirmation_id, trace_id, action_fingerprint, expires_at, used=false

4. Operator submits live execution request (future API only)
      → Body includes live_execution_request { confirmation_id, … }
      → Chat/brain path merges context
      → apply_live_execution_guard_to_context
      → Guard: validates record, trace, action, risk, allowlist, rollback
      → Still dry_run=true while config off
      → Audit JSONL records confirmation_id (redacted)

5. Only after governance + config enable:
      → Same flow may set dry_run=false IF guard allows AND config allows
```

**Today:** steps 3–5 are **not** implemented; step 1–2 operate with guard wired fail-closed on any live intent.

---

## F. API shape proposal (not implemented)

### Create confirmation (future)

`POST /api/operator/live-execution/confirmations`

```json
{
  "conversation_id": "control_panel",
  "dry_run_trace_id": "bp-20260518-abc123",
  "confirmed_action_id": "act_fingerprint_sha256_short",
  "requested_action_summary": "Run capability brain:noop with planner goal 'answer operator'",
  "requested_tool_name": "brain:noop",
  "requested_action_type": "capability_invoke",
  "risk_level": "low",
  "medium_risk_approved": false,
  "acknowledged_rollback_plan_id": null
}
```

Response:

```json
{
  "operator_confirmation_id": "conf_uuid",
  "expires_at": "2026-05-18T13:00:00Z",
  "status": "pending"
}
```

### Execute with confirmation (future — still config-gated)

`POST /api/chat` or `POST /api/operator/chat` (existing routes)

```json
{
  "message": "Proceed with the reviewed action.",
  "conversation_id": "control_panel",
  "live_execution_request": {
    "operator_confirmation_id": "conf_uuid",
    "dry_run_trace_id": "bp-20260518-abc123",
    "confirmed_action_id": "act_fingerprint_sha256_short",
    "medium_risk_approved": false,
    "request_live_execution": true
  }
}
```

Runtime merges into Brain context:

```python
merge.update({
    "live_execution_requested": True,
    "operator_confirmed": True,
    "operator_confirmation_id": body["live_execution_request"]["operator_confirmation_id"],
    "dry_run_trace_id": body["live_execution_request"]["dry_run_trace_id"],
    # … remaining fields from confirmation record lookup + trace hydrate
})
```

**Important:** `request_live_execution: true` alone must **not** enable execution without a valid confirmation record and config flags.

---

## G. Safety rules

1. **Confirmation must match trace and action** — Record stores `dry_run_trace_id` + `confirmed_action_id` fingerprint; runtime rejects mismatch.
2. **Confirmation expires** — Default TTL e.g. 15–60 minutes; guard rejects stale trace and expired confirmation.
3. **Confirmation is single-use** — Mark `used_at` on first live attempt; reuse denies with `confirmation_already_used`.
4. **High/blocked risk cannot be confirmed** — UI must not issue confirmations; guard denies even with ID.
5. **Medium risk requires explicit approval** — `medium_risk_approved` / `explicit_medium_risk_approval` must be true.
6. **Self-modification requires separate workflow** — Not confirmable via operator chat; separate governance path only.
7. **Autonomy cannot be confirmed through operator chat** — `is_autonomy_context` must be false; autonomy entrypoint not eligible.
8. **Raw command text denied** unless separately allowlisted — No paste of shell/LLM output as executable command.
9. **Config off = dry_run forced** — Even allowed guard outcome keeps `dry_run=True` until explicit config enable (current runtime behavior).
10. **Audit records confirmation ID** — Redacted JSONL row includes `operator_confirmation_id`, `dry_run_trace_id`, `allowed`, `reasons` (no raw message).

---

## H. Tests to add before implementation

| Test module | Scenario |
|-------------|----------|
| `test_operator_confirmation_store.py` | Create/load confirmation; expiry; single-use |
| `test_operator_confirmation_trace_binding.py` | Mismatched `dry_run_trace_id` / `confirmed_action_id` denied |
| `test_live_execution_guard_confirmation.py` | Missing `operator_confirmation_id` denied |
| `test_live_execution_guard_confirmation.py` | Stale confirmation denied |
| `test_live_execution_guard_confirmation.py` | Reused confirmation denied |
| `test_live_execution_guard_confirmation.py` | High/blocked risk denied even with confirmation |
| `test_live_execution_guard_confirmation.py` | Medium risk requires `medium_risk_approved` |
| `test_live_execution_guard_runtime_integration.py` | Audit row contains confirmation ID (redacted) |
| `test_live_execution_guard_runtime_integration.py` | Config off → `dry_run` stays true after guard |
| `test_api_operator_chat_live_execution_request.py` | API ignores `live_execution_request` until feature flag (fail closed) |
| `test_control_panel_operator_chat_helper_integration.py` | Existing tests still pass; no live button |

---

## I. Non-goals

- No **Enable live execution** button or toggle in control panel (safe-stack panels stay read-only).
- No **live execution** in production (`operator_chat_live_execution` remains false).
- No **autonomy** wiring or confirm-through-chat for autonomy loops.
- No **patch apply**, **implement proposal**, or **run command** from this flow.
- No **real LLM** or **external API** calls in confirmation/guard tests.
- No **UI/API route** that creates confirmations from operator chat (store is library-only until wired).

### Implemented (data-only)

| Item | Location |
|------|----------|
| Confirmation store | `project_guardian/governance/operator_confirmation_store.py` |
| Storage | `data/runtime/operator_confirmations.jsonl` |
| Tests | `project_guardian/tests/test_operator_confirmation_store.py` |
| Runtime validation integration | `project_guardian/brain/live_execution_runtime.py` |
| Integration tests | `project_guardian/tests/test_operator_confirmation_guard_integration.py` |

---

## J. References

| Component | Path |
|-----------|------|
| Guard policy | `project_guardian/governance/live_execution_guard.py` |
| Runtime adapter | `project_guardian/brain/live_execution_runtime.py` |
| Brain entry | `project_guardian/brain/runtime.py` |
| Operator chat | `project_guardian/safe_stack/operator_chat.py` |
| Runtime API | `elysia/api/server.py` |
| Control panel | `project_guardian/ui_control_panel.py` |
| Audit log | `data/runtime/live_execution_guard_audit.jsonl` |
| Confirmation store | `project_guardian/governance/operator_confirmation_store.py` |
| Confirmations JSONL | `data/runtime/operator_confirmations.jsonl` |
| Governance plan | `docs/LIVE_EXECUTION_GOVERNANCE_PLAN.md` |
