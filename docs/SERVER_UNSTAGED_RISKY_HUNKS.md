# Unstaged risky hunks — `elysia/api/server.py`

**Date:** 2026-05-24  
**Purpose:** Isolate proposal-implementation and WebScout expansion work from the safe-stack milestone.  
**Related:** `da8d0ae` (3E), `docs/SAFE_STACK_POST_3E_REVIEW.md`, `docs/SAFE_STACK_STAGING_MANIFEST.md`

---

## 1. Exact file with remaining diff

| Item | Value |
|------|--------|
| **File** | `elysia/api/server.py` |
| **Status** | Modified in working tree; **not** in index |
| **Committed baseline** | `da8d0ae` — safe-stack API/control panel wiring only |
| **Unstaged stat** | 108 insertions, 20 deletions (128 lines touched) |
| **Index** | Empty — nothing staged |

```powershell
git diff --name-only -- elysia/api/server.py
# elysia/api/server.py

git diff --stat -- elysia/api/server.py
# 1 file changed, 108 insertions(+), 20 deletions(-)
```

---

## 2. Categories of unstaged hunks

### A. Auto-implement constructor wiring

- `auto_implement_on_approval: bool = False` on `RuntimeAPIServer.__init__`
- `self._auto_implement_on_approval` instance field

**Risk:** Global opt-in path for chained implementation on approval; must not ship with safe-stack defaults.

### B. Proposal implementation helpers

- `_approval_should_implement(data)` — honors request keys `auto_implement`, `implement`, `run_implementation`, or server flag
- `_run_implementation(proposal_id, *, dry_run=False)` — invokes `ImplementerAgent.run_for_proposal`, emits `implementation_triggered` on event bus

**Risk:** Executes code paths tied to Elysia proposal **implementation**, not safe-stack review/export.

### C. Approval / status transition hooks

- `POST /api/proposals/<id>/approve` — on success, may attach `response["implementation"]` from `_run_implementation`
- `POST /api/proposals/<id>/status` — on `approved` transition, same chained implementation

**Risk:** Approval becomes an implicit implement trigger without separate governance review.

### D. Implement route refactor + preview endpoint

- `POST /api/proposals/<id>/implement` — refactored to call `_run_implementation` instead of inline `ImplementerAgent` block
- **New** `GET|POST /api/proposals/<id>/implementation/preview` — dry-run preview via `_run_implementation(..., dry_run=True)`

**Risk:** Expands implementation surface; preview route is not in `da8d0ae` and is not covered by safe-stack smoke as a milestone deliverable.

### E. WebScout `research_options` expansion

- `POST /api/webscout/research` — builds `research_options` dict: `tags`, `check_duplicates`, `implementation_plan`, `max_sources`, `auto_generate_implementation_plan`
- Calls `self._webscout.research_topic(topic, domain, **research_options)` instead of `(topic, domain)`

**Risk:** Research API behavior change; may pull external research/LLM paths outside safe-stack scope.

---

## 3. Why these hunks are outside the safe-stack milestone

| Reason | Detail |
|--------|--------|
| **Different product goal** | Safe-stack = read-only visibility, conversation memory, config-gated brain trace, governance **GET**, self-improvement review/export. These hunks add **execute/implement** and richer research calls. |
| **3E already landed safe server wiring** | `da8d0ae` committed operator chat, ConversationStore routes, brain trace, memory ranking, prompt contracts, operator confirmations — without these hunks. |
| **Conflicts with fail-closed posture** | Safe-stack live-execution governance (`c528124`) and brain dry-run (`e8e2783`) assume implementation is not auto-chained from HTTP approval. |
| **Not smoke-milestone scope** | `scripts/run_safe_stack_smoke_tests.py` does not validate proposal implement/preview or WebScout option matrices. |
| **Mixed staging hazard** | Staging `elysia/api/server.py` wholesale would re-introduce risky hunks after intentional 3E exclusion. |

---

## 4. Why they must not be staged with tests/docs in this milestone

