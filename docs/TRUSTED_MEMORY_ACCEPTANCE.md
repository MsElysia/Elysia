# Trusted pinned-source MemoryCore acceptance (draft)

Replacement for stopped PR #214. It exercises disposable source only, never the operator's installed Elysia or real memory.

## One-command invocation

From a clean, independent Git checkout, obtain the exact target SHA from the independently reviewed PR and run:

```powershell
python -I -B scripts/trusted_memory_acceptance.py --expected-sha <exact-40-character-SHA>
```

The command refuses mismatched HEAD, dirty/untracked source, or known installed-release directories. Before invoking pytest, it removes inherited GIT_* variables, checks the actual worktree root, and exports the pinned commit with `git archive` into a new temporary directory. It compares the extracted Git blob IDs of the runner, MemoryCore module and test module against the pinned commit. It executes tests from the isolated snapshot, not the potentially contaminated checkout.

Python runs with `-I -B`, no inherited PYTHONPATH/PYTEST_ADDOPTS/PYTEST_PLUGINS, an explicit temporary pytest configuration outside the repo, no conftest/auto-loaded plugins, a temporary home and no inherited provider credentials. Source integrity relies on trusted Git and Python installations, not protection from a malicious system administrator.

An exit code of 0 requires real canonical MemoryCore tests to pass, named required test counts to match, no skipped/failed cases, and successful JSON receipt preservation under `REPORTS/trusted-memory/`. Missing prerequisites, wrong source SHA, changed files, missing required assertions and unavailable evidence all fail nonzero. The receipt records source SHA/blob fingerprints, operating system, Python, test counts, outcome and scope flags without retaining memory text.

## Four falsifiable controls

A. Clean pinned commit must run actual MemoryCore tests and save truthful evidence.
B. Dirty B with 30 no-op replacements and inherited GIT_DIR/GIT_WORK_TREE pointing at clean A must not be certified as the clean A source.
C. Ignored pytest.ini and extra/forged_plugin.py must not influence test collection.
D. Untracked or ignored ci_stubs/pytest.py must not replace installed pytest even when inherited Python/pytest environment variables are contaminated.

The adversarial test fixtures have a tracked failing assertion. Wrong SHA, missing required test cases, blocked report output and installed-path refusal are negative controls too. The CI workflow runs both the adversarial tests and the actual one-command source gate on hosted Windows and Ubuntu.

## Scope and release stop

Only hosted/disposable source testing is covered. Actual operator-native Windows read-only ACLs, backup/restore, installed release and restart, privilege-gated symlink tests, and previous canonical merge-SHA CI are NOT verified. Receipts explicitly set installed_release_tested=false, native_windows_directory_acl_tested=false and operational_data_used=false. Existing #11/#6 archive merge hold continues. No authority to merge, install, migrate real data or enable providers/autonomy.

Rollback: close the draft PR and remove its isolated branch; no installed changes exist.
