# Live Readiness After Limited Live Activation Wrapper

**Milestone:** Readiness evidence update — **limited live mode remains BLOCKED**  
**Date:** 2026-05-30  
**Status:** Limited-live activation wrapper verified; readiness evidence updated

**Starting checkpoint:** `7293ff8 feat(autonomy): add limited live activation wrapper`

**Related docs:** [`LIMITED_LIVE_ACTIVATION_WRAPPER.md`](LIMITED_LIVE_ACTIVATION_WRAPPER.md), [`LIMITED_LIVE_ACTIVATION_PROFILE_PLAN.md`](LIMITED_LIVE_ACTIVATION_PROFILE_PLAN.md), [`LIVE_READINESS_AFTER_LIMITED_LIVE_SMOKE_COMMAND.md`](LIVE_READINESS_AFTER_LIMITED_LIVE_SMOKE_COMMAND.md)

---

## Evidence updated

| Check | Default | Meaning |
|-------|---------|---------|
| `LIMITED_LIVE_ACTIVATION_WRAPPER_PRESENT` | `true` | Operator wrapper `scripts/run_limited_live_activation.py` exists |
| `LIMITED_LIVE_ACTIVATION_WRAPPER_VERIFIED` | `true` | Wrapper verified by `tests/test_limited_live_activation_wrapper.py` |
| `LIMITED_LIVE_ACTIVATION_OPERATOR_CONFIRMATION_REQUIRED` | `true` | Wrapper requires `--confirm-limited-live-activation` |
| `LIMITED_LIVE_ACTIVATION_PROFILE_REQUIRED` | `true` | Wrapper requires `limited_live_harmless_smoke_activation_v1` |
| `LIMITED_LIVE_ACTIVATION_RC_TAG_VALIDATION_PRESENT` | `true` | Wrapper validates RC tag `limited_live_rc_1` → `236f0b5` |
| `LIMITED_LIVE_ACTIVATION_CONFIG_DISABLED_VALIDATION_PRESENT` | `true` | Wrapper validates `config/autonomy.json` `enabled=false` |
| `LIMITED_LIVE_ACTIVATION_ROLLBACK_VERIFIED` | `true` | Wrapper verifies rollback via smoke command delegation |
| `PRODUCTION_LIVE_EXECUTION_DISABLED_BY_DEFAULT` | `false` | Blocker — triple execution gates off by default |
| `AUTONOMY_CONFIG_DISABLED` | `false` | Blocker — `config/autonomy.json` remains disabled |

**Prior milestones still passing:** profile declared, runbook present, smoke command, route wiring, executor, harmless smoke, rollback, and tmp-workspace verification evidence remain `true`.

**Safety verification (passing, not readiness grant):** `AUTONOMY_CONFIG_DEFAULT_DISABLED=true` confirms config remains disabled by design.

---

## Limited-live activation wrapper verified

Operator wrapper: `scripts/run_limited_live_activation.py`

- Requires `--confirm-limited-live-activation`
- Requires `--activation-profile limited_live_harmless_smoke_activation_v1`
- Requires `--profile operator_approved_harmless_smoke_v1`
- Validates RC tag `limited_live_rc_1` → `236f0b5`
- Validates branch `codex/limited-live-activation-wrapper` in operator mode
- Validates `config/autonomy.json` `enabled=false`
- Delegates to verified smoke command logic only
- Uses temp-only workspace rules from smoke command
- Executes exact harmless smoke file/content only
- Performs and verifies rollback
- Emits JSON summary with activation evidence fields

---

## Why readiness remains blocked

`evaluate_live_mode_readiness()` returns:

- `status=BLOCKED`
- `ready_for_limited_live_mode=false`
- `safety_verdict=NOT_READY_FOR_LIVE_MODE`

Verified activation wrapper is necessary operator tooling but does not enable production live execution or autonomy config.

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
- Does **not** change wrapper behavior
- Does **not** change smoke script behavior
- Does **not** change approval route behavior
- Does **not** change executor behavior
- Does **not** touch API/server
- Does **not** modify `config/autonomy.json` (`enabled=false` unchanged)
- Does **not** mark broad autonomy ready

Readiness evidence only — no runtime wiring or execution changes.
