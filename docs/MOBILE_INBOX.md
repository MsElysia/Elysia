# Local-first mobile inbox (draft, archive only)

Elysia can now take a stable local file delivered by an external transport, verify
its exact bytes, archive it once by SHA-256, and preserve each observed source
path/version in a receipt. This command does not interpret content, normalize
text, create memory candidates, write memory records, call providers, or start a
watcher. Syncthing installation, pairing and transport remain operator work.

## Inspection and overlap decision

Isolated branch: `codex/local-first-mobile-inbox-20261010`.
Exact base: main `722d8e4fe85d7e42ac34066c2d651849d15e734c`.
Main has no `project_guardian/local_ingestion` package. The existing ingestion
architecture was inspected on the reconciliation and memory-import branches,
along with transcription tests, main's memory-path, duplicate-proposal and
FileWriter path-safety tests. No applicable tracked AGENTS.md exists on this base.
All open PRs were inventoried on 2026-10-10; none supplies this inbox capability.

| Existing lane | Reused concept / reason it cannot supply this intake |
| --- | --- |
| Reconciliation transcription ingestion | Existing `.txt/.md/.vtt/.srt` allowance and provenance fields inform this command. It normalizes text/line endings and hashes normalized content, writes non-atomic artifacts and omits duplicate origins. Calling it would lose original bytes. |
| [Issue #95](https://github.com/MsElysia/Elysia/issues/95), [PR #103](https://github.com/MsElysia/Elysia/pull/103) `53770acf...` | Raw source hashes and source linkage are established patterns. ChatGPT apply is format-specific and also creates intelligence/candidate artifacts. This command archives opaque bytes before any later, separately authorized import. |
| [Issue #111](https://github.com/MsElysia/Elysia/issues/111), [PR #113](https://github.com/MsElysia/Elysia/pull/113) `e59e3716...` | Repairs rollback integrity in existing memory publication. Inbox artifacts are immutable, one-file publications with replay, so no memory rollback or journal dependency is needed. |
| [Issue #112](https://github.com/MsElysia/Elysia/issues/112), [PR #114](https://github.com/MsElysia/Elysia/pull/114) `75032928...` | Consolidation/verification relay, not file intake. Pipeline, workflows, and production holds are unchanged. |
| Main FileWriter / proposal duplicate checks | FileWriter is repository-scoped and imports trust/runtime components; proposal detection is semantic, not byte identity. Neither is appropriate for an external opaque archive. |

[Issue #11's current checkpoint/handoff](https://github.com/MsElysia/Elysia/issues/11#issuecomment-6089305304)
and predecessor consolidation gates were read. This is a separate draft from
main, not the gated #110+#101 composition, and carries no inherited acceptance or
release authority. No code from pending branches is incorporated. Standard
library SHA-256, JSON, filesystem atomic rename and native OS locking supply the
missing intake layer; receipts are archival metadata, not another memory store.

## One-shot command

Requires Python 3.10+ and a local fixed Windows disk (NTFS recommended). No new
dependencies. Create an inbox and a separate **empty** archive directory outside
all repository checkouts and memory storage. Both must already exist. Supply
every existing external memory directory with repeated `--memory-root` arguments;
repository storage is excluded automatically, including the original checkout
when running from a Git worktree. The command deliberately does not discover or
open live database/configuration contents.

For an operator-created layout such as `C:\ElysiaInbox`, `C:\ElysiaInboxArchive`
and an existing memory directory `D:\ElysiaMemory`, run from this draft checkout:

```powershell
python -I scripts/mobile_inbox.py `
  --inbox C:\ElysiaInbox `
  --archive C:\ElysiaInboxArchive `
  --memory-root D:\ElysiaMemory `
  --stable-seconds 10 `
  --max-bytes 26214400
```

Replace the example memory root with the actual directory; repeat for other
roots. A memory directory may be protected even if its files have other names.
Missing roots, relative/traversing paths, overlapping roots, UNC/device paths,
mapped/network/removable drives, and symlink/junction/reparse-point components
fail before archive initialization. Never point the archive at existing storage.

Default extensions: `.txt .md .vtt .srt .json .pdf .jpg .jpeg .png`. Narrow with
`--extensions .txt .md`; expansion beyond this fixed allowlist is refused. This
is extension gating, not format validation or malware scanning. A `.txt` may
contain binary bytes: those bytes remain inert and are preserved without parsing.

Only top-level regular files are processed. Hidden names, Windows reserved names,
alternate streams, control/bidi characters, trailing dots/spaces, and names over
200 characters are rejected. Hard links and special files are also refused.
Syncthing's `.stfolder`, `.stignore`, `.stversions`, `.syncthing.*.tmp` and
`~syncthing~*.tmp` are reported as `ignored_transport`; they are neither read as
content nor traversed. Linked transport entries are rejected.

Files must be at least the stability interval old and retain identity, size and
mtime across two observations separated by that interval (default 10 seconds,
configurable above zero up to 60). Source bytes are streamed to staging with a
size bound, hashed, reread, and compared; staged bytes are read back and verified.
On Windows the source handle denies writers and deletion while held. Changing
or newly written files are deferred; sharing/permission failures are explicit
errors. A deferred file requires another manual invocation.

## Archive and restart behavior

```text
archive.kind          dedicated archive identity
intake.lock           persistent lock file; OS lock released on exit/process death
objects/<sha256>      original bytes, no filename-derived destination paths
receipts/<id>.json    source/version provenance (untrusted-data, no memory write)
temporary/*.part      unpublished staging; never ingested on restart
runs/<uuid>.json      one local structured report per completed invocation
```

Receipt identity is SHA-256 over source absolute path, byte hash, size and source
mtime in nanoseconds. It records source name, mtime/ctime, archive time and object
link. Ctime has OS-specific semantics and is recorded as reported; CPython Windows
lstat/fstat ctime semantics differ, so ctime is excluded from cross-handle checks.
Identical bytes under another name get another receipt referencing the same
object. Replay of the same observed source/version does not rewrite the object or
receipt. This records observations, not transport session/device authentication.

The entire invocation holds a nonblocking OS archive lock. Publications use
same-volume rename under that lock. A successful blob publication may precede
its receipt; this is intentional, recoverable ordering, not an atomic batch.
Failure before blob publication leaves no accepted object. Failure after it
leaves verified reusable bytes; replay verifies them and supplies the missing
receipt. Corrupt objects/receipts are refused and retained, never overwritten or
silently repaired. There is no recovery code capable of restoring memory files.

Exit codes: `0` all eligible observations handled (transport entries ignored),
`1` deferred/rejected/file errors, `2` configuration or invocation/log failure,
`130` keyboard interruption. JSON includes per-path status/error type/reason,
hashes, sizes, artifact paths, counts and `live_memory_written=false`. An inability
to write the local log is visible on stderr with code 2; already committed intake
remains safe to replay. Fatal failure may prevent a local log from being written.

Never unlink the persistent lock file. Abrupt process death may leave unpublished
`.part` files. They are ignored rather than mistaken for receipts/objects; review
them while no command runs if disk cleanup is needed. Nothing auto-deletes unique
archived history or incoming source files.

## Synthetic verification

Run from the isolated checkout without loading the repository's runtime fixtures:

```powershell
python -B -m unittest discover -s scripts/tests -p test_mobile_inbox.py -v
git diff --check
```

Tests use disposable synthetic files only. They cover exact bytes including
CRLF/NUL/non-UTF8, SHA/size/provenance, duplicate/renamed duplicate, recent/partial,
same-size changing/replaced sources, copy failures, actual process termination
before blob/receipt publication, lock release/retry, restart/idempotence, corrupt
artifacts, names/extensions/size bounds, path/root/hardlink/reparse protections,
real Windows junctions and open writers, missing folders, injected EACCES/ENOSPC,
log failures, CLI exits, synthetic memory sentinels, and provider/network/external
action breakers. No ACL changes or actual disk filling are used for fault tests.

Native Windows Python 3.13.15: **35 tests run, 34 passed, 1 skipped**. The skipped
test requires real symlink-creation privileges; no privileges were changed.
An initial sandbox attempt failed to create disposable temp subdirectories and
was not counted as product evidence. Native runs exposed Windows ctime differences
and a venv-launcher kill-test issue; both were corrected before this final pass.
`git diff --check` also passed. Normal CLI evidence is recorded
in [MOBILE_INBOX_SYNTHETIC_EVIDENCE.json](MOBILE_INBOX_SYNTHETIC_EVIDENCE.json).
The normal command ran in three fresh processes: first intake archived one object
and detected one duplicate; restart returned two already-recorded observations;
rename added one duplicate origin. All exited zero with one unchanged 67-byte
object, three receipts and an unchanged synthetic memory sentinel. The fixture
included `.stfolder`. Synthetic demonstration folders were removed afterward.

## Later operator-run Syncthing demonstration on Windows

This procedure is documentation only; Syncthing was not installed/configured or
used during implementation, and no live phone/user files were ingested.

1. After installing Syncthing on Windows and Syncthing-Fork on Android yourself,
   create a dedicated phone test folder containing only synthetic files. Pair the
   two devices and share only that folder. Set Android **Send Only** and Windows
   **Receive Only**, using the dedicated Windows inbox path. Keep the archive and
   all memory/repository directories outside every shared folder. These folder
   behaviors are described in [Syncthing's folder-type documentation](https://docs.syncthing.net/users/foldertypes.html).
2. Transfer a synthetic `mobile-proof.txt` with a known byte size and SHA-256.
   Wait for the Windows folder to report up to date. Syncthing publishes from
   temporary copies; the intake command ignores both documented temporary naming
   forms ([synchronization documentation](https://docs.syncthing.net/users/syncing.html)).
   Wait an additional quiet interval, then run the one-shot command above with
   the real configured inbox/archive paths and all protected memory roots.
3. Inspect stdout and the reported local run JSON. For the returned object path,
   compare source and archive:

   ```powershell
   Get-FileHash -Algorithm SHA256 C:\ElysiaInbox\mobile-proof.txt
   Get-FileHash -Algorithm SHA256 C:\ElysiaInboxArchive\objects\<reported-sha256>
   (Get-Item C:\ElysiaInbox\mobile-proof.txt).Length
   (Get-Item C:\ElysiaInboxArchive\objects\<reported-sha256>).Length
   ```

   Replace `<reported-sha256>` with the actual result. Check the receipt's source
   path/time/hash/size and `untrusted-data` flag. Verify source remains present.
4. Run the same command again: expect `already_recorded`, no new object/receipt.
   Send an identical synthetic file with another name: expect `duplicate`, a new
   provenance receipt and the same object. Restart the command process and repeat.
5. During a synthetic transfer, run intake: unfinished Syncthing temporary files
   must be ignored, never archived. An ordinary file still open for writing is
   refused on Windows. Finish transfer, wait, rerun. Unsupported `.exe` and nested
   content must remain unprocessed with clear reports. Compare only synthetic
   memory sentinels if demonstrating memory isolation; do not open live records.
6. Save exact draft SHA, Python/Windows versions, command, reports and synthetic
   source/archive hashes as demonstration evidence. Stop after verification.
   No watcher, background service, memory promotion, merge or runtime activation
   follows from a successful demonstration.

## Limits

Completion is inferred from the transport's final filename, quiet interval and
Windows sharing checks; there is no Syncthing API/protocol integration. A paused,
closed writer can resume later, producing a separately archived observed version.
This does not certify the phone's final intended content. No recursive intake,
automatic content parsing, memory promotion, device authentication, deduplication
of semantically similar content, archive garbage collection, or quota manager.

Trusted local operator ownership of inbox/archive parents is required. Checks
reject observed links/reparse points; they are not a sandbox against a malicious
same-user process swapping parent directories or editing archive metadata. OS
locks serialize cooperating commands only. SHA-256 verifies consistency, not
authenticity. Physical power loss, Windows directory fsync, network/removable
filesystem semantics, malicious concurrent archive writers and POSIX execution
are not certified by the Windows results. Disk-full/permission behavior is tested
through deterministic injection; a physical exhausted volume is not tested.
Real Windows symlink creation requires privileges unavailable in this account;
that one test skips, while simulated symlink mode, reparse and real junction tests
run. No permissions were changed to bypass that limitation. A real Android
Syncthing transfer and independent exact-SHA review remain later verification.
