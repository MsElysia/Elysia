# Issue #116 repair evidence and independent-review handoff

Defective parent: `da6445424ecca0493e976973bcb84e986eaef318`.
Existing draft PR: https://github.com/MsElysia/Elysia/pull/115
Defect: https://github.com/MsElysia/Elysia/issues/116

Disposable synthetic `evidence.txt` reproduction on the exact parent:
first `archived`, then `already_recorded` after changing source_name,
archived_at to 1900 and adding unexpected_trusted_field. Tampered receipt
and archived object remained byte-identical. After repair the same reproduction
returns `rejected`; both artifacts remain unchanged.

Native Windows / Python 3.13.15 validation on 2026-10-12:

- Original suite on defective parent: 35 run, 34 passed, 1 skipped, no failures.
- Final expanded suite: 40 run, 39 passed, 1 skipped, no failures.
- Focused `-k test_receipt` regressions: 5 run, 5 passed, no skips/failures.
- Skip: real symlink creation unavailable (WinError 1314). No privilege changes.
  Simulated links/reparse points, real junction and Windows sharing tests pass.
- Earlier expanded run: 40 run, 38 passed, 1 failure, 1 skip. Existing writer
  test retried inside the recent-write quiet interval; test now resets synthetic
  mtime after closing the writer to isolate sharing recovery. Production quiet
  interval behavior was not changed.
- Initial reproduction in sandbox failed with temp-directory PermissionError;
  rerun with approved native access succeeded. A read-only Python `-c` attempt
  had shell quoting SyntaxError; it supplied no validation evidence.
- Initial diff check reported an extra EOF blank line in documentation, removed
  before final diff check. No hosted CI or Safe Stack pass is claimed.

Commands from the existing worktree:

```text
python -B -m unittest discover -s scripts/tests -p test_mobile_inbox.py -v
python -B -m unittest discover -s scripts/tests -p test_mobile_inbox.py -k test_receipt -v
git diff --check
```

Fresh independent review must pin the updated PR head (the repair commit
containing this file) and compare it to the defective parent above. Reproduce
the combined original mutation and each individual provenance/schema mutation
using disposable data. Verify receipts/objects are unchanged on rejection,
missing objects are not republished behind existing receipts, and interrupted
object-without-receipt recovery, duplicate/rename behavior and exact bytes remain
intact. Run all 40 tests and report skips explicitly. Review strict integer vs
boolean types, duplicate JSON keys, ctime comparison using path snapshots on
Windows, invalid/past/future timestamps, and the positive plausible-timestamp
regression. No independent PASS is claimed by the implementer.

Remaining limit: archived_at has format/local-clock consistency validation only.
A plausible alteration can pass; no trusted historical record authenticates it.
Source filesystem metadata is also a current local observation, not signed
provenance. See MOBILE_INBOX.md for clock rollback and restored-source behavior.
No new service/integration, real memory changes, provider/autonomy activation,
permission changes, governance release, merge or deployment occurred.
