# Dirty `elysia/api/server.py` Retriage

## Current checkpoint

**HEAD:** `8ec3bc7 fix(tests): repair core smoke path-safety expectations`

**Date:** 2026-06-02

**Milestone:** Documentation/triage only — inspect quarantine; do not stage, commit, restore, or discard `elysia/api/server.py`.

---

## File under quarantine

| Item | Value |
|------|--------|
| Path | `elysia/api/server.py` |
| `git status` | `M` (modified, unstaged) |
| Staged | **No** |
| Committed in `8ec3bc7` | **No** |

---

## Inspection commands and results

```powershell
git diff -- elysia/api/server.py
# → no hunks (empty diff; CRLF normalization warning only)

git diff --stat -- elysia/api/server.py
# → no line changes

git hash-object elysia/api/server.py
# → 4cd01db9622d3d84b8080b1e0c13177db074be21

git rev-parse HEAD:elysia/api/server.py
# → 4cd01db9622d3d84b8080b1e0c13177db074be21  (identical blob)

git ls-files -v -- elysia/api/server.py
# → H elysia/api/server.py  (assume-unchanged bit set)

git diff-index HEAD -- elysia/api/server.py
# → :100644 100644 4cd01db... 0000000000000000000000000000000000000000 M
#   (index marks modified; work-tree blob hash matches HEAD)
```

### Summary of the diff

**No textual diff against HEAD.** Work-tree file content is byte-identical to committed `HEAD`. The `M` flag is a **phantom / index-metadata** dirty state (stale index entry with zero work-tree hash in `diff-index`, plus `assume-unchanged`), not a reappearance of the previously quarantined ~128-line risky hunk set.

### Historical context (not present now)

Prior operator-approved cleanup (`docs/DIRTY_HUNKS_PERMANENTLY_REJECTED.md`) permanently discarded unstaged hunks that included:

- `auto_implement_on_approval` / approval→implement chaining
- Proposal `_run_implementation` expansion
- WebScout `research_options` API expansion

Those hunks are **not** in the current work-tree diff. Committed HEAD is the safety baseline.

---

## Classification

| Primary | **ACCIDENTAL_OR_UNKNOWN** (phantom dirty flag) |
| Secondary notes | Not **RISKY_API_SURFACE**, **RISKY_PROPOSAL_IMPLEMENTATION**, **RISKY_WEBSCOUT_OR_BROWSER**, or **RISKY_EXECUTION_PATH** — no new code vs HEAD |

Codex concern (risky server hunks) is **not substantiated** by current `git diff` output; status is misleading until index is refreshed.

---

## Recommendation

1. **Keep unstaged** — do not stage or commit `elysia/api/server.py` in autonomy-prep milestones.
2. **Do not rely on it** — no proof value; content equals HEAD.
3. **Do not re-apply** discarded S1–S7 hunks from prior triage docs.
4. **After explicit human approval only**, clear phantom status without adopting new code:
   - `git update-index --no-assume-unchanged elysia/api/server.py`
   - `git update-index --refresh elysia/api/server.py`
   - or `git restore elysia/api/server.py` (no-op on content; resets index stat)
5. If a **future** real diff appears, re-run triage using `docs/DIRTY_RISKY_HUNKS_TRIAGE.md` / `docs/SERVER_UNSTAGED_RISKY_HUNKS.md` classifications before any merge.

Safe-stack API work must continue via **rewrite-from-scratch** using `live_action_*` modules, not dirty server hunks.

---

## Safety statement

| Check | Status |
|-------|--------|
| Autonomy enabled | **No** (`config/autonomy.json` → `"enabled": false`, unchanged) |
| Live execution run | **No** |
| API/server routes added in committed code | **No** (this milestone) |
| Execution code added in committed code | **No** (this milestone) |
| `elysia/api/server.py` staged/committed | **No** |
| Dirty file used as proof | **No** |

---

## Verification at triage time

| Command | Result |
|---------|--------|
| `python scripts/run_elysia_dry_run_report.py --mode real-planning` | SAFE, exit 0 |
| Passive Phase 2 targeted pytest (6 modules) | 92 passed |
| `python scripts/run_safe_stack_smoke_tests.py` | 454 passed |

---

## Related docs

- [`DIRTY_HUNKS_PERMANENTLY_REJECTED.md`](DIRTY_HUNKS_PERMANENTLY_REJECTED.md)
- [`DIRTY_RISKY_HUNKS_TRIAGE.md`](DIRTY_RISKY_HUNKS_TRIAGE.md)
- [`SERVER_UNSTAGED_RISKY_HUNKS.md`](SERVER_UNSTAGED_RISKY_HUNKS.md)
