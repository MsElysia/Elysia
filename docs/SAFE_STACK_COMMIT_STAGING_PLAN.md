# Safe-Stack Commit Staging Plan

## Current git state summary

The repository is in a large mixed-worktree state. Safe-stack milestone files are present alongside unrelated or pre-existing production, configuration, runtime, and generated-data changes.

Recent inspection showed:

- Many tracked files are modified, including safe-stack files and unrelated runtime/autonomy/LLM/mutation-facing modules.
- Many safe-stack milestone files are new and untracked, including governance modules, operator-chat helpers, prompt-contract modules, memory-ranking modules, tests, docs, scripts, and CI configuration.
- `.gitignore` now includes generated/runtime safe-stack coverage for runtime JSON/JSONL, conversation data, audit logs, proposal queues, operator confirmation stores, deployment outputs, temporary output files, and local cache directories.
- `docs/SAFE_STACK_RELEASE_READINESS_AUDIT.md` records the release-readiness state and should be reviewed before staging.

This milestone should be staged manually by explicit path groups. Treat the tree as unsafe for broad staging.

## Warning not to use git add -A

Do not use:

```powershell
git add -A
git add .
git add --all
```

Those commands would risk staging unrelated runtime changes, generated files, autonomy-facing changes, LLM/API-facing changes, proposal queues, reports, and local machine artifacts. The safe-stack milestone should be assembled with explicit path staging and cached-diff review.

## Safe-stack commit groups

Recommended grouping:

1. Generated-data hygiene
   - `.gitignore`
   - `project_guardian/tests/test_safe_stack_gitignore.py`

2. Safe-stack runtime foundations
   - Conversation store
   - Operator-chat helper path
   - Brain pipeline/runtime dry-run guard plumbing
   - Governance guard, audit, confirmation store, and read-only visibility helpers
   - Self-improvement proposal data flow
   - Memory ranking and prompt-contract helpers

3. API and control-panel integration
   - Safe-stack API route consolidation
   - Read-only governance visibility endpoints
   - Control-panel marker and clarity fixes
   - Operator-chat/control-panel helper integration

4. Tests
   - Safe-stack, governance, prompt-contract, memory-ranking, operator-confirmation, control-panel marker, CI, and smoke-script regression tests.

5. Documentation and checkpoints
   - Architecture checkpoints
   - Governance plans and checkpoint reports
   - Release-readiness audit
   - One-entry operator interface plan
   - This staging plan

6. Scripts and CI
   - Safe-stack smoke script
   - Safe-stack CI workflow
   - Quarantined one-shot maintenance scripts and warnings

7. Safe-stack configuration defaults
   - Brain pipeline config
   - Memory-ranking config

Each group can be staged as a separate commit, or the groups can be staged together only after reviewing `git diff --cached --name-only` and `git diff --cached --stat`.

## Files/directories to stage

Stage these paths only after reviewing their current diffs:

```powershell
git add -- .gitignore
git add -- config/brain_pipeline.json config/memory_ranking.json
git add -- elysia/api/server.py project_guardian/ui_control_panel.py
git add -- project_guardian/conversation_store.py
git add -- project_guardian/brain
git add -- project_guardian/governance
git add -- project_guardian/memory_ranking
git add -- project_guardian/orchestration/think_decide_act.py
git add -- project_guardian/prompt_contracts
git add -- project_guardian/safe_stack
git add -- project_guardian/self_improvement
```

Safe-stack tests to stage include:

```powershell
git add -- project_guardian/tests/test_api_host_route_parity.py
git add -- project_guardian/tests/test_brain_pipeline_config.py
git add -- project_guardian/tests/test_brain_pipeline_trace.py
git add -- project_guardian/tests/test_brain_runtime.py
git add -- project_guardian/tests/test_conversation_store.py
git add -- project_guardian/tests/test_control_panel_advanced_ui_markers.py
git add -- project_guardian/tests/test_control_panel_brain_trace_panel.py
git add -- project_guardian/tests/test_control_panel_memory_ranking_panel.py
git add -- project_guardian/tests/test_control_panel_operator_chat_helper_integration.py
git add -- project_guardian/tests/test_control_panel_proposal_export.py
git add -- project_guardian/tests/test_control_panel_self_improvement_proposals_panel.py
git add -- project_guardian/tests/test_control_panel_ui_clarity.py
git add -- project_guardian/tests/test_live_execution_governance_docs.py
git add -- project_guardian/tests/test_live_execution_guard.py
git add -- project_guardian/tests/test_live_execution_guard_runtime_integration.py
git add -- project_guardian/tests/test_memory_ranking.py
git add -- project_guardian/tests/test_one_shot_ui_scripts_quarantined.py
git add -- project_guardian/tests/test_operator_chat_helper.py
git add -- project_guardian/tests/test_operator_confirmation_context_plan.py
git add -- project_guardian/tests/test_operator_confirmation_guard_integration.py
git add -- project_guardian/tests/test_operator_confirmation_store.py
git add -- project_guardian/tests/test_operator_confirmation_visibility.py
git add -- project_guardian/tests/test_prompt_contract_ui_panel.py
git add -- project_guardian/tests/test_prompt_contracts.py
git add -- project_guardian/tests/test_runtime_operator_chat_helper_integration.py
git add -- project_guardian/tests/test_safe_stack_ci_config.py
git add -- project_guardian/tests/test_safe_stack_gitignore.py
git add -- project_guardian/tests/test_safe_stack_response_helpers.py
git add -- project_guardian/tests/test_safe_stack_smoke_script.py
git add -- project_guardian/tests/test_self_improvement_proposals.py
git add -- project_guardian/tests/test_self_improvement_store.py
git add -- project_guardian/tests/test_tda_trace_fields.py
```

