# Safe-Stack Staging Manifest

## Current verification

Generated: 2026-05-24.

Inspected:

- `git status --short`
- `git diff --name-only`
- `git ls-files --others --exclude-standard`
- `docs/SAFE_STACK_COMMIT_STAGING_PLAN.md`
- `docs/BROADER_TEST_AUDIT.md`

Latest targeted adjacent cleanup command:

```powershell
python -m pytest project_guardian/tests/test_brain_config_runtime.py project_guardian/tests/test_conversation_store_consolidation.py project_guardian/tests/test_safe_stack_ci_config.py -q
```

Result:

- Passed.
- `33 passed, 3 warnings in 0.54s`

Latest safe-stack smoke command:

```powershell
python scripts/run_safe_stack_smoke_tests.py
```

Result:

- Passed.
- `386 passed, 3 warnings in 5.46s`

Current git state remains a mixed worktree. Safe-stack files and the adjacent cleanup files are present alongside unrelated tracked modifications, runtime/generated data, local audit captures, launcher work, autonomy/LLM/mutation work, OpenClaw/MCP work, and broader environmental test failures. Do not use broad staging.

### Post–3E warning — unstaged `elysia/api/server.py` hunks

**3E committed:** `da8d0ae` — `feat(safe-stack): wire runtime and control panel safe-stack surfaces`

- Safe-stack server wiring (ConversationStore, operator chat, read-only brain/governance/memory/prompt/self-improvement routes) is **already in that commit**.
- **`project_guardian/ui_control_panel.py`** matches `da8d0ae` on disk (no remaining unstaged UI diff for 3E).

**Do not stage** the remaining unstaged proposal-implementation / WebScout hunks in `elysia/api/server.py` as part of this safe-stack milestone:

- `auto_implement_on_approval`, `_approval_should_implement`, `_run_implementation`
- Approval/status transition implementation hooks
- Implement route refactor and new `/implementation/preview`
- WebScout `research_options` expansion

Details: `docs/SERVER_UNSTAGED_RISKY_HUNKS.md`, `docs/SAFE_STACK_POST_3E_REVIEW.md`

```powershell
# Verify isolation before Group 4+ staging
git diff --cached --name-only          # must be empty
git diff --name-only -- elysia/api/server.py   # risky hunks still only here until separate track
```

Do **not** run `git add elysia/api/server.py` without `git add -p` and explicit review of every hunk.

## Exact files to stage by group

### Group 1 - Safe-stack config and generated-data hygiene

Stage only the safe-stack hunks in tracked files where needed:

```text
.gitignore
README.md
Makefile
config/brain_pipeline.json
config/memory_ranking.json
```

Notes:

- Stage `.gitignore` for generated safe-stack runtime ignore coverage.
- Stage `README.md` only for safe-stack smoke command documentation if unrelated README changes are present.
- Stage `Makefile` for the optional `safe-smoke` target used by static CI tests.
- Do not stage other config files in this group.

### Group 2 - Safe-stack production/runtime modules

```text
elysia/api/server.py
project_guardian/ui_control_panel.py
project_guardian/conversation_store.py
project_guardian/orchestration/think_decide_act.py
project_guardian/brain/__init__.py
project_guardian/brain/config.py
project_guardian/brain/context_builder_module.py
project_guardian/brain/contracts.py
project_guardian/brain/dashboard_module.py
project_guardian/brain/execution_module.py
project_guardian/brain/learning_module.py
project_guardian/brain/live_execution_runtime.py
project_guardian/brain/llm_router_module.py
project_guardian/brain/memory_module.py
project_guardian/brain/memory_ranking.py
project_guardian/brain/pipeline.py
project_guardian/brain/planner_module.py
project_guardian/brain/risk_module.py
project_guardian/brain/runtime.py
project_guardian/brain/self_improvement_module.py
project_guardian/brain/tda_trace_fields.py
project_guardian/brain/think_decide_act_adapter.py
project_guardian/brain/tool_router_module.py
project_guardian/brain/trace_visibility.py
project_guardian/governance/__init__.py
project_guardian/governance/live_execution_audit.py
project_guardian/governance/live_execution_guard.py
project_guardian/governance/operator_confirmation_store.py
project_guardian/governance/operator_confirmation_visibility.py
project_guardian/memory_ranking/__init__.py
project_guardian/memory_ranking/ranking.py
project_guardian/memory_ranking/visibility.py
project_guardian/prompt_contracts/__init__.py
project_guardian/prompt_contracts/contracts.py
project_guardian/prompt_contracts/controls.py
project_guardian/prompt_contracts/default_contracts.py
project_guardian/prompt_contracts/integration.py
project_guardian/prompt_contracts/registry.py
project_guardian/prompt_contracts/status.py
project_guardian/prompt_contracts/validation.py
project_guardian/safe_stack/__init__.py
project_guardian/safe_stack/operator_chat.py
project_guardian/safe_stack/responses.py
project_guardian/self_improvement/__init__.py
project_guardian/self_improvement/prompt_export.py
project_guardian/self_improvement/proposal_queue.py
```

