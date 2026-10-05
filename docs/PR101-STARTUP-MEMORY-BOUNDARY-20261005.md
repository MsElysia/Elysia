# PR #101 startup memory boundary — 2026-10-05

Isolated child of draft PR #101. Not merged. Not pushed.

## Identity

- Branch: `codex/pr101-startup-memory-boundary-20261005`
- Parent: `71ac66c3c9d4a4f4f68922941563db85618a2922`
- Source behavior inspected, not imported: `0760798bc3ecb036c92fca456670c67e901c7ed7`

## Before, on exact PR #101

Disposable 4,200-record store, SHA-256 `7add19433d097f0aab5acf4d0de9d587b90d02bce4206f850b72bdb2b2f7d0b6`.

- `GuardianCore._check_and_cleanup_memory()` consolidated `4200 -> 0`. After SHA-256 `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.
- `Heartbeat._beat()` with the count above the high-water mark consolidated `4200 -> 0`. Same after hash.
- The production shutdown callback called `memory.remember` with category `adversarial_finding` for `task_completed_unverified`.

## After

Real `elysia.py` probe, autonomy disabled, two startup/heartbeat/shutdown cycles each:

| Scenario | Count | SHA-256, both cycles | Findings stayed in registry/logs |
| --- | --- | --- | --- |
| clean | 4200 -> 4200 | `7add19433d097f0aab5acf4d0de9d587b90d02bce4206f850b72bdb2b2f7d0b6` | none expected |
| duplicate errors | 4200 -> 4200 | `88fc71597d254aabf9d7bdb1f75f9c35bc849d5661cc24f67cbf4a6e6c84e200` | `repeated_failure` |
| degraded vector | 4200 -> 4200 | `88fc71597d254aabf9d7bdb1f75f9c35bc849d5661cc24f67cbf4a6e6c84e200` | `repeated_failure`, `degraded_vector_state`, `startup_configuration_weakness`; shutdown logged `task_completed_unverified` |

No consolidation log. Autonomy file bytes unchanged. Exit 0 and `Goodbye!` on every cycle.

## Tests

- Focused startup, Issue #91, Guardian activation, and Brain bridge tests: 58 passed.
- Safe Stack: 587 passed in 20.78s.
- `git diff --check`: clean.

## Vega handoff

Review this child only. Parent acceptance does not transfer. Confirm disabled-autonomy startup, heartbeat, shutdown, and reopen leave a 4,200-record store byte-identical, while explicit `remember`, explicit consolidation, and `run_adversarial_cycle` still write. Do not treat this as merge approval.