Safe-stack docs to stage include:

```powershell
git add -- docs/API_HOST_FINAL_CONSOLIDATION_AUDIT.md
git add -- docs/API_HOST_FINAL_CONSOLIDATION_CHECKPOINT.md
git add -- docs/CONTROL_PANEL_CONVERSATION_MEMORY.md
git add -- docs/ELYSIA_ARCHITECTURE_CHECKPOINT.md
git add -- docs/ELYSIA_SAFE_STACK_FINAL_CHECKPOINT.md
git add -- docs/LIVE_EXECUTION_GOVERNANCE_CHECKPOINT.md
git add -- docs/LIVE_EXECUTION_GOVERNANCE_PLAN.md
git add -- docs/MEMORY_RANKING_AND_COMPRESSION.md
git add -- docs/ONE_ENTRY_OPERATOR_INTERFACE_PLAN.md
git add -- docs/OPERATOR_CONFIRMATION_CONTEXT_PLAN.md
git add -- docs/PROMPT_CONTRACTS.md
git add -- docs/SAFE_STACK_COMMIT_STAGING_PLAN.md
git add -- docs/SAFE_STACK_RELEASE_READINESS_AUDIT.md
```

Safe-stack scripts and CI to stage include:

```powershell
git add -- scripts/run_safe_stack_smoke_tests.py
git add -- scripts/maintenance/one_shot
git add -- .github/workflows/safe-stack-smoke.yml
```

Use `git add -p` for `elysia/api/server.py` and `project_guardian/ui_control_panel.py` if their diffs contain unrelated edits.

## Files/directories to exclude

Do not stage generated/runtime data:

```text
data/runtime/
data/context_pipeline/
data/prompt_registry/
deployments/
tmp_*.out
tmp_*.err
ollama_server_log.txt
memory/heartbeat-state.json
REPORTS/*.json
REPORTS/*.jsonl
```

Do not stage unrelated or risky production changes unless they are reviewed as a separate milestone:

```text
elysia.py
elysia/runtime.py
project_guardian/core.py
project_guardian/mission_autonomy.py
project_guardian/autonomy_*.py
project_guardian/mutation*.py
project_guardian/tool_executor.py
project_guardian/capability_execution.py
project_guardian/implementer/
project_guardian/llm/
project_guardian/unified_llm_route.py
project_guardian/ask_ai.py
project_guardian/multi_api_router.py
config/autonomy.json
config/mission_autonomy.json
config/auto_learning.json
REPORTS/review_queue.jsonl
```

Do not stage launcher, environment, local-server, or experimental files unless separately requested and reviewed.

## Manual staging examples

Stage one group at a time and inspect the cache after each group:

```powershell
git add -- .gitignore project_guardian/tests/test_safe_stack_gitignore.py
git diff --cached --name-only
git diff --cached --stat
```

Stage core safe-stack modules:

```powershell
git add -- project_guardian/conversation_store.py project_guardian/safe_stack
git add -- project_guardian/brain project_guardian/governance
git add -- project_guardian/memory_ranking project_guardian/prompt_contracts
git add -- project_guardian/self_improvement project_guardian/orchestration/think_decide_act.py
git diff --cached --name-only
```

Stage API/control-panel changes cautiously:

```powershell
git add -p -- elysia/api/server.py
git add -p -- project_guardian/ui_control_panel.py
git diff --cached -- elysia/api/server.py project_guardian/ui_control_panel.py
```

Stage tests, docs, scripts, and CI by explicit path:

```powershell
git add -- project_guardian/tests/test_live_execution_guard.py project_guardian/tests/test_live_execution_guard_runtime_integration.py
git add -- project_guardian/tests/test_operator_confirmation_store.py project_guardian/tests/test_operator_confirmation_guard_integration.py
git add -- docs/LIVE_EXECUTION_GOVERNANCE_PLAN.md docs/LIVE_EXECUTION_GOVERNANCE_CHECKPOINT.md
git add -- scripts/run_safe_stack_smoke_tests.py .github/workflows/safe-stack-smoke.yml
git diff --cached --name-only
```

## Verification commands

Before committing, run:

```powershell
git diff --cached --name-only
git diff --cached --stat
git status --short
git ls-files --others --exclude-standard
python -m pytest project_guardian/tests/test_safe_stack_gitignore.py -q
python scripts/run_safe_stack_smoke_tests.py
```

Review the cached file list against the include/exclude lists above. The staged set should not include generated runtime data, proposal queues, local reports, or unrelated autonomy/LLM/mutation work.

## Risks/review notes

- `project_guardian/ui_control_panel.py` is likely to have a large diff and should be reviewed carefully before staging.
- `elysia/api/server.py` should be staged only for safe-stack route and read-only visibility work.
- Autonomy, mission-autonomy, mutation, implementer, tool-executor, and LLM/API-facing changes are outside this safe-stack staging plan.
- Runtime data and generated JSON/JSONL files must remain uncommitted even if useful during local testing.
- The safe-stack smoke passing is necessary but not a substitute for reviewing the staged diff.
- Live execution remains disabled, autonomy remains unwired, and this plan does not authorize any runtime behavior change.
