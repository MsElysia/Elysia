#!/usr/bin/env bash
set -euo pipefail

# Owner-run proposal generator. It prints a proposed branch-protection PUT;
# it never calls the mutating endpoint.
repo="${GITHUB_REPOSITORY:-MsElysia/Elysia}"
context="${REQUIRED_CHECK_CONTEXT:-}"
app_id="${REQUIRED_CHECK_APP_ID:-}"
verified="${CHECK_VERIFIED_ON_MAIN_TARGETING_PR:-}"

if [[ -z "$context" || ! "$app_id" =~ ^[0-9]+$ || "$verified" != "yes" ]]; then
  cat >&2 <<'MSG'
STOP: set REQUIRED_CHECK_CONTEXT, REQUIRED_CHECK_APP_ID, and
CHECK_VERIFIED_ON_MAIN_TARGETING_PR=yes only after a successful run confirms
that exact check on a pull request targeting main. Existing evidence shows
seed-validation on #32 and safe-stack-smoke on #97, on different draft
lineages; neither is yet verified for today's main.
MSG
  exit 2
fi
if [[ ! "$context" =~ ^[A-Za-z0-9_.:/ -]+$ ]]; then
  echo "STOP: check context contains characters this proposal generator does not accept." >&2
  exit 2
fi

body=$(cat <<JSON
{
  "required_status_checks": {
    "strict": true,
    "checks": [{"context": "${context}", "app_id": ${app_id}}]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 1,
    "require_last_push_approval": true
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
)

printf '%s\n' 'Proposed owner-only mutation (NOT executed):'
printf 'gh api --method PUT repos/%s/branches/main/protection --input - <<\047JSON\047\n%s\nJSON\n' "$repo" "$body"
printf '\n%s\n' 'Before running it, the repository owner must inspect bypass actors and confirm the approver account is not usable by automation.'
