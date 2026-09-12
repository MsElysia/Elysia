# Safe-Stack Post–3E Verification Review

**Date:** 2026-05-24  
**Verifier role:** Committer-side post-3E check (read-only; no staging/commits)  
**Latest commit:** `da8d0ae` — `feat(safe-stack): wire runtime and control panel safe-stack surfaces`

---

## 1. Latest commit

| Field | Value |
|-------|--------|
| Hash | `da8d0ae` |
| Message | `feat(safe-stack): wire runtime and control panel safe-stack surfaces` |
| Files | `elysia/api/server.py` (+472 / −20 net in stat), `project_guardian/ui_control_panel.py` (+3849 / −97 net) |
| Total | 2 files changed, 4204 insertions, 117 deletions |

---

## 2. Index status

```text
git diff --cached --name-only
→ (empty)
```

**Index is clean.** Nothing staged.

---

## 3. Remaining unstaged high-risk diffs

| File | Unstaged? | Stat |
|------|-----------|------|
| `elysia/api/server.py` | **Yes** | 108 insertions, 20 deletions |
| `project_guardian/ui_control_panel.py` | **No** | Matches `da8d0ae` |

---

## 4. Committed 3E content (safety)

### `elysia/api/server.py` (in `da8d0ae`)

**Included (safe-stack):**

- `project_guardian.safe_stack.responses` and `operator_chat` integration
- `ConversationStore` / `get_default_conversation_store` for `/api/chat`, history, conversations
- Config-gated `_maybe_run_brain_operator_chat_trace` (dry-run metadata only)
- Read-only / review routes via shared builders:
  - `GET /api/brain/trace/latest`
  - `GET /api/self-improvement/proposals`, `GET …/<id>`, `POST …/<id>/status`, `GET …/export_prompt`
  - `GET /api/prompt-contracts/status`
  - `GET /api/governance/operator-confirmations`, `GET …/<id>`
  - `GET /api/memory/ranking/summary`

**Excluded from commit (left unstaged on disk — see §5):**

- `_approval_should_implement`, `_run_implementation`, `auto_implement_on_approval`
- Approve/transition hooks that chain implementation on approval
- WebScout `research_options` expansion
- New `GET|POST /api/proposals/<id>/implementation/preview`
- Refactored implement route calling `_run_implementation`

**Pre-existing (not introduced by 3E):**

- Legacy Elysia proposal routes (`/api/proposals/.../implement`, implementation status) remain with **inline** `ImplementerAgent` in the committed tree (same pattern as pre-3E parent). Not newly enabled by this commit.

**Live execution / autonomy (committed server):**

- No `live_execution_enabled` wiring; brain trace is config-gated.
- No autonomy routes on runtime API server.
- Self-improvement: list / detail / status / export only (no code execution path in safe-stack routes).
- Operator confirmations: GET list + GET detail only.

### `project_guardian/ui_control_panel.py` (in `da8d0ae`)

**Staging method:** Full file (patch `git add -p` not practical; 54 hunks, large mixed template blocks).

**Safe-stack surfaces present:**

- ConversationStore-backed chat/history; `run_operator_chat_turn` / `safe_stack.responses` mirrored routes
- Panels: Brain Trace, Self-Improvement (review/export), Memory Ranking, Prompt Contracts
- UI copy: live execution off for safe-stack panels; self-improvement review/export only
- Operator confirmation read-only fetches (via shared response builders)

**3E diff did not add new autonomy execute lines:**

- `git diff da8d0ae^..da8d0ae` on UI: **0** new `+` lines matching `execute-cycle` or `run_autonomous`.

**Caveat (documented, not a 3E regression):**

- File still contains **legacy** `/api/autonomy`, `/api/autonomy/execute-cycle`, and `run_autonomous_cycle` (pre-existing dashboard). These are **outside** safe-stack milestone intent and must not be treated as newly approved safe-stack behavior. No new execute controls were added in the 3E commit diff.

**Other mixed dashboard/workbench content** may be present in the full-file commit (income, wallet, workbench helpers, etc.). Treat as **follow-up review** if a slimmer UI commit is desired later; not required for 3E milestone gate if smoke passes.

---

## 5. Unstaged `elysia/api/server.py` hunks — classification

