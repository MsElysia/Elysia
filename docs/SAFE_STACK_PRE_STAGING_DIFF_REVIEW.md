# Safe-Stack Pre-Staging Diff Review

## Review scope

Date: 2026-05-24.

This is a documentation-only pre-staging review. No files were staged or committed by this review.

Inspected:

- `docs/SAFE_STACK_STAGING_MANIFEST.md`
- `git diff --stat`
- `git diff --name-only`
- `git status --short`

Tracked diff snapshot:

- `159 files changed`
- `22,948 insertions`
- `2,676 deletions`
- Largest tracked candidate: `project_guardian/ui_control_panel.py` with `3,849` changed lines in tracked diff.

High-risk staged-candidate files/directories reviewed:

- `.gitignore`
- `elysia/api/server.py`
- `project_guardian/ui_control_panel.py`
- `project_guardian/brain/runtime.py`
- `project_guardian/brain/live_execution_runtime.py`
- `project_guardian/safe_stack/`
- `project_guardian/governance/`
- `project_guardian/conversation_store.py`
- `scripts/run_safe_stack_smoke_tests.py`

Important git-state note:

- Several safe-stack modules are currently untracked, so `git diff --stat` does not describe their content. They were reviewed from the working tree.
- The worktree remains mixed with unrelated autonomy, LLM, mutation, launcher, OpenClaw/MCP, runtime data, and broader test-health files. Do not use `git add -A`.

## High-risk file summaries

### `project_guardian/ui_control_panel.py`

Summary:

- Very large tracked diff and the highest manual-review risk.
- Contains safe-stack UI visibility additions for conversation memory, brain trace visibility, prompt contracts, memory ranking, self-improvement proposal review, governance confirmation diagnostics, and operator chat helper integration.
- Safe-stack sections are review/visibility oriented and repeatedly label dry-run or review-only behavior.

Review findings:

- Red-flag scan found legacy/autonomy dashboard surfaces in the same file: `/api/autonomy`, `/api/autonomy/execute-cycle`, `run_autonomous_cycle`, and an `Execute` button for next actions.
- These autonomy/execute controls are outside the safe-stack staging intent and should not be expanded or treated as part of the safe-stack milestone.
- Because this file mixes safe-stack panels with older dashboard controls, it requires patch-level staging or careful full-file review.

Tests covering this area:

- `project_guardian/tests/test_control_panel_chat_memory.py`
- `project_guardian/tests/test_control_panel_legacy_history_retirement.py`
- `project_guardian/tests/test_control_panel_brain_visibility.py`
- `project_guardian/tests/test_control_panel_js_smoke.py`
- `project_guardian/tests/test_control_panel_operator_chat_helper_integration.py`
- `project_guardian/tests/test_control_panel_ui_clarity.py`
- `project_guardian/tests/test_one_shot_ui_scripts_quarantined.py`
- `project_guardian/tests/test_prompt_contract_controls.py`
- `project_guardian/tests/test_memory_ranking_visibility.py`
- `project_guardian/tests/test_operator_confirmation_visibility.py`

### `elysia/api/server.py`

Summary:

- Tracked diff is significant and includes mirrored safe-stack API routes for conversation storage, chat history, brain trace visibility, self-improvement proposals, prompt contracts, governance confirmation diagnostics, and memory ranking.
- Uses shared safe-stack response helpers where possible.

Review findings:

- Red-flag scan found proposal implementation surfaces already present in this file: `_run_implementation`, `/api/proposals/<proposal_id>/implement`, and implementation preview/status routes.
- Those implementation routes are outside the live-execution governance milestone and must be manually reviewed before staging the whole file.
- Safe-stack additions should remain read-only or review-only except for bounded conversation storage and proposal status updates.

Tests covering this area:

- `project_guardian/tests/test_api_host_route_parity.py`
- `project_guardian/tests/test_runtime_operator_chat_helper_integration.py`
- `project_guardian/tests/test_runtime_api_conversations.py`
- `project_guardian/tests/test_conversation_store_consolidation.py`
- `project_guardian/tests/test_safe_stack_response_helpers.py`

### `project_guardian/brain/runtime.py`

Summary:

- Runtime entry point for the config-gated BrainPipeline path.
- Calls `apply_live_execution_guard_to_context` before passing context into `BrainPipeline.run`.
- Adjacent cleanup changed the metadata annotation to use `getattr(trace, "run_context", None)` so mocked pipeline returns do not crash tests.

Review findings:

- No shell, subprocess, real LLM, external API, or autonomy call found.
- Runtime keeps BrainPipeline behind config and records compact live-execution guard metadata.
- Live execution remains fail-closed through `live_execution_runtime`.

Tests covering this area:

