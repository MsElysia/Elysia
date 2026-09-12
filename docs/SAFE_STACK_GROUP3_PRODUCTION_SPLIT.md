# Safe-stack Group 3 — production split plan

**Date:** 2026-05-18  
**Prior commits:** `1ada6e8` (smoke/CI), `aca1c1d` (config defaults)  
**Gate:** `python scripts/run_safe_stack_smoke_tests.py` → 386 passed

Do **not** use `git add -A` or `git add project_guardian/brain/`.

---

## Subcommit overview

| ID | Theme | Risk | Patch staging? |
|----|--------|------|----------------|
| **3A** | Shared conversation + safe_stack foundations | Low | No |
| **3B** | Advisory visibility (memory, prompts, proposals) | Low–medium | No |
| **3C** | Governance + live-execution guard runtime | Medium | No |
| **3D** | Brain pipeline (dry-run, trace, TDA) | Medium | No — stage **files**, not whole tree bulk |
| **3E** | API + control panel hosts | High | **Yes** (`git add -p`) |

---

## 3A — Shared foundations

**Commit message:** `feat(safe-stack): add shared conversation and response foundations`

### Files

| Path | Role |
|------|------|
| `project_guardian/conversation_store.py` | Canonical JSONL store, redaction |
| `project_guardian/safe_stack/__init__.py` | Package marker |
| `project_guardian/safe_stack/operator_chat.py` | Turn orchestration (no HTTP/LLM) |
| `project_guardian/safe_stack/responses.py` | Shared API response builders |
| `elysia/api/conversation_store.py` | Re-export shim → canonical store |

### Import note (review)

`responses.py` top-level imports `project_guardian.self_improvement.proposal_queue`. After **3A only**, a fresh clone can import `operator_chat` but importing `responses` fails until **3B** lands. Lazy imports inside `responses` also reference brain/memory/prompt/governance (modules on disk after later subcommits). **Run 3B soon after 3A** for a consistent tree.

### Risk: **Low** (no autonomy/live exec; disk writes under `data/runtime/` only at runtime)

### Tests (targeted)

```powershell
python -m pytest project_guardian/tests/test_conversation_store.py project_guardian/tests/test_operator_chat_helper.py project_guardian/tests/test_safe_stack_response_helpers.py project_guardian/tests/test_api_host_route_parity.py -q
```

### Smoke

```powershell
python scripts/run_safe_stack_smoke_tests.py
```

---

## 3B — Advisory visibility modules

**Suggested message:** `feat(safe-stack): add memory ranking, prompt contracts, and proposal queue`

### Files

```text
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
project_guardian/self_improvement/__init__.py
project_guardian/self_improvement/proposal_queue.py
project_guardian/self_improvement/prompt_export.py
```

### Risk: **Low–medium** (advisory/dry-run; `allow_delete_proposals: false` in config)

### Tests

```powershell
python -m pytest project_guardian/tests/test_memory_ranking.py project_guardian/tests/test_memory_ranking_visibility.py project_guardian/tests/test_prompt_contracts.py project_guardian/tests/test_prompt_contract_integration.py project_guardian/tests/test_prompt_contract_controls.py project_guardian/tests/test_self_improvement_proposal_queue.py project_guardian/tests/test_self_improvement_prompt_export.py -q
```

---

## 3C — Governance + guard runtime

**Suggested message:** `feat(safe-stack): add live-execution governance and guard runtime`

### Files

```text
project_guardian/governance/__init__.py
project_guardian/governance/live_execution_audit.py
project_guardian/governance/live_execution_guard.py
project_guardian/governance/operator_confirmation_store.py
project_guardian/governance/operator_confirmation_visibility.py
project_guardian/brain/live_execution_runtime.py
```

**Exclude:** `project_guardian/governance/operator_confirmation_store.py.bak`

### Risk: **Medium** (fail-closed guard; audit append when live *requested* — still denied by defaults)

### Tests

