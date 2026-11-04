# Canonical retrieval reconciliation — 2026-11-04

Scope: isolated draft integration; no release promotion or operational-data access.

## Rechecked inputs

- Canonical: `integration/windows-canonical`, `54b6c2604029fa630a0616584dbc1ee59ba6385f`.
- Draft #200: `6869aad00038dedfce3316c2ed29d714cb7959c7`.
- Draft #203: `c9d69d0cd65c3ff27ae1214039ec0011661834cf`.
- Test-only integration baseline: `8d56270a88ba1de99056db324ed070b115e15e8c`.
- One draft PR: https://github.com/MsElysia/Elysia/pull/204.

## Reconciliation decisions

Canonical and both drafts share rarity-weighted lexical ranking, current snapshot
facts, fact-first ties, four evidence slots and a 10,000-byte serialized evidence
cap. Canonical independently added Unicode tokenization, tail windows, diagnostic
filtering and an independent review suite. Those remain present.

Port #200's original-source hash preservation and separate excerpt checksum;
canonical had overwritten the original hash when shrinking evidence. Correct the
canonical assertion that endorsed that overwrite. Source ID, chunk ID, revision,
highlight ID, filename and page are retained. Window scoring uses the same Unicode
casefold and finite alias normalization as ranking, on original-text windows;
casefold expansion cannot shift offsets in the original text.

Port #203's deterministic relevance/diversity selection, keeping its 0.65 overlap
penalty and original deterministic ties. Candidates are neither merged nor
rewritten. Promote canonical duplicate-pressure xfail to an ordinary regression;
keep its lexical-semantic limitation as a strict expected failure. Test both
short conflicts and long near-identical disagreements under duplicate pressure.

Port the shared finite vocabulary into both context selection and DocumentLibrary
search, including proper-name hard negatives. Keep the standalone extractor import
path working. Do not substitute the draft's ASCII-only context tokenizer.

The real FAISS regressions expose a required preservation dependency absent from
canonical: JSON-first transactional cleanup, primary-history read authority,
checksum-bound vector generations, restart validation and fencing of failed or
stale vector writes. Port the existing tested memory_cleanup/memory_vector changes
as a unit. Do not port unrelated registry persistence or Windows sync changes.
No cleanup or index rebuild is run against operator data by this task.

Retain the canonical RC manifest; add retrieval vocabulary and both cleanup suites.
Add the drafts' read-only, exact-head Windows/Ubuntu FAISS and large-document
workflows. Existing gates and the two symlink exclusions are unchanged.

## Behavioral evidence

Test-only baseline on both hosted operating systems:

- RC: Windows 67 failed / 262 passed / 2 deselected / 1 xfailed;
  Ubuntu 67 failed / 261 passed / 1 Windows-only skip / 2 deselected / 1 xfailed.
  https://github.com/MsElysia/Elysia/actions/runs/41929355381
- Real offline FAISS: 16 failed on each OS, exercising actual native FAISS,
  not mocks or skips. https://github.com/MsElysia/Elysia/actions/runs/41929356106
- Large-document baseline: see
  https://github.com/MsElysia/Elysia/actions/runs/41929355337

Local integrated implementation (Windows Python 3.13.15):

- Focused retrieval/vocabulary/cleanup: 163 passed, 1 strict expected semantic miss.
- Complete relevant RC manifest: 328 passed, 1 NTFS-junction privilege skip,
  2 existing symlink exclusions, 1 strict expected semantic miss.
- Real FAISS 1.15.1 / NumPy 2.5.4: 16 passed; sockets blocked by test fixture,
  deterministic NumPy embeddings, disposable JSON/index/metadata/manifest files.
- Real large-document worker/ingestion/restart: 7 passed, including >500k and
  multi-million-character sources and preservation of uploaded bytes.
- Changed-file secret scan: no findings. Diff whitespace check passed.

Exact final SHA and hosted results are recorded in the PR description after all
three workflows complete; that avoids a self-referential evidence commit.

## Limitations and risks

These tests score evidence selection and preservation, not model answers or truth.
The finite vocabulary is not general semantic retrieval; doctor/physician remains
a documented expected miss. Unicode examples do not certify all languages or
segmentation. Diversity is a heuristic and can trade redundant corroboration for
less relevant material. Four slots and byte caps cannot preserve every conflict;
excerpts are lossy. Diagnostic exclusion needs explicit labels; unlabeled logs are
not classified automatically. Document search still has its existing top-six gate.

Persisted legacy FAISS pairs without generation manifests are preserved and fenced,
not silently blessed. An explicit rebuild from authoritative JSON is required;
this task does not migrate installed data. Generation verification is not a
multi-process locking or secure-deletion guarantee. Local tests used Python 3.13;
hosted workflows use Python 3.12. Native installed BAT/browser/process identity,
restart and operator-local backup/restore acceptance remain unperformed.

## Rollback and next acceptance step

Before merge: close draft #204 and discard its isolated branch. Canonical and the
installed release have not been changed. If this code is later adopted, revert
this PR's code commits through review; do not copy repository memory over live
history. Keep primary JSON and source bytes; vector artifacts are derived and
must be rebuilt only from verified authoritative JSON, never stale metadata.

Smallest native-Windows next step: use the exact reviewed SHA in a disposable,
isolated application checkout with synthetic data, verify launcher/browser/process
source identity, restart, correction citations, a tail excerpt and backup/restore.
Do not promote or point the installed launcher at the draft as part of that test.
