# GitHub ↔ Windows reconciliation (2026-10-31)

## Authoritative Windows development installation

| Item | Value |
|------|--------|
| Path | `C:\Users\Owner\Project guardian\.worktrees\windows-local-intel-20261029` |
| Branch | `cursor/windows-dashboard-plan-progress-20261031` |
| Exact HEAD | `8d35e1455b34a7e3024cb8d5bda7c6139319e154` |
| Remote | `origin` → `https://github.com/MsElysia/Elysia.git` |
| Interpreter | `C:\Users\Owner\Project guardian\.venv\Scripts\python.exe` (3.13.15) |
| Production launcher | `pilot\START_ELYSIA_VERIFIED_PILOT.bat` |
| Isolated RC launcher | `pilot\START_ELYSIA_RC_DISPOSABLE.bat` |
| Ollama | `127.0.0.1:11434` · model `llama3.2:3b` |

**Do not use** the primary checkout `C:\Users\Owner\Project guardian` as the Windows intelligence app: it is on an older unrelated branch (`codex/issue-91-monitoring-memory-boundary` @ `0760798`) with a large dirty tree.

## Preserved pilot (untouched)

| Item | Value |
|------|--------|
| Path | `C:\Users\Owner\Project guardian\.worktrees\windows-integration-20261028` |
| Branch | `cursor/windows-integration-20261028` |
| SHA | `4f69bd12eaa30f8aa83e3c731359d9c7ea626e50` |

## GitHub `main` vs Windows intel

| Side | SHA | Relation |
|------|-----|----------|
| `origin/main` | `722d8e4fe85d7e42ac34066c2d651849d15e734c` | Ancestor of Windows intel HEAD |
| Windows intel HEAD | `8d35e14…` | **44 commits ahead** of `origin/main`, **0 behind** |

Conclusion: GitHub `main` is **older**, not more advanced. The complete intended Windows local-intelligence program lives on local-only branches and has **not** been pushed.

## Local-only (missing from GitHub remotes)

All `cursor/windows-*` tips used for this integration, including:

- `cursor/windows-dashboard-plan-progress-20261031` @ `8d35e14` (authoritative app)
- `cursor/windows-release-candidate-20261031` @ `cb5821d`
- `cursor/windows-comparable-outcome-learning-20261031` @ `f23280d`
- `cursor/windows-integration-20261028` @ `4f69bd12` (preserved pilot)
- Intermediate feature branches (chat, docs, extract, replan, outcome, …)

None of `8d35e14`, `f23280d`, `4f69bd12`, `cb5821d`, `2981364` appear on any `origin/*` remote-tracking branch after `git fetch`.

## GitHub present / not in Windows intel tip (do not blind-merge)

Diverged draft/integration lines (share ancestry with older Windows delivery but **not** ancestors of `8d35e14`):

| Remote tip | Notes |
|------------|--------|
| `origin/integration/windows-local-delivery-20261028` @ `9bd56b9` | PR #163 draft lineage (restricted memory↔model chat) |
| `origin/chatgpt/windows-local-chat-coverage-20261030` @ `c957260` | PR #164 draft CI coverage |
| `origin/codex/issue-162-memory-persistence` @ `4051eba` | PR #174 — known fail-closed memory work; keep out of intel tip until reviewed |
| `origin/codex/issue-171-task-evidence` @ `f8bbdbc` | PR #173 |
| `origin/codex/verified-capability-v1` @ `452d986` | PR #175 |
| `origin/codex/verified-browser-calculator-v1` @ `292ee50` | PR #176 |
| `origin/cursor/application-runtime-safety-668d` @ `0eb52e2` | New remote tip |

Open PRs observed via public API (gh CLI unauthenticated): many drafts (#163–#177 stack, #160 Linux boot, dashboard series #149–#159, etc.). None of these replace the authoritative local Windows intel tip.

## Primary checkout dirty state (preserved, not integrated)

`C:\Users\Owner\Project guardian` has ~81 dirty/untracked paths on `codex/issue-91-monitoring-memory-boundary`. Snapshot saved under USB `main-dirty-snapshot\` (status + tracked diff). **Not** reset or merged into the Windows intel worktree.

## USB recovery

`D:\ElysiaBackups\windows-github-reconciliation-20261031\`

- `elysia-authoritative-8d35e14.bundle`
- `elysia-windows-authoritative-all-branches.bundle` (21 Windows branch tips)
- `MANIFEST.md`

## Safe reconciliation performed

1. `git fetch origin --prune` (no pull/merge/reset).
2. Verified commit identity and ahead/behind vs `origin/main`.
3. USB bundles + independent restore of authoritative tip.
4. Documented single authoritative install path.
5. No push; no merge of diverged GitHub draft PRs into the Windows tip.

## Owner approval still required to

- Push `cursor/windows-dashboard-plan-progress-20261031` (or a release branch) to GitHub.
- Merge any of PR #160–#177 / issue-162 into the Windows tip.
- Clean or relocate the dirty primary checkout.
