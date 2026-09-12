# Think-Decide-Act Pipeline

Project Guardian now has a focused staged pipeline for Elysia in
`project_guardian.orchestration.think_decide_act`.

The pipeline keeps one process from observing, reasoning, choosing, validating,
executing, reviewing, and remembering as one opaque action. Each run returns a
visible trace:

1. Observe
2. Think
3. Propose
4. Validate
5. Execute
6. Review
7. Remember

## Calling The Pipeline

```python
from project_guardian.orchestration import run_think_decide_act_pipeline

trace = run_think_decide_act_pipeline(
    {"source": "user_request", "raw_input": "search memory for deployment notes"},
    context={
        "relevant_context_ids": ["operator-session-42"],
        "memory_search_limit": 5,
    },
    guardian=guardian_core,
)

print(trace.to_dict())
```

The returned trace includes structured dataclasses for observation, thought,
proposal, validation, execution, review, optional memory record, and per-stage
logs.

## Dry Run

Use dry-run mode when another Elysia module wants a decision trace without
performing the action:

```python
trace = run_think_decide_act_pipeline(
    "check system health",
    context={"dry_run": True},
    guardian=guardian_core,
)
```

Dry-run mode still observes, thinks, proposes, validates, creates an execution
log entry, and reviews the result. It does not call the executor.

## Safety Notes

- Direct shell, terminal, subprocess, and destructive file-system requests are
  blocked during validation.
- LLM or user text is never converted into executable code or commands.
- Execution uses an injected executor, existing safe tool/capability bridges, or
  safe deferred/no-op paths.
- `module:` and `tool:` capability targets require either an injected approved
  executor or a matching `allowed_capabilities` entry.
- Useful memory summaries are redacted before storage. Raw credentials, tokens,
  secrets, and API keys are not written to memory by this pipeline.
- The review stage can recommend one retry for low/medium risk execution
  failures, but the pipeline does not loop automatically.

## Implementation Report

Implemented:

- Typed dataclasses for all seven stages and the full trace.
- `run_think_decide_act_pipeline(input_event, context=None, ...)` orchestrator.
- Conservative default risk checker with hooks for existing Guardian gates:
  `TrustEvalAction`, `TrustMatrix`, and `EAISafetyFramework` when available.
- Execution guard that refuses blocked actions and supports dry-run mode.
- Remember stage that writes only useful redacted summaries.
- Unit / smoke tests: `project_guardian/tests/test_think_decide_act_smoke.py` (dry-run executor skip, shell intent blocked).

## Relationship to `BrainPipeline`

`BrainPipeline` (`project_guardian/brain/pipeline.py`) is the **higher-level brain orchestrator** (context → memory → planner → LLM/tool routing → brain risk on the routed command). When `BrainPipeline.run(..., context={"use_think_decide_act": True})` is used, the routed action is passed into **this** pipeline through **`think_decide_act_adapter`**: the adapter builds a `preferred_action` `ActionProposal`, injects `BrainCapabilityExecutor` when a `guardian` exists, and returns a full **`ThinkDecideActTrace`** merged into the brain trace’s **`unified_export`** for UI/API visibility.

Think-Decide-Act remains the **staged validate / execute / review / remember** implementation; Brain does not duplicate those stages when the adapter is on. Default remains **`use_think_decide_act: False`** so existing callers keep direct `execute_capability` execution until they opt in.

## Migration Notes

Good future candidates to migrate into this staged trace:

- Mistral decision actions currently flowing through `project_guardian.tool_executor`.
- Bounded capability execution paths in `project_guardian.orchestration.pipelines.serial`.
- Chat capability pre-execution in `project_guardian.unified_llm_route`.
- Autonomous learning and diagnostic triggers that currently jump straight to a
  tool call.
- Any module that proposes file, network, mutation, subprocess, or deployment
  work before a shared validation trace exists.
