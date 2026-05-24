# Elysia brain architecture (operator view)

## BrainPipeline and Think–Decide–Act

The unified **BrainPipeline** coordinates observation, optional **Think–Decide–Act (TDA)**, memory writes, and optional self-improvement enqueueing. Persisted traces are summarized for operators; raw TDA payloads are not exposed on dashboard APIs.

## Trace visibility

- **API:** `GET /api/brain/trace/latest` (Elysia runtime API and control panel).
- **Module:** `project_guardian/brain/trace_visibility.py` — `load_latest_brain_trace_summary()`.
- **Storage:** path from `BrainPipelineConfig.trace_path` (typically under `data/runtime/`).

Summary fields include `enabled`, `dry_run`, `trace_exists`, `brain_pipeline_id`, `started_at`, `input_source`, `risk_level`, `execution_success`, `tda_used`, `stage_count`, `last_transition`, `memory_written`, `self_improvement_queued`, `self_improvement_proposal_count`, and `trace_path`.

### TDA trace field naming

| Role | Field |
|------|--------|
| **Canonical detailed trace** (persisted JSON, `BrainPipelineTrace`) | `think_decide_act_trace` |
| **Compatibility alias** (same dict reference when written) | `tda_trace` |
| **Present flag** (persisted / dashboard) | `think_decide_act_trace_present` |
| **Compact API/UI flag** (summary only; not a second blob) | `tda_used` |

Helpers live in `project_guardian/brain/tda_trace_fields.py` (`get_think_decide_act_trace`, `has_think_decide_act_trace`, `apply_persisted_tda_fields`). `BrainPipelineTrace.tda_trace` is a property alias of `think_decide_act_trace` for older tests and callers.

`GET /api/brain/trace/latest` does **not** return the detailed TDA dict—only `tda_used` and other sanitized summary keys.

## Self-improvement proposals

When the pipeline enqueues learning outcomes, proposals are written to the canonical JSONL queue. See [SELF_IMPROVEMENT_PROPOSAL_QUEUE.md](SELF_IMPROVEMENT_PROPOSAL_QUEUE.md).

## Control panel

The **Dashboard** tab includes a **Brain Trace & Self-Improvement** section:

- Refresh trace / proposals manually, or rely on periodic dashboard polling.
- Review proposals and set status via the control panel; **no code is applied** from this UI.

Autonomy and live execution remain separate controls and are not enabled by these views.