- **Do not** `git add elysia/api/server.py` while these hunks remain in the working tree (use patch staging or a dedicated branch after review).
- **Do not** bundle with Group 3 smoke test commits or doc-only commits — reviewers will assume milestone = safe-stack only.
- **Do not** treat passing smoke (386) as approval of unstaged hunks — smoke passes on mixed worktree today; **committed** milestone is `da8d0ae` server content only.
- Implementation/WebScout changes need their own tests (implementer integration, webscout contract, approval chaining, preview route) and governance review — not the safe-stack slice.

---

## 5. Recommended future track: proposal implementation governance

Stage these hunks only under a **separate** track, for example:

**Track name:** `proposal implementation governance` (or `elysia-api-proposal-implement-governance`)

**Suggested commit split (example):**

1. Refactor `_run_implementation` + implement route (dry-run default, no auto chain).
2. Optional preview endpoint + tests.
3. Opt-in approval chaining behind explicit config + operator confirmation.
4. WebScout `research_options` with documented API contract + tests.

**Out of scope for that track until reviewed:** safe-stack panels, autonomy loop, live brain execution enablement.

---

## 6. Safety gates before staging (checklist)

Before any future commit that includes these hunks:

| Gate | Requirement |
|------|-------------|
| **Separate config flag** | e.g. `config/proposal_implementation.json` or env — `enabled: false` by default |
| **Dry-run default** | Implement/preview paths default `dry_run=True`; live apply requires explicit flag |
| **Explicit operator approval** | No implement on approve unless request + config + optional operator confirmation record |
| **Live-execution guard integration** | `apply_live_execution_guard_to_context` (or equivalent) before any non-dry implement |
| **No auto-implement by default** | `auto_implement_on_approval=False`; reject silent True in production config |
| **Rollback / test plan** | Dedicated pytest suite; document revert; no dependency on safe-stack smoke as sole gate |
| **Audit** | `implementation_triggered` events reviewed; no new autonomy wiring |

---

## 7. What safe-stack 3E already committed (do not re-stage)

In `da8d0ae`, `elysia/api/server.py` already includes:

- `safe_stack.responses` + `operator_chat` for `/api/chat` and conversation APIs
- Read-only: brain trace, self-improvement list/detail/status/export, prompt contracts status, operator confirmations, memory ranking summary
- Legacy inline `ImplementerAgent` on `POST .../implement` (pre-existing pattern) — **not** the unstaged refactor/preview/auto-chain

**Re-staging the file without `-p` would risk pulling §2 hunks into the milestone.**

---

## 8. Verify hunks remain unstaged

Run before any safe-stack Group 4+ commit:

```powershell
git diff --cached --name-only
# expect: (empty)

git diff --name-only -- elysia/api/server.py
# expect: elysia/api/server.py  (until intentionally committed on separate track)

git diff --stat -- elysia/api/server.py
# expect: ~108 insertions, ~20 deletions while isolated
```

If `git diff --name-only -- elysia/api/server.py` is empty, either hunks were committed elsewhere or the worktree was reset — check `git log -1 -- elysia/api/server.py`.

---

## 9. Optional worktree hygiene (not performed by default)

To align disk with `da8d0ae` **without** losing hunks:

```powershell
# Save patch for separate track (documentation only — run manually if desired)
git diff elysia/api/server.py > proposals/server_implementation_webscout.patch

# Restore committed server (DESTRUCTIVE to unstaged hunks — only after saving patch)
# git checkout da8d0ae -- elysia/api/server.py
```

**This cleanup agent did not revert or modify `elysia/api/server.py`.**

---

## 10. Safety confirmation (milestone)

| Check | Status |
|-------|--------|
| Live execution enabled by unstaged hunks | **No** — not part of safe-stack config; implement path is separate from brain live-exec guard |
| Autonomy wired | **No** — no autonomy routes in these hunks |
| Safe-stack milestone commit | **`da8d0ae` unchanged** |
| Documentation-only change in this task | **Yes** |

---

## 11. Reference: unstaged diff summary (line regions)

Approximate regions in working tree vs `da8d0ae` (line numbers may shift):

| Region | Symbols / routes |
|--------|------------------|
| ~46–60 | `auto_implement_on_approval` |
| ~79–133 | `_approval_should_implement`, `_run_implementation` |
| ~639–686 | approve + transition implementation hooks |
| ~697–734 | WebScout `research_options` |
| ~743–756 | implement refactor + `implementation/preview` |

Full diff: `git diff elysia/api/server.py`
