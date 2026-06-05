# API approval execution-behavior repair

## Starting failed commit

**HEAD:** `c0861e5 fix(tests): repair api approval contract expectations`

## Codex failure

**Verdict:** FAIL — `Execution behavior added? Yes`

**Reason:** `elysia/api/server.py` added a branch on `POST /api/proposals/<id>/implement` that ran `self._implementer.run_for_proposal()` when an implementer was injected. That violated safe-autonomy restrictions (no execution wiring in this phase).

## Root cause

Commit `c0861e5` intended testability for `/implement` but re-enabled execution (injected implementer first, then default `ImplementerAgent`). Tests asserted successful dry-run and file mutation via the API.

## Repair performed

| Path | Behavior after repair |
|------|------------------------|
| `POST .../approve` | Unchanged — records approval only |
| `POST .../status` | Unchanged — status transition only |
| `POST .../implement` | **403 blocked** — `implementation_execution_disabled`; no `ImplementerAgent`, no injected implementer |
| `GET .../implementation` | Unchanged — read-only status metadata |

Removed the injected-implementer branch and the `ImplementerAgent` execution path from `/implement`.

## Files changed

- `elysia/api/server.py` — passive `/implement` stub (fail-closed 403)
- `tests/test_elysia_api_approval_implementation.py` — assert blocked responses; no file mutation via API
- `docs/API_APPROVAL_EXECUTION_BEHAVIOR_REPAIR.md` — this document

## Proof

- **`/approve`:** Tests assert `implementer.calls == []` and no `implementation` in JSON.
- **`/status`:** Tests assert transition only; `implementer.calls == []`.
- **`/implement`:** Returns `403` with `executed: false`, `blocked: true`; injected `FakeImplementer` never called; target files unchanged.

## Safety statement

- Autonomy **not** enabled (`config/autonomy.json` → `"enabled": false`, unchanged)
- No live execution, tools, capabilities, WebScout, or browser activity
- **No new** API routes
- **No execution code** added (execution paths removed/neutralized)
- Approval remains passive; implementation API is explicitly disabled

## Remaining blockers

- Gateway smoke drift
- Artifact/run_once policy
- UI residual
- Router/task telemetry
- Environment cleanup
- Broad `-k` approval selector may still fail on e2e/gateway tests outside `test_elysia_api_approval_implementation.py`

## Related docs

- [`docs/API_APPROVAL_TEST_REPAIR.md`](API_APPROVAL_TEST_REPAIR.md) — superseded for `/implement` execution expectations
- [`docs/PHASE2_LIVE_ACTION_ALLOWLIST_DESIGN.md`](PHASE2_LIVE_ACTION_ALLOWLIST_DESIGN.md)
