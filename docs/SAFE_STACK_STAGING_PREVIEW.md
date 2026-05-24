# Safe-Stack Staging Preview

## Current git state

Generated: 2026-05-24.

This is a documentation-only staging preview. No files were staged or committed by this preview.

Inspected:

- `docs/SAFE_STACK_STAGING_MANIFEST.md`
- `docs/SAFE_STACK_PRE_STAGING_DIFF_REVIEW.md`
- `git status --short`
- `git diff --name-only`
- `git ls-files --others --exclude-standard`
- `git diff --cached --name-only`
- `git diff --cached --stat`

Current working tree summary:

- `git status --short` reports a mixed worktree with `404` status entries.
- Tracked modified entries: `159`.
- Visible untracked status entries: `239`.
- `git diff --name-only` resolves `158` tracked paths with unstaged diffs.
- `git ls-files --others --exclude-standard` reports `297` visible untracked files.
- A final cached-diff check shows `7` currently staged files with `604` insertions and `2` deletions. This preview did not create that staged state.

The worktree still mixes safe-stack milestone files with unrelated autonomy, LLM, mutation, launcher, MCP/OpenClaw, root-test, report, and runtime/generated changes. Do not use broad staging commands such as `git add -A`.

Currently staged files observed during this preview:

```text
.github/workflows/safe-stack-smoke.yml
.gitignore
Makefile
project_guardian/tests/test_safe_stack_ci_config.py
project_guardian/tests/test_safe_stack_gitignore.py
project_guardian/tests/test_safe_stack_smoke_script.py
scripts/run_safe_stack_smoke_tests.py
```

These staged files are within the manifest family, but they are not limited to Group 1. Review the cached diff before any commit.

## Manifest-matched stage candidates

Use `docs/SAFE_STACK_STAGING_MANIFEST.md` as the source of truth for staging, with patch review for the high-risk files called out below.

Group 1: safe-stack config and generated-data hygiene.

- `.gitignore`
- `README.md`
- `Makefile`
- `config/brain_pipeline.json`
- `config/memory_ranking.json`

Group 2: safe-stack production/runtime modules.

- `elysia/api/server.py`
- `project_guardian/ui_control_panel.py`
- `project_guardian/conversation_store.py`
- `project_guardian/orchestration/think_decide_act.py`
- `project_guardian/brain/`
- `project_guardian/governance/`
- `project_guardian/memory_ranking/`
- `project_guardian/prompt_contracts/`
- `project_guardian/safe_stack/`
- `project_guardian/self_improvement/`

Group 3: smoke-covered safe-stack tests.

- Safe-stack smoke test files listed in `scripts/run_safe_stack_smoke_tests.py`.
- The current smoke runner covers `32` test files and `386` tests.

Group 4: adjacent cleanup tests.

- `project_guardian/tests/test_brain_config_runtime.py`
- `project_guardian/tests/test_conversation_store_consolidation.py`
- `project_guardian/tests/test_safe_stack_ci_config.py` is already included in the smoke group.

Group 5: safe-stack docs, audits, and plans.

- The manifest-listed safe-stack docs should be staged as a docs group.
- Add `docs/SAFE_STACK_PRE_STAGING_DIFF_REVIEW.md` to this docs group if the operator wants the latest pre-staging review included.
- Add this file, `docs/SAFE_STACK_STAGING_PREVIEW.md`, to this docs group if the operator wants the current preview included.

Group 6: safe-stack smoke script, CI, and quarantined one-shot scripts.

- `.github/workflows/safe-stack-smoke.yml`
- `scripts/run_safe_stack_smoke_tests.py`
- `scripts/maintenance/one_shot/`

The manifest-matched candidate check found the core config, production/runtime, governance, safe-stack, CI, and smoke-script paths present in the working tree.

## Excluded/do-not-stage files

Do not stage generated/runtime data or local audit captures:

- `.broader_test_audit_pg.txt`
- `REPORTS/broader_audit_pg_maxfail80.txt`
- `REPORTS/broader_audit_pg_tests.txt`
- `REPORTS/broader_audit_tests_root.txt`
- `REPORTS/review_queue.jsonl`
- `data/runtime/`
- `data/context_pipeline/`
- `data/prompt_registry/`
- `deployments/`
- `elysia_timeline.db-journal`
- `memory/heartbeat-state.json`
- `ollama_server_log.txt`
- `tmp_*.err`
- `tmp_*.out`

Do not stage unrelated config, autonomy, LLM routing, mutation, MCP/OpenClaw, launcher, root-test, or proposal work unless separately reviewed and explicitly scoped.

Examples visible in the current worktree but outside this safe-stack preview:

- `config/autonomy.json`
- `config/llm_router.yaml`
- `config/openclaw.json`
- `elysia.py`
- `elysia/runtime.py`
- `project_guardian/autonomy_*.py`
- `project_guardian/llm/`
- `project_guardian/mutation*.py`
- `project_guardian/openclaw_adapter.py`
- `project_guardian/tool_executor.py`
- `proposals/`
- `tests/`
- launcher scripts such as `START_ELYSIA_UNIFIED.bat`, `START_OPENCLAW_STUB.bat`, and `TOGGLE_ELYSIA_DESKTOP.bat`

## High-risk files requiring patch review

Patch-review before staging:

- `project_guardian/ui_control_panel.py`
- `elysia/api/server.py`
- `.gitignore`
- `project_guardian/brain/live_execution_runtime.py`
- `project_guardian/brain/runtime.py`
- `project_guardian/conversation_store.py`
- `scripts/run_safe_stack_smoke_tests.py`

Review focus:

- `project_guardian/ui_control_panel.py` is the largest tracked safe-stack candidate and still contains legacy autonomy/execute-cycle UI surfaces in the same file.
- `elysia/api/server.py` contains safe-stack mirrored routes, but also proposal implementation routes and `_run_implementation`.
- `.gitignore` intentionally hides broad generated/runtime paths and should be reviewed before staging.
- `project_guardian/brain/live_execution_runtime.py` must remain validation-only and must continue forcing dry-run when live execution is denied.
- `project_guardian/brain/runtime.py` should only add guard metadata and must not add executor/autonomy behavior.
- `project_guardian/conversation_store.py` performs local JSONL conversation persistence and bounded deletion; review the mutation boundaries.
- `scripts/run_safe_stack_smoke_tests.py` uses `subprocess.run` only as a pytest test runner and should not be treated as runtime tooling.

## Missing expected files

No missing files were found in the checked core manifest stage candidates for config, production/runtime modules, governance modules, safe-stack modules, CI workflow, and smoke script.

Manifest freshness gaps:

- `docs/SAFE_STACK_PRE_STAGING_DIFF_REVIEW.md` exists and is untracked, but it was created after the manifest and is not listed in Group 5.
- `docs/SAFE_STACK_STAGING_PREVIEW.md` exists only after this task and is not listed in the existing manifest.
- `project_guardian/tests/test_runtime_api_conversations.py` is referenced in the pre-staging review as coverage for runtime API behavior, but it is not in the manifest smoke group. Keep it excluded unless the operator explicitly scopes it.

## Generated/runtime visibility check

Normal untracked visibility still includes report/audit artifacts that should not be staged:

- `.broader_test_audit_pg.txt`
- `REPORTS/broader_audit_pg_maxfail80.txt`
- `REPORTS/broader_audit_pg_tests.txt`
- `REPORTS/broader_audit_tests_root.txt`

Tracked generated data remains visible because it is already tracked:

- `REPORTS/review_queue.jsonl`

Ignored generated/runtime paths are hidden from normal untracked output and show as ignored with `git status --short --ignored`:

- `data/context_pipeline/`
- `data/prompt_registry/`
- `data/runtime/`
- `deployments/`
- `memory/heartbeat-state.json`
- `ollama_server_log.txt`
- `tmp_elysia_live*.err`
- `tmp_elysia_live*.out`
- `tmp_ollama_autostart.*`
- `tmp_project_guardian_ui.*`

This means the `.gitignore` coverage is active, but visible report text files and the tracked review queue still require manual exclusion.

## Proposed commit order

Recommended order if the operator proceeds with staging:

1. Safe-stack generated-data hygiene and smoke infrastructure.
2. Safe-stack docs, audits, governance plans, and staging review documents.
3. Safe-stack data-only/runtime helper modules with guard/governance behavior.
4. Safe-stack API/control-panel visibility surfaces, using patch review for high-risk files.
5. Smoke-covered tests and adjacent cleanup tests.
6. Quarantined one-shot UI maintenance scripts and CI workflow.

Keep unrelated autonomy, LLM routing, mutation, OpenClaw/MCP, launcher, report, runtime/generated, root-test, and proposal work out of this milestone.

## Verification commands

Before staging:

```powershell
git status --short
git diff --name-only
git ls-files --others --exclude-standard
python scripts/run_safe_stack_smoke_tests.py
```

After any future staging, before commit:

```powershell
git diff --cached --name-only
git diff --cached --stat
git status --short
python -m pytest project_guardian/tests/test_brain_config_runtime.py project_guardian/tests/test_conversation_store_consolidation.py project_guardian/tests/test_safe_stack_ci_config.py -q
python scripts/run_safe_stack_smoke_tests.py
python -m pytest project_guardian/tests/test_safe_stack_gitignore.py -q
```

Do not commit if the cached diff includes generated/runtime data, local audit captures, report queues, unrelated autonomy/LLM/mutation work, OpenClaw/MCP work, launcher changes, or root `tests/` legacy work.