Adjacent cleanup included in this group:

- `project_guardian/brain/runtime.py` now tolerates mocked non-trace returns by using `getattr(trace, "run_context", None)` before adding guard metadata. This preserves real `BrainPipelineTrace` behavior and does not enable live execution.

Notes:

- **3E complete for hosts:** `elysia/api/server.py` safe-stack hunks are in `da8d0ae`; do not re-stage that file for milestone Groups 4–6 while unstaged implementation/WebScout hunks remain (see post–3E warning above).
- Use patch staging for `elysia/api/server.py` and `project_guardian/ui_control_panel.py` if unrelated hunks are mixed into those tracked files.
- Live execution remains disabled by config and guard behavior.
- Autonomy remains unwired.

### Group 3 - Smoke-covered safe-stack tests

These are the exact test files resolved by `scripts/run_safe_stack_smoke_tests.py` in the latest smoke run:

```text
project_guardian/tests/test_api_host_route_parity.py
project_guardian/tests/test_brain_tda_integration.py
project_guardian/tests/test_brain_trace_visibility.py
project_guardian/tests/test_conversation_store.py
project_guardian/tests/test_control_panel_brain_visibility.py
project_guardian/tests/test_control_panel_chat_memory.py
project_guardian/tests/test_control_panel_js_smoke.py
project_guardian/tests/test_control_panel_legacy_history_retirement.py
project_guardian/tests/test_control_panel_operator_chat_helper_integration.py
project_guardian/tests/test_control_panel_ui_clarity.py
project_guardian/tests/test_live_execution_governance_docs.py
project_guardian/tests/test_live_execution_guard.py
project_guardian/tests/test_live_execution_guard_runtime_integration.py
project_guardian/tests/test_memory_ranking.py
project_guardian/tests/test_memory_ranking_imports.py
project_guardian/tests/test_memory_ranking_visibility.py
project_guardian/tests/test_one_shot_ui_scripts_quarantined.py
project_guardian/tests/test_operator_chat_helper.py
project_guardian/tests/test_operator_confirmation_context_plan.py
project_guardian/tests/test_operator_confirmation_guard_integration.py
project_guardian/tests/test_operator_confirmation_store.py
project_guardian/tests/test_operator_confirmation_visibility.py
project_guardian/tests/test_prompt_contract_controls.py
project_guardian/tests/test_prompt_contract_integration.py
project_guardian/tests/test_prompt_contracts.py
project_guardian/tests/test_runtime_operator_chat_helper_integration.py
project_guardian/tests/test_safe_stack_ci_config.py
project_guardian/tests/test_safe_stack_gitignore.py
project_guardian/tests/test_safe_stack_response_helpers.py
project_guardian/tests/test_safe_stack_smoke_script.py
project_guardian/tests/test_self_improvement_legacy_queue_retirement.py
project_guardian/tests/test_self_improvement_prompt_export.py
project_guardian/tests/test_self_improvement_proposal_queue.py
project_guardian/tests/test_tda_trace_fields.py
```

### Group 4 - Adjacent cleanup tests

These are outside the smoke list but were targeted and are now green:

```text
project_guardian/tests/test_brain_config_runtime.py
project_guardian/tests/test_conversation_store_consolidation.py
```

`project_guardian/tests/test_safe_stack_ci_config.py` is also part of the adjacent targeted command, but it is already listed in Group 3 because the smoke script includes it.

### Group 5 - Safe-stack docs, audits, and plans

