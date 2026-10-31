# MemoryCore persistence repair (Issue162)

Exact base: 11691e2f62913f1f8a7c09523cf4f74751311324, parent 722d8e4fe85d7e42ac34066c2d651849d15e734c. Separate from PR170/Issue171. Reuses MemoryCore and its persistence regression suite.

Before repair, added quarantine-failure and failed-primary-with-eviction regressions fail on unchanged historical production (2 failed, 1 retry test passed). Quarantine failure followed by remember returned True and overwrote original corrupt bytes; failed persistence retained staged memory.

After repair: failed corrupt-history preservation fences every _save until an explicit successful load/preservation. Quarantine bytes are compared before clearing the fence. Remember serializes append/eviction/commit with the existing lock made reentrant, restores the previous list after primary failure, and returns before timeline/vector side effects. Optional mirror failure after a confirmed primary commit does not cause a false primary failure/retry. Existing source and interfaces preserved.

Native Windows focused suite: 16 passed, zero failed/skipped. Disposable synthetic stores only. Tests cover corrupted history, injected move/write failures, false move success, eviction rollback, vector/timeline non-publication, retry, primary-before-secondary ordering, restart consistency, optional mirror failure and successful recovery. Secondary adapters use recording doubles; primary JSON writes/reloads are real. No actual vector model, USB device, or personal memory is accessed. Multi-process writers, fully atomic cross-store publication and release-level durability are outside this bounded repair.

Command: python -B -m pytest --noconftest -q -rs -p no:cacheprovider tests/test_memory_core_persistence.py

Rollback: close/abandon this additive branch; original historical source, main and Issue171 child remain intact. If separately imported, revert only this repair commit. Never copy test state into operational memory. Recovery for synthetic corrupt state: remove injected fault and explicitly call load() to retry verified quarantine, then remember(). Never clear persistence_blocked manually.

Draft/unmerged. Independent exact-head review required; no READY_FOR_MERGE_REVIEW or release claim.
