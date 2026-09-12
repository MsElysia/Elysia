# Phase 1c.2 full pytest collection repair baseline

## Scope

This document records the Phase 1c.2 collection-repair milestone and the current test baseline. It does **not** authorize real autonomy or live execution.

- Milestone: Phase 1c.2 full pytest collection repair
- Repair commit: `47f559e` — `test(safe-stack): repair full pytest collection`

## Files changed by repair

- `pytest.ini`
- `tests/test_invariants.py`

## What was fixed

1. **`tests/test_invariants.py` syntax issue**
   - Misplaced `except` blocks on `TestInvariant2_TrustEngine` (handlers were attached to the wrong method).
   - Duplicate `else:` branch in `TestInvariant3_MutationFlow` (`test_mutation_engine_rejects_governance_files`).

2. **Unregistered `meta` marker under strict markers**
   - `tests/test_artifact_policy_coverage.py` uses `@pytest.mark.meta`.
   - Committed `pytest.ini` had `--strict-markers` but no `meta` marker registration.
   - Fix: register `meta` in `pytest.ini`.

## Collection results

### Targeted collection (known blockers)

- `tests/test_invariants.py` + `tests/test_artifact_policy_coverage.py`
- Result: **15 tests collected**

### Full collection

| Environment | Result |
|-------------|--------|
| Cursor | **441 tests collected in 7.76s** |
| Codex | **400 tests collected in 13.78s** |

**Collection count mismatch:** The difference (441 vs 400) is recorded as environment/path/discovery-dependent until explained. Investigate if it affects future gates (e.g. different `testpaths`, plugins, or working-tree discovery).

## Safe-stack smoke

- Result: **408 passed, 3 warnings**
- Autonomy and live execution are not exercised or enabled by this gate.

## Full runtime pytest baseline (out of scope for 1c.2)

Full root pytest was run once after collection repair (Cursor):

- **98 failed, 274 passed, 9 skipped, 60 errors in 116.37s**

Runtime failures and errors remain **out of scope** for Phase 1c.2. They include mutation/subprocess/WebReader/WebScout-adjacent suites and other pre-existing runtime issues. Codex did not rerun full runtime pytest (optional; same scope caveat).

## Config and autonomy status

- `config/autonomy.json`: **enabled=false** (unchanged)
- Autonomy: **dry-run only**
- Real autonomy mode: **not run**
- Live execution: **not run**

## Dirty worktree note

The original dirty worktree was preserved:

- `project_guardian/core.py` — dirty, unstaged
- `elysia/api/server.py` — dirty, unstaged

No clean/reset/stash/discard was performed on those files.

## Final verdict

- **PASS** for collection repair (full pytest collection succeeds; known blockers fixed).
- **NOT** a full runtime test pass (root pytest runtime baseline remains failing/erroring).
