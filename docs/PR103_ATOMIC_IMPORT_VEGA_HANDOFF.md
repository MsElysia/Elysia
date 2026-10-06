# PR #103 serialized, recoverable apply — Vega handoff

2026-10-06. IMPLEMENTED / DRAFT CHILD / independent Vega review pending.
Branch: `codex/issue95-atomic-import-20261006`.
Exact immediate parent: `53770acf3d51b0b76f70922d70b7d1adc691c761`.
Final SHA: the commit containing this handoff, pinned in its draft PR body.
Neither PR #101 nor PR #107 was merged, copied or restacked into this work.

## Reproduced parent failures

On a detached exact-parent checkout, the deterministic overlap regression fails
with `DID NOT RAISE ChatGPTExportIngestError`: a second interpreter's apply is
not refused while the first interpreter is paused after reading known IDs.
The original PR's separate failure probes were also reproduced:

- Failure on the original-export raw-source write leaves one derived raw file,
  zero intelligence records, and no candidate queue.
- Partial intelligence JSON write leaves two raw files, one truncated JSON
  record, and no queue; recall rejects the malformed record.
- Candidate staging failure leaves one published intelligence record and no
  queue. The failed operation has therefore already published logical memory.

Saved serialization reports were read in full. The POSIX directory-lock design
and the exact Boolean apply guard were reused from their patches; no unrelated
lineage or local commit was imported. Existing `memory_vector._atomic_write_json`
and `file_writer` replacement patterns were inspected. Those are single-file
mechanisms associated with different owners/runtime dependencies, not a
multi-artifact import transaction. This slice uses the same fsync/replace pattern
locally, with one small apply-specific journal; no new memory schema or store.

## Repair protocol

1. Reject non-Boolean apply flags before I/O. Resolve one preview/destination.
2. Acquire a nonblocking OS directory lock; recover any abandoned transaction
   before validation, known-ID reads or writes. Reentry by an apply is rejected;
   nested readers use the already-held lock in the same thread/process.
3. Stage extracted text, metadata, derived/original raw bytes, intelligence JSON,
   the complete candidate queue and apply reports under a private transaction
   directory. Existing public artifact paths and source-linked data stay unchanged.
   Corrupt/unreadable/duplicate-ID existing queues refuse new apply.
4. Fsync staged bytes and backups. Atomically install and fsync the recovery
   manifest before replacing any public file. Preserve old bytes for every
   overwritten target. Each replacement is atomic; parent directories are synced.
5. Only after all replacements, atomically install the committed marker. Before
   that point exceptions/death cause rollback; after it the entire result survives.
6. Rollback restores old bytes by atomic replacement and removes new files.
   Backups are retained until rollback finishes, so interrupted recovery is
   repeatable. Rename the resolved journal to a cleanup namespace before removing
   backups, so death during cleanup cannot resemble an unfinished publication.

`load_memory_intelligence_records`, query and raw/context expansion hold the
same lock over their complete reads. Candidate-ID reads and review-queue reads
also recover under that lock. Readers refuse while another worker holds it;
after process death the first cooperating read restores old state or retains a
complete committed result before returning. Recovery failure leaves the journal
and blocks both readers and apply instead of exposing partial memory.

This is recoverable logical publication, not one atomic rename of the entire
destination. A direct filesystem observer that bypasses these APIs can see
individual replacements and journal files. No such observer is certified.

## Changed files

- `project_guardian/local_ingestion/apply_transaction.py`
- `project_guardian/local_ingestion/chatgpt_export_ingest.py`
- `project_guardian/local_ingestion/memory_intelligence.py`
- `project_guardian/local_ingestion/memory_candidates.py`
- `project_guardian/local_ingestion/memory_candidate_review.py`
- `project_guardian/tests/test_chatgpt_export_ingest.py`
- `project_guardian/tests/test_chatgpt_apply_transaction.py`
- `scripts/run_safe_stack_smoke_tests.py`
- This handoff.

## Verification and exact-candidate review instructions

