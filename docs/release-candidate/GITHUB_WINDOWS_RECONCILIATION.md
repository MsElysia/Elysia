# GitHub ↔ Windows reconciliation (2026-10-31)

## Authoritative Windows development installation

| Item | Value |
|------|--------|
| Path | `C:\Users\Owner\Project guardian\.worktrees\windows-local-intel-20261029` |
| Branch | `cursor/windows-dashboard-plan-progress-20261031` |
| Exact HEAD (published) | `2759ba43cf14ef9fb3be579d143183788f341af3` |
| Draft PR | [#178](https://github.com/MsElysia/Elysia/pull/178) (base `main`) |
| Remote | `origin` → `https://github.com/MsElysia/Elysia.git` |
| Interpreter | `C:\Users\Owner\Project guardian\.venv\Scripts\python.exe` (3.13.15) |
| Production launcher | `pilot\START_ELYSIA_VERIFIED_PILOT.bat` |
| Isolated RC launcher | `pilot\START_ELYSIA_RC_DISPOSABLE.bat` |
| Ollama | `127.0.0.1:11434` · model `llama3.2:3b` |

**Do not use** the primary checkout `C:\Users\Owner\Project guardian` as the Windows intelligence app: it is on an older unrelated branch (`codex/issue-91-monitoring-memory-boundary` @ `0760798`) with a large dirty tree.

Isolated verification worktree (exact PR #178 head; may also host a separate docs/CI repair branch):  
`C:\Users\Owner\Project guardian\.worktrees\pr178-rc-verify-20261031`

## Preserved pilot (untouched)

| Item | Value |
|------|--------|
| Path | `C:\Users\Owner\Project guardian\.worktrees\windows-integration-20261028` |
| Branch | `cursor/windows-integration-20261028` |
| SHA | `4f69bd12eaa30f8aa83e3c731359d9c7ea626e50` |

## GitHub `main` vs Windows intel

| Side | SHA | Relation |
|------|-----|----------|
| `origin/main` | `722d8e4fe85d7e42ac34066c2d651849d15e734c` | Ancestor of published Windows intel HEAD |
| Published Windows intel HEAD | `2759ba43…` | Ahead of `origin/main`, **0 behind**; published as draft PR #178 |

Conclusion: GitHub `main` remains older. The Windows local-intelligence program is on the published draft branch above; it is **not** merged to `main`.

Historical local tips (superseded as “current app tip”, still useful USB/checkpoints):

- `8d35e1455b34a7e3024cb8d5bda7c6139319e154` — Plan & Progress + RC disposable BAT
- `f23280d9765759e1f97a96b9b9b786f0caa1760d` — comparable-outcome learning
- `cb5821d…` — local RC docs branch tip prior to recon commit

## Related local branches (do not confuse with PR #178 head)

- `cursor/windows-dashboard-plan-progress-20261031` @ `2759ba43` — **published** authoritative app / PR #178
- `cursor/windows-release-candidate-20261031` — historical local RC docs line
- `cursor/windows-comparable-outcome-learning-20261031` @ `f23280d` — feature checkpoint
- `cursor/windows-integration-20261028` @ `4f69bd12` — preserved pilot
- `cursor/pr178-rc-verify-docs-ci-20261031` — separate draft repair for RC identity/docs/CI (must not replace PR #178 head without authorization)

## GitHub present / not in Windows intel tip (do not blind-merge)

Diverged draft/integration lines (share ancestry with older Windows delivery but **not** ancestors of `2759ba43`):

| Remote tip | Notes |
|------------|--------|
| `origin/integration/windows-local-delivery-20261028` @ `9bd56b9` | PR #163 draft lineage (restricted memory↔model chat) |
| `origin/chatgpt/windows-local-chat-coverage-20261030` @ `c957260` | PR #164 draft CI coverage |
| `origin/codex/issue-162-memory-persistence` @ `4051eba` | PR #174 — known fail-closed memory work; keep out of intel tip until reviewed |
| `origin/codex/issue-171-task-evidence` @ `f8bbdbc` | PR #173 |
| `origin/codex/verified-capability-v1` @ `452d986` | PR #175 |
| `origin/codex/verified-browser-calculator-v1` @ `292ee50` | PR #176 |
| `origin/cursor/application-runtime-safety-668d` @ `0eb52e2` | New remote tip |

None of these replace the authoritative Windows intel tip published in PR #178.

## Primary checkout dirty state (preserved, not integrated)

`C:\Users\Owner\Project guardian` has a large dirty/untracked tree on `codex/issue-91-monitoring-memory-boundary`. Snapshot saved under USB `main-dirty-snapshot\` (status + tracked diff). **Not** reset or merged into the Windows intel worktree.

## USB recovery

`D:\ElysiaBackups\windows-github-reconciliation-20261031\`

- `elysia-authoritative-HEAD.bundle` / `elysia-authoritative-8d35e14.bundle`
- `elysia-windows-authoritative-all-branches.bundle` (Windows branch tips)
- `MANIFEST.md`

## Safe reconciliation performed

1. `git fetch origin --prune` (no pull/merge/reset).
2. Verified commit identity and ahead/behind vs `origin/main`.
3. USB bundles + independent restore of authoritative tip.
4. Documented single authoritative install path.
5. Later: exact-SHA non-force push of `2759ba43…` and draft PR #178 (no merge).