```powershell
python -m pytest project_guardian/tests/test_live_execution_guard.py project_guardian/tests/test_live_execution_guard_runtime_integration.py project_guardian/tests/test_operator_confirmation_store.py project_guardian/tests/test_operator_confirmation_guard_integration.py project_guardian/tests/test_operator_confirmation_visibility.py project_guardian/tests/test_live_execution_governance_docs.py -q
```

---

## 3D — Brain pipeline integration (file-by-file)

**Suggested message:** `feat(safe-stack): add dry-run brain pipeline and trace visibility`

**Do not** `git add project_guardian/brain/`. Stage each file explicitly:

```text
project_guardian/brain/__init__.py
project_guardian/brain/config.py
project_guardian/brain/contracts.py
project_guardian/brain/pipeline.py
project_guardian/brain/runtime.py
project_guardian/brain/trace_visibility.py
project_guardian/brain/tda_trace_fields.py
project_guardian/brain/think_decide_act_adapter.py
project_guardian/brain/context_builder_module.py
project_guardian/brain/planner_module.py
project_guardian/brain/memory_module.py
project_guardian/brain/risk_module.py
project_guardian/brain/execution_module.py
project_guardian/brain/learning_module.py
project_guardian/brain/llm_router_module.py
project_guardian/brain/tool_router_module.py
project_guardian/brain/memory_ranking.py
project_guardian/brain/self_improvement_module.py
project_guardian/brain/dashboard_module.py
```

**Defer / review before staging:** any file that predates safe-stack and duplicates legacy brain — all listed paths are untracked new in current worktree.

**Not in 3D:** `live_execution_runtime.py` (3C).

### Risk: **Medium** (`runtime.py` guard metadata only; pipeline off by config)

### Tests

```powershell
python -m pytest project_guardian/tests/test_brain_config_runtime.py project_guardian/tests/test_brain_trace_visibility.py project_guardian/tests/test_brain_tda_integration.py project_guardian/tests/test_tda_trace_fields.py -q
python scripts/run_safe_stack_smoke_tests.py
```

---

## 3E — API + control panel (patch only)

**Suggested message:** `feat(safe-stack): wire runtime API and control panel safe-stack routes`

### Files

| Path | Method |
|------|--------|
| `elysia/api/server.py` | `git add -p` — safe-stack routes, conversation import, governance GET only |
| `project_guardian/ui_control_panel.py` | `git add -p` — template panels, mirrored routes, operator chat |

### Risk: **High** (large tracked diffs; pre-existing autonomy route may remain — do not stage unrelated hunks)

### Tests

```powershell
python -m pytest project_guardian/tests/test_api_host_route_parity.py project_guardian/tests/test_control_panel_ui_clarity.py project_guardian/tests/test_control_panel_brain_visibility.py project_guardian/tests/test_control_panel_operator_chat_helper_integration.py project_guardian/tests/test_runtime_operator_chat_helper_integration.py -q
python scripts/run_safe_stack_smoke_tests.py
```

---

## Do not stage (Group 3 scope)

```text
project_guardian/orchestration/think_decide_act.py   # optional; separate if not required for 3A–3E smoke
project_guardian/core.py
config/autonomy.json
elysia.py
REPORTS/review_queue.jsonl
data/runtime/
deployments/
```

---

## Suggested commit order

1. **3A** — foundations (this task)  
2. **3B** — visibility modules (unblocks `responses` import on clean checkout)  
3. **3C** — governance  
4. **3D** — brain files (explicit list)  
5. **3E** — server + UI (`-p`)

After Group 3: Group 4 (remaining smoke tests), Group 5 (adjacent tests), Group 6 (docs).

---

## Patch-staging required

| File | Subcommit |
|------|-----------|
| `elysia/api/server.py` | 3E only |
| `project_guardian/ui_control_panel.py` | 3E only |

All other Group 3 paths: explicit `git add <file>` or `git add <dir>` per subcommit list.