| Hunk | Classification | Safe-stack milestone |
|------|----------------|----------------------|
| `auto_implement_on_approval` constructor + instance field | Unrelated proposal implementation | **Exclude** |
| `_approval_should_implement`, `_run_implementation` helpers | Unrelated proposal implementation | **Exclude** — risky / do-not-stage without explicit review |
| Approve + transition_status hooks calling `_run_implementation` | Unrelated proposal implementation | **Exclude** — risky |
| WebScout `research_options` (`tags`, `implementation_plan`, `auto_generate_implementation_plan`, etc.) | WebScout/research expansion | **Exclude** |
| Implement route refactor + new `/implementation/preview` | Unrelated proposal implementation | **Exclude** — risky / do-not-stage |

**Recommendation:** Keep all of the above **unstaged** and **out of the safe-stack milestone** until a separate, explicitly reviewed commit (if ever). Do not `git add` them as part of Group 3.

---

## 6. Test results (2026-05-24)

**Note:** Pytest/smoke ran against the **working tree**: committed `da8d0ae` UI + server **plus** unstaged server hunks in §5. Milestone gate still passes; committed-only checkout would omit §5 behavior.

### Targeted API/UI tests

```powershell
python -m pytest project_guardian/tests/test_runtime_operator_chat_helper_integration.py `
  project_guardian/tests/test_control_panel_operator_chat_helper_integration.py `
  project_guardian/tests/test_runtime_api_conversations.py `
  project_guardian/tests/test_control_panel_chat_memory.py `
  project_guardian/tests/test_control_panel_brain_visibility.py `
  project_guardian/tests/test_memory_ranking_visibility.py `
  project_guardian/tests/test_prompt_contract_controls.py `
  project_guardian/tests/test_self_improvement_prompt_export.py `
  project_guardian/tests/test_operator_confirmation_visibility.py `
  project_guardian/tests/test_api_host_route_parity.py -q
```

**Result:** **112 passed**, 3 warnings (~2.75s).

### Safe-stack smoke

```powershell
python scripts/run_safe_stack_smoke_tests.py
```

**Result:** **386 passed**, 3 warnings (~5.77s).

---

## 7. Red flags

| Flag | Severity | Status |
|------|----------|--------|
| Unstaged server implementation/WebScout hunks on disk | Medium | **Documented; excluded from milestone** |
| UI committed as full file (mixed dashboard) | Medium | **Known; 3E diff did not add autonomy execute lines** |
| Legacy autonomy UI/routes still in committed UI | Low (pre-existing) | **Not newly wired by 3E** |
| Pre-existing `/api/proposals/.../implement` on committed server | Low (pre-existing) | **Not refactored/enhanced in `da8d0ae`** |
| Index not clean | — | **None — index clean** |

No blocker found for safe-stack milestone acceptance of **3E as committed**.

---

## 8. Safety confirmation

| Check | Result |
|-------|--------|
| Live execution enabled | **No** — config/guard unchanged; panels labeled off; read-only governance GETs |
| Autonomy newly wired in 3E | **No** — no new autonomy routes in 3E server/UI diffs |
| Safe-stack self-improvement API | **Review/status/export only** (committed server) |
| Operator confirmations | **Read-only GET** (committed server) |
| Brain / memory / prompt routes | **Read-only / status** via `safe_stack.responses` |
| New apply/run/execute in safe-stack panels | **No** new controls in 3E diff |

---

## 9. Safe-stack commit chain (reference)

```text
da8d0ae feat(safe-stack): wire runtime and control panel safe-stack surfaces
e8e2783 feat(safe-stack): add brain runtime dry-run orchestration
c528124 feat(safe-stack): add fail-closed live execution governance
f11d9e6 feat(safe-stack): add advisory ranking, prompts, and proposal helpers
3f0fd77 feat(safe-stack): add shared conversation and response foundations
aca1c1d config(safe-stack): add dry-run brain and memory defaults
1ada6e8 chore(safe-stack): add smoke gate and ignore runtime artifacts
```

---

## 10. Next steps (out of scope for this review)

- Group 4: remaining smoke test files (if not already committed).
- Optional follow-up: patch-commit or revert unstaged server hunks to match `da8d0ae` exactly on disk.
- Optional follow-up: slim `ui_control_panel.py` to safe-stack-only hunks in a future commit.