- `project_guardian/tests/test_brain_config_runtime.py`
- `project_guardian/tests/test_live_execution_guard_runtime_integration.py`
- `project_guardian/tests/test_brain_tda_integration.py`
- `project_guardian/tests/test_brain_trace_visibility.py`

### `project_guardian/brain/live_execution_runtime.py`

Summary:

- Validation-only wiring for the live-execution guard.
- Applies confirmation validation metadata, evaluates guard rules, forces `dry_run=True` when denied, and writes compact audit JSONL for attempted live enablement.

Review findings:

- No execution path is present.
- No shell, subprocess, real LLM, external API, or autonomy call found.
- The runtime explicitly injects `runtime_live_execution_not_enabled` when a request would otherwise pass validation, keeping the current integration validation-only.
- Audit append failure fails closed by adding `audit_write_failed`.

Tests covering this area:

- `project_guardian/tests/test_live_execution_guard_runtime_integration.py`
- `project_guardian/tests/test_operator_confirmation_guard_integration.py`
- `project_guardian/tests/test_live_execution_guard.py`

### `project_guardian/safe_stack/`

Summary:

- `operator_chat.py` provides framework-neutral operator chat turn orchestration.
- `responses.py` provides framework-neutral API response builders for mirrored safe-stack routes.

Review findings:

- `operator_chat.py` does not call LLMs, tools, shell, or autonomy; host code supplies the responder callback.
- `responses.py` is mostly read-only response shaping, with bounded conversation create/delete/history helpers and proposal status update response helpers.
- No real LLM/API calls found.

Tests covering this area:

- `project_guardian/tests/test_operator_chat_helper.py`
- `project_guardian/tests/test_runtime_operator_chat_helper_integration.py`
- `project_guardian/tests/test_control_panel_operator_chat_helper_integration.py`
- `project_guardian/tests/test_safe_stack_response_helpers.py`

### `project_guardian/governance/`

Summary:

- `live_execution_guard.py` is side-effect free and fail-closed.
- `live_execution_audit.py` writes compact, redacted audit JSONL for attempted live enablement.
- `operator_confirmation_store.py` stores data-only confirmation records.
- `operator_confirmation_visibility.py` exposes sanitized read-only summaries.

Review findings:

- No execution, shell, subprocess, real LLM, or external API calls found.
- `operator_confirmation_store.py` includes create/use/revoke data-store methods, but the current API/control-panel visibility path is read-only and does not mark confirmations used.
- High/blocked risk, autonomy context, self-modification, raw command, missing rollback, stale dry-run trace, and missing allowlist are denied by guard/store tests.

Tests covering this area:

- `project_guardian/tests/test_live_execution_guard.py`
- `project_guardian/tests/test_live_execution_guard_runtime_integration.py`
- `project_guardian/tests/test_operator_confirmation_store.py`
- `project_guardian/tests/test_operator_confirmation_guard_integration.py`
- `project_guardian/tests/test_operator_confirmation_visibility.py`
- `project_guardian/tests/test_live_execution_governance_docs.py`

### `project_guardian/conversation_store.py`

Summary:

- Durable JSONL-per-conversation store under `data/runtime/conversations`.
- Redacts obvious credentials before persistence or API return.
- Bounds text and conversation size.

Review findings:

- No LLM, external API, shell, subprocess, or autonomy behavior found.
- Writes local conversation JSONL and supports bounded delete of a sanitized conversation file.
- `delete_conversation` is intentionally limited by `sanitize_conversation_id` and the configured store directory, but should be reviewed as a state mutation.

Tests covering this area:

- `project_guardian/tests/test_conversation_store.py`
- `project_guardian/tests/test_conversation_store_consolidation.py`
- `project_guardian/tests/test_control_panel_chat_memory.py`
- `project_guardian/tests/test_runtime_operator_chat_helper_integration.py`

### `.gitignore`

Summary:

- Adds ignore coverage for safe-stack generated/runtime artifacts.
- Covers `data/runtime/`, `data/context_pipeline/`, `data/prompt_registry/`, `deployments/`, temp outputs, report JSON/JSONL, `.mypy_cache/`, and `.ruff_cache/`.

Review findings:

- No production behavior impact.
- Broad rules are intentional for generated data, but should be reviewed before staging because they can hide future runtime artifacts from `git status`.

Tests covering this area:

- `project_guardian/tests/test_safe_stack_gitignore.py`

### `scripts/run_safe_stack_smoke_tests.py`

Summary:

- Focused smoke runner for safe-stack tests.
- Lists exact pytest paths and safety reminders.

Review findings:

- Uses `subprocess.run` to invoke `python -m pytest`; this is expected for a test runner, not production runtime.
- Does not start services, use secrets, enable autonomy, or enable live execution.

Tests covering this area:

- `project_guardian/tests/test_safe_stack_smoke_script.py`
- `project_guardian/tests/test_safe_stack_ci_config.py`

## Tests covering each area