```text
docs/API_HOST_FINAL_CONSOLIDATION_AUDIT.md
docs/API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md
docs/BROADER_TEST_AUDIT.md
docs/CONTROL_PANEL_CONVERSATION_MEMORY.md
docs/ELYSIA_ARCHITECTURE_AUDIT.md
docs/ELYSIA_ARCHITECTURE_CHECKPOINT.md
docs/ELYSIA_SAFE_STACK_AUDIT.md
docs/ELYSIA_SAFE_STACK_FINAL_CHECKPOINT.md
docs/LIVE_EXECUTION_GOVERNANCE_CHECKPOINT.md
docs/LIVE_EXECUTION_GOVERNANCE_PLAN.md
docs/MEMORY_RANKING_AND_COMPRESSION.md
docs/ONE_ENTRY_OPERATOR_INTERFACE_PLAN.md
docs/OPERATOR_CHAT_HELPER_AUDIT.md
docs/OPERATOR_CHAT_HELPER_PLAN.md
docs/OPERATOR_CONFIRMATION_CONTEXT_PLAN.md
docs/PROMPT_CONTRACTS.md
docs/SAFE_STACK_COMMIT_STAGING_PLAN.md
docs/SAFE_STACK_RELEASE_READINESS_AUDIT.md
docs/SAFE_STACK_STAGING_MANIFEST.md
docs/SELF_IMPROVEMENT_PROPOSAL_QUEUE.md
docs/THINK_DECIDE_ACT_PIPELINE.md
```

Adjacent cleanup included in this group:

- `docs/BROADER_TEST_AUDIT.md` records the fixed adjacent tests and deferred full-suite failures.
- `docs/ELYSIA_ARCHITECTURE_CHECKPOINT.md` records the Safe stack smoke command and workflow marker required by CI config tests.

### Group 6 - Safe-stack smoke script, CI, and quarantined one-shot scripts

```text
.github/workflows/safe-stack-smoke.yml
scripts/run_safe_stack_smoke_tests.py
scripts/maintenance/one_shot/README.md
scripts/maintenance/one_shot/_apply_control_panel_secondary_clarity.py
scripts/maintenance/one_shot/_apply_control_panel_ui_clarity.py
scripts/maintenance/one_shot/_patch_prompt_contract_ui.py
scripts/maintenance/one_shot/_restore_safe_stack_control_panel_ui.py
```

These one-shot UI repair scripts are maintenance artifacts only. They are not runtime tooling and are guarded by `project_guardian/tests/test_one_shot_ui_scripts_quarantined.py`.

## Do-not-stage list

### Runtime/generated data and local audit captures

```text
.broader_test_audit_pg.txt
REPORTS/broader_audit_pg_maxfail80.txt
REPORTS/broader_audit_pg_tests.txt
REPORTS/broader_audit_tests_root.txt
REPORTS/review_queue.jsonl
data/runtime/
data/context_pipeline/
data/prompt_registry/
deployments/
elysia_timeline.db-journal
memory/heartbeat-state.json
ollama_server_log.txt
tmp_*.err
tmp_*.out
```

### Unrelated or unsafe-to-mix configs

```text
config/adversarial_policy_recommendations.json
config/auto_learning.json
config/autonomy.json
config/context_pipeline.json
config/llm_router.yaml
config/mcp_capability_allowlist.example.json
config/mcp_servers.example.json
config/memory_pressure.json
config/mission_autonomy.json
config/mistral_decider.json
config/openclaw.json
config/openclaw_provider_elysia.example.json
config/prompt_evolution.json
config/social_intelligence.json
```

### Unrelated production/runtime areas

```text
elysia.py
elysia/runtime.py
elysia/config.py
elysia/agents/
elysia/api/conversation_store.py
elysia_config.py
elysia_interface.py
elysia_sub_apikeys.py
elysia_sub_income.py
elysia_sub_modules.py
elysia_entrypoint.py
load_api_keys.py
project_guardian/adversarial_self_learning.py
project_guardian/ai_mutation_validator.py
project_guardian/ai_tool_registry_engine.py
project_guardian/api_key_manager.py
project_guardian/api_usage_meter.py
project_guardian/ask_ai.py
project_guardian/auto_learning.py
project_guardian/autonomy_*.py
project_guardian/bounded_browser/
project_guardian/capability_execution.py
project_guardian/context_pipeline/
project_guardian/core.py
project_guardian/implementer/
project_guardian/llm/
project_guardian/llm_trace_jsonl.py
project_guardian/mcp_capability.py
project_guardian/mcp_stdio_bridge.py
project_guardian/mission_autonomy.py
project_guardian/multi_api_router.py
project_guardian/mutation*.py
project_guardian/openclaw_adapter.py
project_guardian/prompts/
project_guardian/prompt_evolution.py
project_guardian/tool_executor.py
project_guardian/unified_api_budget.py
project_guardian/unified_llm_route.py
proposals/
```

