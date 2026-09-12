# Live Readiness After Limited Live Smoke Command

**Milestone:** Readiness evidence update — **limited live mode remains BLOCKED**  
**Date:** 2026-05-30  
**Status:** Limited-live smoke command verified; readiness evidence updated

**Starting checkpoint:** `30a4915 fix(autonomy): constrain limited live smoke workspace`

**Related docs:** [`LIMITED_LIVE_SMOKE_COMMAND.md`](LIMITED_LIVE_SMOKE_COMMAND.md), [`LIMITED_LIVE_RELEASE_CANDIDATE_BASELINE.md`](LIMITED_LIVE_RELEASE_CANDIDATE_BASELINE.md), [`LIVE_READINESS_AFTER_LIMITED_LIVE_PROFILE.md`](LIVE_READINESS_AFTER_LIMITED_LIVE_PROFILE.md)

---

## Evidence updated

| Check | Default | Meaning |
|-------|---------|---------|
| `LIMITED_LIVE_SMOKE_COMMAND_PRESENT` | `true` | Operator command `scripts/run_limited_live_smoke.py` exists |
| `LIMITED_LIVE_SMOKE_COMMAND_VERIFIED` | `true` | Command verified by `tests/test_limited_live_smoke_script.py` |
| `LIMITED_LIVE_SMOKE_WORKSPACE_TEMP_ONLY` | `true` | Default and custom workspace constrained to system temp only |
| `LIMITED_LIVE_SMOKE_UNSAFE_WORKSPACES_REJECTED` | `true` | Repo/home/cwd/external/relative/unsafe paths rejected before execution |
| `LIMITED_LIVE_SMOKE_ROLLBACK_VERIFIED` | `true` | Command verifies rollback in isolated temp workspace |
| `PRODUCTION_LIVE_EXECUTION_DISABLED_BY_DEFAULT` | `false` | Blocker — triple execution gates off by default |
| `AUTONOMY_CONFIG_DISABLED` | `false` | Blocker — `config/autonomy.json` remains disabled |

**Prior milestones still passing:** profile declared, runbook present, route wiring, executor, harmless smoke, rollback, and tmp-workspace verification evidence remain `true`.

**Safety verification (passing, not readiness grant):** `AUTONOMY_CONFIG_DEFAULT_DISABLED=true` confirms config remains disabled by design.

---

## Limited-live smoke command verified

Operator command: `scripts/run_limited_live_smoke.py`

- Requires `--confirm-limited-live-smoke` and `--profile operator_approved_harmless_smoke_v1`
- Default mode uses `tempfile.mkdtemp()` only
- Custom `--workspace` allowed only inside system temp directory
- Unsafe workspace parents rejected before packet registration or execution
- Writes exact harmless smoke file/content only in isolated temp workspace
- Performs and verifies rollback
- Emits JSON summary with `workspace_root`, `workspace_rejected`, and `safe`

Workspace safety repair (`30a4915`) verified: unsafe paths write nothing.

---

## Why readiness remains blocked

`evaluate_live_mode_readiness()` returns:

- `status=BLOCKED`
- `ready_for_limited_live_mode=false`
- `safety_verdict=NOT_READY_FOR_LIVE_MODE`

Verified smoke command is necessary operator tooling but does not enable production live execution or autonomy config.

---

## Remaining blockers

| Blocker key | Reason |
|-------------|--------|
| `PRODUCTION_LIVE_EXECUTION_DISABLED_BY_DEFAULT` | Triple execution gates remain off by default in production/runtime |
| `AUTONOMY_CONFIG_DISABLED` | `config/autonomy.json` `enabled=false` |

---

## Safety statement

This milestone:

- Does **not** enable autonomy
- Does **not** change script behavior
- Does **not** change approval route behavior
- Does **not** change executor behavior
- Does **not** modify `config/autonomy.json` (`enabled=false` unchanged)
- Does **not** mark broad autonomy ready

Readiness evidence only — no runtime wiring or execution changes.
