# Prompt contracts (validation integration)

Project Guardian defines **versioned JSON-shaped outputs** for planner, routers, risk, memory ranking, learning, and Think–Decide–Act stages under `project_guardian/prompt_contracts/`.

This document describes **optional runtime validation** wired into **BrainPipeline** and **Think–Decide–Act** without changing default production behavior.

## Default behavior

Unless explicitly enabled in context, **no prompt-contract validation runs**. Operator chat and normal BrainPipeline runs remain unchanged.

### Config (`config/brain_pipeline.json`)

Under `brain_pipeline.prompt_contract_validation` (all safe defaults):

| Key | Default | Meaning |
|-----|---------|---------|
| `enabled` | `false` | Master switch for config-driven validation context |
| `mode` | `warn` | `warn` or `strict` (strict only blocks when `dry_run` is true) |
| `modules` | planner, routers, risk, TDA modules | Module names passed as `prompt_contract_modules` |
| `operator_chat` | `false` | When true **and** `enabled`, operator-chat BrainPipeline traces may validate |

Operator chat does **not** validate unless `enabled` and `operator_chat` are both true. **Strict** mode is downgraded to **warn** when `dry_run` is not true.

## Operator visibility

- **API:** `GET /api/prompt-contracts/status` — config flags, contract catalog (id/module/version only), and compact latest validation from the persisted brain trace file. No raw prompts or model outputs.
- **Control panel:** Brain Trace area → **Prompt Contracts** panel (refresh only; does not write config).

## Enabling validation

Pass flags on the BrainPipeline `context` dict or Think–Decide–Act `context` dict:

```json
{
  "validate_prompt_contracts": true,
  "prompt_contract_mode": "warn",
  "prompt_contract_modules": [
    "planner",
    "tool_router",
    "llm_router",
    "risk_checker",
    "memory_ranker",
    "learning_reviewer",
    "think_decide_act_thinker",
    "think_decide_act_proposer"
  ]
}
```

- **`prompt_contract_modules` omitted**: all hooked modules for that pipeline may be validated when relevant (for example `memory_ranker` only runs when BrainPipeline `rank_memory` is true).
- **`prompt_contract_overrides`**: optional dict mapping a module name to a fixed payload (string or dict) used instead of the derived projection (tests / diagnostics).
- **`dry_validate_planner_contract`** plus **`dry_validate_planner_contract_sample`**: legacy planner-only hook remains supported and implies **warn-mode** validation for **planner** without requiring `validate_prompt_contracts`.

Legacy aliases for overrides also work via **`prompt_contract_validation_outputs`** (see `integration.resolve_prompt_contract_payload`).

## Modes

| Mode | Behavior |
|------|-----------|
| **off** | Default. No validation (`validate_prompt_contracts` false and no `dry_validate_planner_contract`). |
| **warn** | Validate; attach errors/warnings to traces; **never** block production execution on validation alone. |
| **strict** | Invalid output sets **`blocked`: true** when **`dry_run` is also true**. BrainPipeline may **early-abort** after planner validation only if strict fails there. TDA may **skip normal validate()** and inject a blocked `ValidationResult` so execution does not proceed as approved. |

**Production safety**: strict blocking **never activates** unless **`dry_run`** is true in the same context. Normal runtime (`dry_run` false) cannot strict-block from prompt contracts.

## Where results appear

### BrainPipeline

Serializable results live under:

`trace.run_context["prompt_contract_validation"][<module_name>]`

Each entry matches:

```json
{
  "module_name": "planner",
  "contract_id": "planner.v1",
  "valid": true,
  "errors": [],
  "warnings": [],
  "mode": "warn",
  "blocked": false
}
```

Planner-only legacy compatibility:

`trace.run_context["planner_contract_validation"]` → `{ "ok": bool, "errors": [...] }`

### Think–Decide–Act

Results are stored on the trace object:

`ThinkDecideActTrace.prompt_contract_validation`

Same per-module shape as above.

## Integration module

`project_guardian/prompt_contracts/integration.py` exposes helpers:

- `contract_mode_from_context`
- `should_validate_prompt_contracts`
- `validate_module_output_for_trace`
- `add_prompt_contract_result_to_trace`
- `resolve_prompt_contract_payload`
- Brain-oriented projection helpers (`brain_plan_to_contract_projection`, etc.)

No HTTP or LLM providers are imported here.

## Limitations

- Validation uses **projections** from internal datatypes (for example `Plan`, `ToolRouteDecision`) into contract-shaped JSON; modules are **not** forced to emit LLM JSON yet.
- **Forbidden reasoning keys** and **shell-like patterns** are detected **pattern-wise**, not semantically.
- Strict abort after planner only applies to **BrainPipeline**; other modules record **`blocked`** but do not stop the pipeline except as noted for **TDA validate override**.

## Diagnostic script

```bash
python scripts/prompt_contracts_diagnostic.py
```

Prints contract count, integration availability, and a tiny sample validation.
