# `main` protection audit — read-only result

Observed during this run (GitHub API refs captured 2026-10-03 UTC). No repository setting was changed.

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

For #32 product SHA `0843d9cad29a632a42946a5daf4abe4d0b93bdb0`, the check-runs API returned `total_count: 2`; both checks were named `seed-validation`, used GitHub Actions App ID `15368`, and concluded `success` on run `34643332080`.

For #97 SHA `f67787dfb3ad277d2128d32dc0e41538d4b8458f`, the check-runs API returned `total_count: 1`; it was named `safe-stack-smoke`, used GitHub Actions App ID `15368`, and concluded `success` on run `37069697890`.

These are different check contexts on different draft lineages. Neither result proves that a CI check runs on a pull request targeting today's `main`; today's `main` tree has no workflow path. The correct required context must be verified on a PR targeting `main` before an owner enables it.

## Conclusions and limits

- The branch endpoint reports `protected: false` and `protection.enabled: false`; the ruleset listing is empty. The API evidence therefore exposes no active branch protection or applicable ruleset for `main`.
- The denied protection GET prevents inspection of detailed settings such as the configured review count, force-push setting, or bypass actors. The branch object does not return those values.
- The successful check names above are evidence of checks on those exact draft SHAs only. They do not establish that either check is required on `main`.
- Requiring a GitHub review is not, by itself, a human-presence trust anchor. Issue #31 remains open: automation may appear under an owner identity. A repository owner must ensure the approver's credentials cannot be exercised by the gated automation.
- No settings mutation was attempted.
