# Issue #111: authenticated rollback backup contents

Direct child of PR #110 exact base
`700cbfebf13686f776cd904da8f27ec0dfe05455`, branch
`codex/issue111-backup-integrity-20261009`. Keep draft and unmerged.

## Reproduction

On native Windows, execute the exact base transaction module obtained with
`git show 700cbfebf13686f776cd904da8f27ec0dfe05455:project_guardian/local_ingestion/apply_transaction.py`
in a disposable process, leaving the base's queue reader and all other modules
unchanged. Create a synthetic queue containing `{"candidate_id":"old"}`,
a version-1 manifest targeting that queue with `existed: true`, and
`backup-0` containing `BROKEN\n`. Call `read_known_candidate_ids(queue)`.

Observed at the exact base:

```text
reader_result= set()
prior_preserved= False
public_bytes= b'BROKEN\n'
journal_exists= False
```

The repaired regression
`test_issue111_exact_legacy_reproduction_now_blocks_queue_reader` requires an
exception and byte-for-byte preservation of both public files and journal.
All destinations are synthetic, disposable test directories.

## Protocol and compatibility

Version-2 manifests record `backup_size` and lowercase hex `backup_sha256` for
every existing destination, computed from the same original bytes written to
its flushed backup. New destinations record null for both fields. Backups and
manifest are flushed before any publication. A verification-only recovery pass
checks storage preserved every original before publishing a stage file.

Recovery validates the complete manifest schema, paths, commit marker, sizes,
digests and all required backup files before restoring or deleting any public
file. It retains verified bytes and never reopens a backup during restoration.
Malformed metadata (including duplicate JSON keys), missing/non-file/symlink
backups and mismatched bytes refuse, retaining the active journal and public
files. Participating readers and writers remain blocked. Version-2 committed
journals are also verified before cleanup, conservatively preserving evidence
on corruption even though no rollback is needed.

An unfinished version-1 manifest with any existing destination refuses because
its backup integrity cannot be established. It is never upgraded by hashing
the currently present backup, comparing a possibly published target, or guessing
from parseable content. Version-1 journals needing only removal of newly created
destinations may roll back; a valid committed version-1 journal may finish its
existing cleanup protocol without restoring bytes. Existing schema/path/backup
presence checks still apply. Staging without a published manifest retains the
existing safe cleanup behavior.

An interrupted valid rollback retains its complete journal and can repeat. If
backup corruption occurs before a later retry, that retry blocks before any
further restoration. The repair does not undo legitimate restorations completed
before a subsequent storage failure.

## Verification handoff

The draft repair PR records the final exact commit and hosted run links/counts;
this source document deliberately does not predict a commit hash or CI result.
Both inherited workflow jobs check out and assert the exact PR head. Linux runs
the Safe Stack including the transaction suite; native Windows runs the complete
memory slice, including real mutex abandonment, process collision and killed
workers during staging/publication/rollback/commit/cleanup. New cases in the
same transaction test file run in both jobs without workflow changes.

Fresh independent verifier: detach the repair PR's recorded SHA. Reproduce the
base failure separately, then attack corrupted, truncated, equal-size swapped,
missing, non-file and malformed backups/metadata. Place the bad backup last in
rollback order and include newly created destinations to prove zero partial
mutation. Verify reader/writer refusal and journal preservation, interrupted
multi-file rollback/retry, empty originals, backup write corruption before
publication, verified-byte snapshot behavior and all version-1 policies. Run
both inherited platform slices; neither Windows-native test may skip on Windows.
Report exact SHA, commands/counts/skips, any falsification, remaining limits and
a bounded PASS / FAIL / PARTIAL verdict. Earlier PR acceptance does not transfer.

## Limits

Digests detect backup-content corruption relative to the durably recorded
manifest; they do not authenticate a malicious rewrite of both manifest and
backups. All verified original bytes are held in memory; large exports remain
uncertified. Local cooperating APIs and existing OS locks remain the boundary.
Physical power loss, raw observers, noncooperating writers, destination identity
replacement, network filesystems, untargeted aliases and inherited cleanup
storage failures retain PR #110's limits. Windows directory fsync is unavailable.
Older unfinished journals needing backup restoration require independently
trusted original data and a separate explicit repair decision; this code does
not clear or regenerate them automatically.

No real user memory, merge, deployment, runtime autonomy, provider activation,
permissions, credentials, approval promotion, executor wiring or Issue #112
integration is part of this repair.