| Area | Primary tests |
|------|---------------|
| Control panel safe-stack UI | `test_control_panel_chat_memory.py`, `test_control_panel_brain_visibility.py`, `test_control_panel_js_smoke.py`, `test_control_panel_ui_clarity.py`, `test_control_panel_operator_chat_helper_integration.py` |
| Runtime API mirrored routes | `test_api_host_route_parity.py`, `test_runtime_operator_chat_helper_integration.py`, `test_safe_stack_response_helpers.py`, `test_conversation_store_consolidation.py` |
| Brain runtime and dry-run governance | `test_brain_config_runtime.py`, `test_brain_tda_integration.py`, `test_brain_trace_visibility.py`, `test_live_execution_guard_runtime_integration.py` |
| Live-execution guard | `test_live_execution_guard.py`, `test_live_execution_guard_runtime_integration.py`, `test_live_execution_governance_docs.py` |
| Operator confirmation store/visibility | `test_operator_confirmation_store.py`, `test_operator_confirmation_guard_integration.py`, `test_operator_confirmation_visibility.py`, `test_operator_confirmation_context_plan.py` |
| Operator chat helper | `test_operator_chat_helper.py`, `test_runtime_operator_chat_helper_integration.py`, `test_control_panel_operator_chat_helper_integration.py` |
| Conversation storage | `test_conversation_store.py`, `test_conversation_store_consolidation.py`, `test_control_panel_chat_memory.py` |
| Gitignore/runtime data hygiene | `test_safe_stack_gitignore.py` |
| Smoke/CI wiring | `test_safe_stack_smoke_script.py`, `test_safe_stack_ci_config.py` |

Current verified results from manifest context:

- Adjacent targeted tests: `33 passed`
- Safe-stack smoke: `386 passed`

## Red flags check

Blocking red flags found:

- None in the safe-stack guard/helper/governance/conversation-store modules reviewed.

Non-blocking high-risk findings requiring manual review:

- `project_guardian/ui_control_panel.py` contains legacy autonomy and execute-cycle controls in the same large file as safe-stack UI changes.
- `elysia/api/server.py` contains proposal implementation routes and `_run_implementation`; these are existing/high-risk surfaces and should not be confused with live-execution governance.
- `scripts/run_safe_stack_smoke_tests.py` uses `subprocess.run` only to execute pytest.
- `project_guardian/conversation_store.py` and safe-stack response helpers include conversation delete/clear behavior; bounded local state mutation should be reviewed.
- `.gitignore` adds broad runtime ignore rules; appropriate for generated data but easy to over-trust during staging.

Negative checks:

- No new production shell/subprocess call found in safe-stack helper/governance/conversation-store modules.
- No real LLM or external API call found in the safe-stack helper/governance/conversation-store modules.
- No autonomy wiring found in `project_guardian/brain/runtime.py`, `project_guardian/brain/live_execution_runtime.py`, `project_guardian/safe_stack/`, or `project_guardian/governance/`.
- Live execution remains disabled and fail-closed; current runtime integration is validation-only.

## Files needing manual review

Review before staging:

```text
project_guardian/ui_control_panel.py
elysia/api/server.py
.gitignore
project_guardian/brain/live_execution_runtime.py
project_guardian/brain/runtime.py
project_guardian/conversation_store.py
scripts/run_safe_stack_smoke_tests.py
```

Manual review focus:

- Patch-stage `project_guardian/ui_control_panel.py` or confirm its full diff is intended.
- Patch-stage `elysia/api/server.py` or confirm proposal implementation route changes are unrelated/pre-existing and not part of safe-stack live governance.
- Confirm `.gitignore` rules do not hide files that should be reviewed.
- Confirm `live_execution_runtime.py` still forces dry-run and adds `runtime_live_execution_not_enabled`.
- Confirm conversation delete/clear endpoints are intended local-state operations, not execution controls.
- Confirm smoke script remains a test runner only.

## Final verification commands

Run before staging:

```powershell
python -m pytest project_guardian/tests/test_brain_config_runtime.py project_guardian/tests/test_conversation_store_consolidation.py project_guardian/tests/test_safe_stack_ci_config.py -q
python scripts/run_safe_stack_smoke_tests.py
python -m pytest project_guardian/tests/test_safe_stack_gitignore.py -q
```

Run after staging and before commit:

```powershell
git diff --cached --name-only
git diff --cached --stat
git status --short
python -m pytest project_guardian/tests/test_brain_config_runtime.py project_guardian/tests/test_conversation_store_consolidation.py project_guardian/tests/test_safe_stack_ci_config.py -q
python scripts/run_safe_stack_smoke_tests.py
```

Do not commit if the cached diff includes runtime data, report queues, local audit captures, unrelated autonomy/LLM/mutation work, launcher work, OpenClaw/MCP work, or root `tests/` legacy cleanup.