### Launchers, local services, and unrelated scripts

```text
START_ELYSIA_LOCAL_MISTRAL.bat
START_ELYSIA_UNIFIED.bat
START_OPENCLAW_STUB.bat
STOP_ELYSIA_DESKTOP.bat
Start Project Guardian.bat
Start Project Guardian (Replace).bat
Start_Elysia_Backend.cmd
TOGGLE_ELYSIA_DESKTOP.bat
create_elysia_desktop_shortcut.ps1
ensure_ollama_running.ps1
ensure_openclaw_running.ps1
run_elysia_unified.py
toggle_elysia_desktop.py
wait_for_elysia_backend.py
scripts/_audit_release_readiness.py
scripts/autonomy_loop_health.py
scripts/brain_diagnostic.py
scripts/context_pipeline_tune_from_status.py
scripts/elysia_overnight_digest.py
scripts/elysia_selfbuild_operator.py
scripts/mcp_probe.py
scripts/openclaw_stub_worker.py
scripts/register_discovered_capabilities.py
scripts/run_replay_prompts.py
scripts/verify_openclaw_elysia_wiring.ps1
```

### Tests outside this stage set

```text
project_guardian/tests/test_context_pipeline.py
project_guardian/tests/test_memory_ranking_consolidation.py
project_guardian/tests/test_tda_trace_naming.py
project_guardian/tests/test_unified_structured_role.py
tests/
```

Do not stage full-suite failure fixes in this safe-stack manifest unless they are verified and explicitly scoped in a separate pass.

## Manual staging commands

These are commands for a human maintainer to run later. They were not run while creating or refreshing this manifest.

Patch-stage tracked files that may contain unrelated hunks:

```powershell
git add -p -- .gitignore README.md elysia/api/server.py project_guardian/ui_control_panel.py
```

Stage safe-stack config and developer command docs:

```powershell
git add -- Makefile config/brain_pipeline.json config/memory_ranking.json
```

Stage safe-stack production/runtime modules, including the adjacent runtime compatibility fix:

```powershell
git add -- project_guardian/conversation_store.py project_guardian/orchestration/think_decide_act.py
git add -- project_guardian/brain project_guardian/governance project_guardian/memory_ranking
git add -- project_guardian/prompt_contracts project_guardian/safe_stack project_guardian/self_improvement
```

Stage the smoke-covered tests:

```powershell
git add -- project_guardian/tests/test_api_host_route_parity.py
git add -- project_guardian/tests/test_brain_tda_integration.py project_guardian/tests/test_brain_trace_visibility.py
git add -- project_guardian/tests/test_conversation_store.py
git add -- project_guardian/tests/test_control_panel_brain_visibility.py project_guardian/tests/test_control_panel_chat_memory.py
git add -- project_guardian/tests/test_control_panel_js_smoke.py project_guardian/tests/test_control_panel_legacy_history_retirement.py
git add -- project_guardian/tests/test_control_panel_operator_chat_helper_integration.py project_guardian/tests/test_control_panel_ui_clarity.py
git add -- project_guardian/tests/test_live_execution_governance_docs.py project_guardian/tests/test_live_execution_guard.py project_guardian/tests/test_live_execution_guard_runtime_integration.py
git add -- project_guardian/tests/test_memory_ranking.py project_guardian/tests/test_memory_ranking_imports.py project_guardian/tests/test_memory_ranking_visibility.py
git add -- project_guardian/tests/test_one_shot_ui_scripts_quarantined.py project_guardian/tests/test_operator_chat_helper.py
git add -- project_guardian/tests/test_operator_confirmation_context_plan.py project_guardian/tests/test_operator_confirmation_guard_integration.py
git add -- project_guardian/tests/test_operator_confirmation_store.py project_guardian/tests/test_operator_confirmation_visibility.py
git add -- project_guardian/tests/test_prompt_contract_controls.py project_guardian/tests/test_prompt_contract_integration.py project_guardian/tests/test_prompt_contracts.py
git add -- project_guardian/tests/test_runtime_operator_chat_helper_integration.py
git add -- project_guardian/tests/test_safe_stack_ci_config.py project_guardian/tests/test_safe_stack_gitignore.py
git add -- project_guardian/tests/test_safe_stack_response_helpers.py project_guardian/tests/test_safe_stack_smoke_script.py
git add -- project_guardian/tests/test_self_improvement_legacy_queue_retirement.py project_guardian/tests/test_self_improvement_prompt_export.py project_guardian/tests/test_self_improvement_proposal_queue.py
git add -- project_guardian/tests/test_tda_trace_fields.py
```

