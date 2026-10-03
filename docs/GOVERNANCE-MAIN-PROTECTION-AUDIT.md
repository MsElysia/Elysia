# `main` protection audit — read-only result

Observed during this run at `2026-10-03T00:39:25Z`. No repository setting was changed.

## Branch object

`GET https://api.github.com/repos/MsElysia/Elysia/branches/main` returned these relevant fields:

```json
{
  "name": "main",
  "commit": { "sha": "722d8e4fe85d7e42ac34066c2d651849d15e734c" },
  "protected": false,
  "protection": {
    "enabled": false,
    "required_status_checks": {
      "enforcement_level": "off",
      "contexts": [],
      "checks": []
    }
  },
  "protection_url": "https://api.github.com/repos/MsElysia/Elysia/branches/main/protection"
}
```

The recursive tree at exact `main` SHA `722d8e4fe85d7e42ac34066c2d651849d15e734c` returned no `.github/workflows/*` paths.

## Classic branch protection

`GET https://api.github.com/repos/MsElysia/Elysia/branches/main/protection` returned HTTP 403:

```json
{
  "message": "Resource not accessible by integration",
  "documentation_url": "https://docs.github.com/rest/branches/branch-protection#get-branch-protection",
  "status": "403"
}
```

The GitHub integration used for this read cannot expose the detailed protection payload. This does not establish the permissions of a separate owner-side `gh` CLI token.

## Applicable rulesets

`GET https://api.github.com/repos/MsElysia/Elysia/rulesets?includes_parents=true` returned:

```json
[]
```

No applicable repository/parent ruleset was returned by that endpoint.

## Exact-head CI identity observed

`GET /repos/MsElysia/Elysia/commits/722d8e4fe85d7e42ac34066c2d651849d15e734c/check-runs?per_page=100` returned:

```json
{"total_count":0,"check_runs":[]}
```

`GET /repos/MsElysia/Elysia/actions/runs?branch=main&per_page=20` likewise returned `total_count: 0` and `workflow_runs: []`.

For #32 product SHA `0843d9cad29a632a42946a5daf4abe4d0b93bdb0`, the check-runs API returned `total_count: 2`; both checks were named `seed-validation`, used GitHub Actions App ID `15368`, and concluded `success`. Check IDs were `103408086036` (run `34643332080`) and `103407941013` (run `34643288327`). Both records returned the exact requested head SHA.

For the latest bounded #46 product SHA cited by issue #46, `25b34c19975ae281c676fe2b7a0a8d63538e2511`, the API returned `total_count: 1`: check ID `106070631033`, context `seed-validation`, App ID `15368`, status `completed`, conclusion `success`, run `35507875810`.

For the latest bounded #76 product SHA with terminal PASS evidence, `8a61c49d3e8c19496fe63fe386c1e3262d5b2472`, the API returned `total_count: 1`: check ID `106603994047`, context `seed-validation`, App ID `15368`, status `completed`, conclusion `success`, run `35683060026`. Issue #76 also cites later source-contract SHA `268686351598e2696e762fbee561facc1bac27f9` as independently failed with no exact-head CI; it is not substituted as a valid check.

For #97 SHA `f67787dfb3ad277d2128d32dc0e41538d4b8458f`, the check-runs API returned `total_count: 1`; it was named `safe-stack-smoke`, used GitHub Actions App ID `15368`, and concluded `success` on run `37069697890`.

The latest open PR at observation time was this audit PR #98, targeting `main` at exact head `dd5f90b940ea6cea9119151840580ea784520d4d`. Its exact-head check-runs response was `total_count: 0`, `check_runs: []`.

These are different check contexts on different draft lineages. Neither result proves that a CI check runs on a pull request targeting today's `main`; today's `main` tree has no workflow path. The correct required context must be verified on a PR targeting `main` before an owner enables it.

## Conclusions and limits

- The branch endpoint reports `protected: false` and `protection.enabled: false`; the ruleset listing is empty. The API evidence therefore exposes no active branch protection or applicable ruleset for `main`.
- No ruleset detail GET was possible because the repository/parent ruleset listing returned no applicable ruleset IDs. This is a confirmed empty list, not an unreadable detail response.
- The denied protection GET prevents inspection of detailed settings such as the configured review count, force-push setting, or bypass actors. The branch object does not return those values.
- A pull request, an approval, admin enforcement, direct-push restrictions, force-push/deletion restrictions, and bypass actors are therefore not configured by any readable rule. Detailed classic values remain unreadable rather than confirmed individually false.
- The successful check names above are evidence of checks on those exact draft SHAs only. They do not establish that either check is required on `main`.
- There is no currently valid required-check candidate for `main`: exact `main` has no check runs, the recursive tree has no workflow, and the newest PR actually targeting `main` has no check run. The owner-side script therefore fails closed until a human establishes and verifies a check on a `main`-targeting PR.
- Requiring a GitHub review is not, by itself, a human-presence trust anchor. Issue #31 remains open: automation may appear under an owner identity. A repository owner must ensure the approver's credentials cannot be exercised by the gated automation.
- No settings mutation was attempted.
