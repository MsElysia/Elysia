# Parallel AI — audit (Task 7)

## Orchestration: `parallel_compare_and_judge`

**Still wired:** `OrchestrationBroker.run_task` dispatches to `ParallelCompareAndJudgePipeline` when `route.pipeline_id == "parallel_compare_and_judge"` (`project_guardian/orchestration/broker.py`).

**Router (`RulesRouter.resolve`) selects parallel when any of:**

1. **YAML route** for task type `critique` defaults to parallel (`config/llm_router.yaml` embedded defaults in `router/rules.py`: `critique` → `parallel_compare_and_judge` with `fanout_models`).
2. **`task_type == CRITIQUE`** — forced to parallel with reason `task_type_critique`.
3. **`high_stakes` metadata** or governance hint **`escalate_reasoning`** — parallel, reason `governance_escalate_or_high_stakes`.
4. **`reasoning` + `uncertainty_level == high`** in context — parallel, reason `ambiguous_reasoning_uncertainty_high`.

**When OpenAI is unavailable** (`not _openai_available()`):

- Executor / fanout refs are coerced to local Ollama via `_fallback_local`.
- **`judge_model` is cleared** if it was OpenAI (`judge_m = None` when OpenAI ref and unavailable) — see `rules.py` ~250–268. The parallel pipeline may then rely more on deterministic judge behavior; confirm quality in your environment.

**Telemetry adaptation:** After the base decision, `adapt_route_from_telemetry` may escalate to parallel on repeated local failures (see tests `test_repeated_failures_escalate_parallel`).

## Elysia memory condensation (ThreadPoolExecutor)

**Location:** `elysia.py` → `condense_memory_with_ai` (~1369+).

**Behavior:** Oldest memory entries chunked (`chunk_size` default 80); each chunk processed in a worker via `_autonomy_llm_completion` (structured JSON contract). **`max_workers` default 4.**

**Risks to watch:** concurrent writes to the same memory object — ensure upstream does not mutate `memory_log` while futures run (current design assumes condensation owns the critical section until merge).

## Manual checklist (dev)

- [ ] From a Python REPL or small harness, build `TaskRequest` with `task_type=critique` (or matching `CRITIQUE` constant), call `OrchestrationBroker().run_task_sync(...)`, confirm `PipelineResult.pipeline_id == parallel_compare_and_judge` and two branch outputs before judge.
- [ ] With OpenAI disabled / no key, confirm parallel still runs (local-local fanout) and does not crash on `judge_model=None`.

## Automated coverage

- `project_guardian/tests/test_orchestration_parallel.py`
- `project_guardian/tests/test_router_telemetry_adapt.py` (parallel escalation / revert)
- `project_guardian/tests/test_router_rules.py` (`test_critique_parallel`, governance parallel)