Python 3.12.14 / pytest 9.1.1. Synthetic disposable destinations only.
The new transaction file contains 36 cases, including:

- Two real subprocesses with empty and preexisting destinations: worker A pauses
  at the previous known-ID race point; worker B attempts the identical source,
  refuses without writes, then retries after A completes. Exactly one queue row,
  one unique candidate ID and one intelligence record; valid source expansion.
- Partial temporary writes/failures during extracted, rendered/raw, original/raw,
  intelligence JSON, queue, report, manifest and final replacement boundaries,
  with both empty and preexisting destinations. Old file bytes restored; retry
  completes without duplicate rows or records.
- SIGKILL during staging, after four public replacements, during rollback, after
  commit marking and during cleanup, with both empty and existing destinations.
  A concurrent recall refuses during the held lock. Public record loading after
  death recovers the exact prior file bytes or the full committed result.
- Recovery storage failure and malformed journal fail closed; repaired storage
  allows recovery and retry. External-session output is refused before publication.

Retained regressions cover original raw bytes, forged-link rejection, same-size
edit rejection, serial intelligence byte stability, canonical/candidate tags,
approved-memory store/search/context, Brain preview, and NumPy-absent production
ingestion. The Safe Stack includes this new transaction test file explicitly.
The draft PR records final focused/Safe Stack/hosted counts and exact SHA.

Vega: detach the published SHA; run `python -m pytest -q
project_guardian/tests/test_chatgpt_apply_transaction.py
project_guardian/tests/test_chatgpt_export_ingest.py
project_guardian/tests/test_memory_intelligence_ingestion.py
project_guardian/tests/test_memory_intelligence_brain_bridge.py
project_guardian/tests/test_approved_memory_store.py
project_guardian/tests/test_approved_memory_search.py
project_guardian/tests/test_approved_memory_context.py
project_guardian/tests/test_local_memory_pipeline_smoke.py
project_guardian/tests/test_memory_candidate_review.py`, then
`python scripts/run_safe_stack_smoke_tests.py`. Attack every replacement index,
commit-marker/cleanup boundaries, death during rollback, reader refusal/recovery,
canonical destination aliases, bad journals, and malformed apply flags. Do not
transfer previous SHA verdicts; report newly discovered failures before PASS.

## Limits and retained boundaries

POSIX `flock` on a stable existing destination directory only; unsupported
platforms including Windows refuse apply. The advisory lock covers cooperating
ChatGPT apply and named recall/queue reader APIs. Other ingestion formats, direct
primitive calls, external filesystem writers, destination inode replacement,
network filesystems and malicious modification of private journal data are not
certified. Files and directories are fsynced, but physical power-loss/hardware
durability and large-export performance remain unproven. Full queue replacement
and artifact backups add temporary disk/I/O cost. Empty directories may remain
after rollback; no incomplete memory files are returned by cooperating readers.

All transactional apply outputs must be under the destination. A preview stored
outside it may be used for dry-run, but apply refuses its external session outputs
before publication. Normal preview sessions already live under the destination.
Readers can return a retryable lock refusal while apply/recovery is active; this
does not promise wait-free old/new reads. Recall may perform journal recovery;
it does not approve candidates or promote memory. Cleanup failure after the
commit marker can produce an uncertain caller result with a complete committed
state; serial retry detects existing candidates and recovers cleanup.

No runtime/provider/autonomy activation, approved-memory promotion, TaskLedger
or executor wiring, credentials/permissions/settings changes, merge, deployment,
gate release, evidence deletion, or integration with #101/#107. PR #103 itself
remains unchanged, draft and unmerged. No live/user memory was used. Usage/credit
telemetry was unavailable; no balance was guessed and no credits purchased.

Scope-qualified success claim to falsify:
“Two concurrent memory-import workers cannot create duplicate logical memory
artifacts, and an interrupted apply cannot expose a partially published memory
state.” This applies to the cooperating POSIX ChatGPT apply/reader APIs above.
