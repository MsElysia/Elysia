# Windows memory import / process-death recovery

2026-10-09. IMPLEMENTED DRAFT CANDIDATE; native Windows CI and independent
exact-SHA review required before a Windows capability PASS.

Direct isolated child of PR #108 exact
`931576224432b6db6f4290eee0ea4c0aa9bd9c73` (tree
`ab770336e69614ecd3ad5eea06c01ac3c9093aa3`). Branch:
`codex/windows-memory-import-20261009`. The draft PR pins the published SHA,
exact-head jobs and final evidence; prior PR acceptance does not transfer.
No other runtime lineage is combined. Issue #11 remains the control plane;
this engineering task neither queues nor commands RECRUIT through Issue #109.

## Objective and ADOPT / ADAPT / BUILD decision

Safely run the existing ChatGPT export apply and participating recall/queue
readers on Nate's Windows computer: overlapping workers refuse without writes,
retry creates one candidate, and process death yields exact prior bytes or one
complete committed result before a reader returns.

ADAPT the existing transaction journal; ADOPT the Windows OS mutex primitive
through Python's standard `ctypes`. No third-party locking package, new store,
schema, lock file, provider call, paid model or background task. External source
material was treated as design documentation, not executable recruited code.
POSIX `flock` remains the same backend. A persistent sidecar lock file was
rejected because first-use lock creation would change destination bytes even
when apply is refused. A new database would exceed this bounded repair.

Primary references inspected:
- https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-createmutexw
- https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject
- https://learn.microsoft.com/en-us/windows/win32/termserv/kernel-object-namespaces
- https://docs.python.org/3/library/os.html

## Protocol

Windows creates/opens a non-inheritable `Global\\Elysia.ChatGPTApply.v1.<hash>`
mutex with the default ACL. The hash derives from the resolved destination's
device/file identity, not path spelling, user or session. Unavailable/zero file
identity refuses. No ACL, privilege, credential or permission changes are made.
The OS mutex coordinates cooperating threads/processes on the same machine;
access denial, timeout, failed/unknown waits and unavailable APIs refuse before
recovery/publication. There is no unlocked fallback, including for readers of
an existing destination.

`WaitForSingleObject(handle, 0)` returns immediately. Both ownership and
abandoned ownership enter the existing journal recovery before serving bytes.
Nested reads reuse same-thread ownership; nested applies, including identity
aliases, refuse. Release and handle closure run on normal return, body error
and recovery error; cleanup failures are reported. OS process termination
releases ownership. Recovery runs on every acquired lock, not only when the
kernel reports abandonment, since the last handle may have vanished at death.

Windows file bytes are flushed/fsynced before replacement. POSIX directory
fsync is retained; Windows directory sync is explicitly a no-op because
`os.open/fsync` has no equivalent directory contract there. This change claims
process-death recovery, NOT power-loss durability. The existing stage/backups,
manifest-before-publication, commit marker, repeatable rollback and cleanup
namespace are unchanged. Windows journal targets additionally reject device
names, alternate streams, drive-relative paths, traversal, control characters,
trailing-dot/space aliases and case aliases of the private journal namespaces.

## Evidence and required review

Local Linux / CPython 3.12.3 / pytest 9.1.1, disposable synthetic exports only:
- Initial focused slice: 103 passed, 1 native Windows test skipped.
- Memory + config/script slice: 251 passed, 1 native test skipped.
- Safe Stack: 668 passed, 1 native test skipped.
An additional native exact-parent differential was then added. Its skip/count
and final published-tree rerun are recorded in the PR; no native PASS is inferred
from the Linux counts or mocked API tests.

The shared transaction suite now runs on both POSIX and Windows: two real
processes collide at the known-ID boundary with empty/existing destinations;
partial writes and publication exceptions restore old bytes; killed workers
during staging/publication/rollback/commit/cleanup cannot serve partial state;
queue/recall readers refuse during contention and recover on reentry. Source
bytes, original expansion, tag behavior, no models/embeddings/live memory and
idempotent replay remain covered by the inherited memory tests.

`test_windows_apply_lock.py` covers mocked API refusal and resource-lifetime
contracts on every platform. Its native tests compare the exact parent Windows
refusal with successful current apply, and prove real case-alias contention plus
`WAIT_ABANDONED` recovery with an unowned watcher handle retained across death.
An additional thread-contention test exercises the actual OS backend.

The existing Safe Stack workflow gains a Windows memory job using Python 3.11,
exact event-head checkout/assertion and read-only workflow permissions. Full
history is available there solely for the exact-parent differential. The Linux
job remains. Both jobs use offline product tests; dependency installation is CI
setup. No runtime, server, executor or autonomy is started.

Independent verifier: detach the published SHA and run the workflow's full
memory slice plus `python scripts/run_safe_stack_smoke_tests.py`. On Windows,
neither native test may skip. Attack directory identity aliases, multiple threads,
process kills before/after each replacement, real API access denial and recovery
storage failure. Check exact previous bytes/full committed state and no duplicate
candidate/record, including original-byte expansion after restart. Publish a
bounded exact-SHA verdict; do not inherit PR #108's PASS.

## Limits and authority

Local filesystem, cooperating ChatGPT apply and named queue/recall readers only.
Mapped-drive/junction/short-name and cross-session identity behavior beyond
tested aliases, cross-user ACLs, network/shared filesystems, reparse attacks,
destination replacement and noncooperating writers remain uncertified. Kernel
mutex precreation can deny access; this is a refusal, not a new trust authority.
Default ACLs are never broadened to solve access failures. Physical power loss,
hardware durability, large exports, other ingestion formats/direct writers and
the inherited cleanup-storage rough edge remain unproven/outside this slice.
New empty directories may remain after rollback. Post-commit cleanup failure
can leave an uncertain caller result with a complete committed journal; retry
recovers it and detects existing candidates. This is not filesystem-wide atomic
visibility for raw observers.

Draft/unmerged only. No merge, deployment, runtime/provider/autonomy activation,
live/user memory mutation, approved-memory promotion, TaskLedger/executor
wiring, credentials, permission/settings expansion or governance release. No
paid model invocation or credit purchase. Usage/credit telemetry is unavailable.
