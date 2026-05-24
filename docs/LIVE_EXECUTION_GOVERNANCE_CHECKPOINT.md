# Live execution governance checkpoint

**Status:** Planning and validation only. **Do not enable live execution.**

## What is implemented

| Layer | Path | Notes |
|-------|------|--------|
| Fail-closed guard | `project_guardian/governance/live_execution_guard.py` | Blocks live paths unless explicitly allowed |
| Runtime adapter | `project_guardian/brain/live_execution_runtime.py` | Validates only; no execution |
| Operator confirmation store | `project_guardian/governance/operator_confirmation_store.py` | Append-only JSONL at `data/runtime/operator_confirmations.jsonl` |
| Confirmation validation in runtime | `project_guardian/brain/live_execution_runtime.py` | Loads confirmation by ID; does **not** mark used |
| Read-only visibility | `project_guardian/governance/operator_confirmation_visibility.py` | Sanitized diagnostics; no mutation |

## Read-only API (operator diagnostics)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/governance/operator-confirmations` | List summaries + governance flags |
| `GET` | `/api/governance/operator-confirmations/<operator_confirmation_id>` | Single record detail |

**Hosts:** `elysia/api/server.py` (`RuntimeAPIServer`), `project_guardian/ui_control_panel.py` (mirrored routes).

**Query parameters (list):** `limit` (default 25, max 50), optional `conversation_id`, optional `status`.

**Response highlights:** `available`, `read_only`, `live_execution_enabled`, `autonomy_enabled`, `dry_run`, `brain_pipeline_enabled`, `confirmation_store_path`, `counts` (`pending`, `used`, `expired`, `revoked`, `invalid`), `total`, `returned`, `limit`, `confirmations[]`, `warnings`.

Each confirmation summary includes: `operator_confirmation_id`, `status` (effective, including computed expiry), `created_at`, `expires_at`, `dry_run_trace_id`, `confirmed_action_id`, `action_summary`, `action_type`, `tool_name`, `risk_level`, `valid_now`, `validation_notes`. Raw prompts, traces, and secrets are **not** exposed.

## Explicit non-goals (unchanged)

- No confirmation **creation** API
- No `mark_operator_confirmation_used` from API or visibility layer
- No apply / run / execute controls
- No autonomy wiring
- No real LLM or external API calls from visibility
- **Config defaults unchanged** (`config/brain_pipeline.json`: pipeline off, dry-run on, live flags off)

## Tests

| File | Role |
|------|------|
| `project_guardian/tests/test_operator_confirmation_visibility.py` | 14 tests: empty store, counts, list/detail, expiry/used/revoked, redaction, limit, endpoint immutability, governance flags, static module scan |
| `project_guardian/tests/test_operator_confirmation_store.py` | Store persistence |
| `project_guardian/tests/test_operator_confirmation_guard_integration.py` | Guard + runtime validation |

**Visibility pytest:** `python -m pytest project_guardian/tests/test_operator_confirmation_visibility.py -q` → **14 passed**.

**Smoke slice:** includes visibility test module in `scripts/run_safe_stack_smoke_tests.py`. Run full slice with `python scripts/run_safe_stack_smoke_tests.py`.

## Default governance flags (read-only reporting)

With default `config/brain_pipeline.json`, visibility endpoints report:

- `live_execution_enabled`: **false**
- `autonomy_enabled`: **false**
- `dry_run`: **true**
- `brain_pipeline_enabled`: **false**
