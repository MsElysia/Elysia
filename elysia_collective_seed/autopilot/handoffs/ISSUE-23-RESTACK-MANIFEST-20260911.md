# Issue #23 authoritative restack manifest

Status: implementation staging branch only; no integration-readiness claim.

## Authoritative base

- Branch: `autopilot-003-issue23-restack`
- Base: PR #26 documentation-bearing head `3ac32d1f3f90a27788553e7c5aebc7baf779e438`
- Independently verified #22 product remains pinned separately to `4e5a55b553a1df303b3559b5579fdab930691204`.
- This branch must not be merged to `main` by the autopilot.

## Source delta to port, not lineage to merge

PR #27 product head `79b6c6456eae1d6a400c8b08516a8478d769d25e` is exactly one commit above obsolete reconciliation snapshot `4d9fceba9fa438077c5eb112c889f4306687ae79`. Its reviewed #23 delta touches exactly:

1. `docs/ISSUE-23-AUDIT-BOOTSTRAP.md` (add)
2. `elysia.py`
3. `elysia_sub_guardian.py`
4. `project_guardian/guardian_singleton.py`
5. `pytest.ini`
6. `tests/conftest.py`
7. `tests/test_guardian_audit_bootstrap.py` (add)

Do **not** merge/cherry-pick PR #27 lineage wholesale: GitHub comparison shows PR #27 and PR #26 are divergent. Port only the reviewed semantic delta file-by-file, resolving against this branch's current files.

## Required acceptance gates after port

- Audit/inspection path performs zero GuardianCore construction or activation.
- Explicit disable policy is not overwritten by lower-level defaults.
- Monitoring, ElysiaLoop, prompt evolution, UI/server auto-start, live probes, socket, subprocess and provider entrypoints are guarded by adversarial tests and untouched in audit mode.
- Repeated audit inspection leaves no persistent/background survivor.
- Preserve #22/#25 behavior and existing safety gates.
- Run the #23 adversarial suite and exact-head safe-stack CI.
- Obtain a fresh independent falsification verdict on the resulting exact SHA.
- Keep Issue #23 open: a descriptor alone does not prove direct `GuardianCore(...)` / `get_guardian_core` construct-without-activate semantics or dynamic canonical runtime wiring.

## Safety boundary

No merge, deployment, runtime/provider/network activation, external posting, credential/private-data expansion, or weakening of audit/rollback controls is authorized by this manifest.