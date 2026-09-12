# One-shot historical repair scripts

**Not runtime code. Not normal maintenance. Not invoked by CI or smoke tests.**

These scripts were used during the safe-stack consolidation (2026-05) to patch
`CONTROL_PANEL_TEMPLATE` in `project_guardian/ui_control_panel.py` when dashboard
markers or helper copy were missing from the template string.

## Source of truth today

| What | Where |
|------|--------|
| Control panel HTML/JS | `project_guardian/ui_control_panel.py` (`CONTROL_PANEL_TEMPLATE`) |
| UI marker tests | `project_guardian/tests/test_control_panel_*.py` |
| Quarantine guard | `project_guardian/tests/test_one_shot_ui_scripts_quarantined.py` |

## When to run (rare)

Only if a checkout has a **broken** template (pytest UI marker tests fail) and you
need to re-apply a known-good patch **manually**. Each script is idempotent: it
exits early if markers are already present.

```bash
# From repository root — run in order only if markers are missing:
python scripts/maintenance/one_shot/_restore_safe_stack_control_panel_ui.py
python scripts/maintenance/one_shot/_apply_control_panel_ui_clarity.py
python scripts/maintenance/one_shot/_apply_control_panel_secondary_clarity.py
# _patch_prompt_contract_ui.py is superseded by restore+clarity; keep for archaeology only.
```

## Scripts

| Script | Purpose |
|--------|---------|
| `_restore_safe_stack_control_panel_ui.py` | Brain Trace, SI proposals, export, memory ranking, prompt contracts panels + JS |
| `_apply_control_panel_ui_clarity.py` | System safety card, helper text, empty states, button labels |
| `_apply_control_panel_secondary_clarity.py` | Learning, Task Queue, Workbench, Security, Introspection, observability helpers |
| `_patch_prompt_contract_ui.py` | Early prompt-contract panel patch (historical; largely superseded) |

## Do not

- Add these to `scripts/run_safe_stack_smoke_tests.py`
- Call from `.github/workflows/*`
- Import from `project_guardian` or `elysia` packages
- Run in production deploy pipelines

See `docs/ELYSIA_SAFE_STACK_FINAL_CHECKPOINT.md` § H (cleanup risks).
