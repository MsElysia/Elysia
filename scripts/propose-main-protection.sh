#!/usr/bin/env bash
set -euo pipefail

# Owner-run proposal generator. It prints a proposed branch-protection PUT;
# it never calls the mutating endpoint.
repo="${GITHUB_REPOSITORY:-MsElysia/Elysia}"
context="${REQUIRED_CHECK_CONTEXT:-}"
app_id="${REQUIRED_CHECK_APP_ID:-}"
pr_number="${VERIFIED_MAIN_PR_NUMBER:-}"

if [[ ! "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ || -z "$context" || ! "$app_id" =~ ^[0-9]+$ || ! "$pr_number" =~ ^[0-9]+$ ]]; then
  cat >&2 <<'MSG'
STOP: provide REQUIRED_CHECK_CONTEXT, REQUIRED_CHECK_APP_ID, and
VERIFIED_MAIN_PR_NUMBER. The script will independently verify the PR base and
the successful exact-head check before printing any proposed settings command.
MSG
  exit 2
fi
context_pattern='^[A-Za-z0-9_.:/ -]+$'
if [[ ! "$context" =~ $context_pattern ]]; then
  echo "STOP: check context contains characters this proposal generator does not accept." >&2
  exit 2
fi

pr_payload=$(gh api "repos/$repo/pulls/$pr_number")
read -r base_ref head_sha < <(python3 -c 'import json,sys; p=json.load(sys.stdin); print(p["base"]["ref"], p["head"]["sha"])' <<<"$pr_payload")
if [[ "$base_ref" != "main" || ! "$head_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "STOP: the selected PR does not target main or has no valid head SHA." >&2
  exit 2
fi

checks_payload=$(gh api "repos/$repo/commits/$head_sha/check-runs?per_page=100")
if ! CHECK_CONTEXT="$context" REQUIRED_CHECK_APP_ID="$app_id" EXPECTED_HEAD_SHA="$head_sha" \
  python3 -c 'import json,os,sys; d=json.load(sys.stdin); c=os.environ["CHECK_CONTEXT"]; a=int(os.environ["REQUIRED_CHECK_APP_ID"]); h=os.environ["EXPECTED_HEAD_SHA"]; ok=any(r.get("name")==c and r.get("head_sha")==h and r.get("status")=="completed" and r.get("conclusion")=="success" and (r.get("app") or {}).get("id")==a for r in d.get("check_runs", [])); sys.exit(0 if ok else 1)' <<<"$checks_payload"; then
  echo "STOP: exact successful check/context/App ID was not found on that main-targeting PR head." >&2
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