Stage the adjacent cleanup tests:

```powershell
git add -- project_guardian/tests/test_brain_config_runtime.py project_guardian/tests/test_conversation_store_consolidation.py
```

Stage docs, CI, and quarantined maintenance artifacts:

```powershell
git add -- docs/API_HOST_FINAL_CONSOLIDATION_AUDIT.md docs/API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md
git add -- docs/BROADER_TEST_AUDIT.md docs/CONTROL_PANEL_CONVERSATION_MEMORY.md
git add -- docs/ELYSIA_ARCHITECTURE_AUDIT.md docs/ELYSIA_ARCHITECTURE_CHECKPOINT.md
git add -- docs/ELYSIA_SAFE_STACK_AUDIT.md docs/ELYSIA_SAFE_STACK_FINAL_CHECKPOINT.md
git add -- docs/LIVE_EXECUTION_GOVERNANCE_CHECKPOINT.md docs/LIVE_EXECUTION_GOVERNANCE_PLAN.md
git add -- docs/MEMORY_RANKING_AND_COMPRESSION.md docs/ONE_ENTRY_OPERATOR_INTERFACE_PLAN.md
git add -- docs/OPERATOR_CHAT_HELPER_AUDIT.md docs/OPERATOR_CHAT_HELPER_PLAN.md
git add -- docs/OPERATOR_CONFIRMATION_CONTEXT_PLAN.md docs/PROMPT_CONTRACTS.md
git add -- docs/SAFE_STACK_COMMIT_STAGING_PLAN.md docs/SAFE_STACK_RELEASE_READINESS_AUDIT.md docs/SAFE_STACK_STAGING_MANIFEST.md
git add -- docs/SELF_IMPROVEMENT_PROPOSAL_QUEUE.md docs/THINK_DECIDE_ACT_PIPELINE.md
git add -- scripts/run_safe_stack_smoke_tests.py .github/workflows/safe-stack-smoke.yml scripts/maintenance/one_shot
```

## Final verification commands

Run these after staging and before committing:

```powershell
git diff --cached --name-only
git diff --cached --stat
git status --short
python -m pytest project_guardian/tests/test_brain_config_runtime.py project_guardian/tests/test_conversation_store_consolidation.py project_guardian/tests/test_safe_stack_ci_config.py -q
python scripts/run_safe_stack_smoke_tests.py
python -m pytest project_guardian/tests/test_safe_stack_gitignore.py -q
```

Review `git diff --cached --name-only` against this manifest. The staged set should not contain generated runtime data, report queues, local audit captures, autonomy changes, LLM/API routing changes, mutation executor work, OpenClaw/MCP work, or launcher changes.

## Remaining deferred failures

Do not fix or stage these in the safe-stack milestone unless a new task explicitly scopes them:

```text
project_guardian/tests/test_integration.py::TestEventLoopIntegration::test_module_adapter_execution
project_guardian/tests/test_introspection_ui.py::TestIntrospectionAPIIntegration::test_memory_patterns_endpoint
project_guardian/tests/test_memory_vector_deferred_embeddings.py::test_enhanced_memory_defers_vector_add_until_embeddings_enabled
project_guardian/tests/test_startup_smoke.py::TestStartupSmoke::test_startup_smoke_operational_state_structure
```

Known environmental/non-blocking noise:

```text
Ollama timeouts
elysia_timeline.db locks
gevent/UIControlPanel stalls
GuardianCore singleton boot/isolation issues
root tests/ legacy mutation, cleanup, and artifact-policy failures
```

The safe-stack smoke is green, the adjacent targeted cleanup tests are green, live execution remains disabled and fail-closed, and autonomy remains unwired.
