# Minimal One-Time Setup for Elysia Autopilot

The objective is to minimize repeated human involvement. These are the few setup actions that require access only the user can grant.

## 1. Local archive workspace

On the Windows machine holding historical Guardian/Elysia files, create one parent workspace without deleting or moving originals yet. Example:

```text
C:\Elysia-Reconciliation\
  canonical\        # current Guardian checkout
  legacy\           # shortcuts/copies/read-only roots to old Guardian/Elysia folders
  incoming\         # ChatGPT export ZIP and newly discovered archives
  reports\          # machine-generated inventories and correspondence maps
  archive-staging\  # proposed archive only; nothing is deleted automatically
```

The exact drive/path can differ. Preserve the original historical folders until reconciliation is verified.

## 2. Cursor local execution

Use Cursor's current local/My Machines capability so agents can inspect the local historical files without uploading the whole archive to GitHub.

Preferred boundary:
- grant Cursor access to the dedicated reconciliation workspace only;
- run Archaeologist/Correspondence Analyst read-only first;
- allow write-capable Consolidator only against an isolated canonical worktree/branch;
- do not expose unrelated home directories or credentials.

Repo-defined Cursor agents/rules/skills should be loaded from the canonical checkout.

## 3. Codex workspace

Open/attach the canonical repository in Codex and ensure it can access the GitHub repo/worktree environment needed for coding tasks.

Codex should follow repository `AGENTS.md`, work from GitHub AUTOPILOT issues, and return changes through branches/PRs rather than directly treating conversation output as project state.

Use Codex Automations for recurring engineering once the initial reconciliation gates are validated.

## 4. ChatGPT historical export

For complete raw-history recovery, request a ChatGPT data export and place the resulting export ZIP unchanged into the reconciliation `incoming` directory.

Do not manually edit the export before import. Guardian already contains historical ChatGPT import tooling; the Collective design adds a provenance-preserving v2 layer around it.

The import pipeline must filter for Elysia/Guardian/Constitution material before anything enters Collective memory. The account-wide export itself is not automatically Collective memory.

## 5. GitHub

GitHub is the external task/review control plane:
- Master issue: `ELYSIA AUTOPILOT MASTER CONTROL PLANE`
- AUTOPILOT issues hold durable objectives/acceptance criteria.
- PRs carry implementation evidence and review.
- GitHub Actions supplies provider-independent checks.

Keep `main` protected from autopilot integration until the reconciliation/release gates are explicitly cleared.

## 6. Optional local model, later

Do not block the project on a local LLM. Add one only when there is enough repetitive work to justify it.

Good local-model jobs:
- bulk file/topic classification;
- duplicate/near-duplicate triage;
- embeddings;
- log clustering;
- cheap routing suggestions;
- local watchdog summaries.

Local model outputs are suggestions/evidence, not governance or release authority.

## After these setup actions

The intended autonomous loop is:

```text
GitHub task/control state
        |
        v
ChatGPT supervisor generates/refines work
        |
        +-------------------+
        |                   |
        v                   v
     Codex                Cursor
 repo/cloud work      local/archive work
        |                   |
        +---------+---------+
                  v
           independent review
                  |
                  v
              CI/tests
                  |
                  v
        accepted task completion
                  |
                  v
          next task generated
```

Human attention should be reserved for:
- first-time access grants;
- ambiguous conflicts in historical intent;
- Constitution interpretation/amendment;
- destructive deletion/archival decisions where provenance is uncertain;
- new authority over private data, deployment, credentials, finance, or external posting;
- final release/governance decisions that policy requires.
