# Candidate and installed-Windows acceptance packet

Never substitute operational data for the disposable root in a development run.
Read REPORT.md for source identities, known limits and rollback. Record exact
`git rev-parse HEAD`, runtime identity, dependency versions, timestamp and evidence
for each run. A dirty launcher reports modified and is not exact-SHA proof.

## Disposable candidate setup (PowerShell)

```powershell
$candidate = 'C:\Users\Owner\Project guardian\.worktrees\windows-chat-documents-20261101'
$env:ELYSIA_PILOT_DATA_ROOT = 'C:\Users\Owner\Project guardian\tmp\windows-ui-mission-runtime'
$env:ELYSIA_PREFERRED_UI_PORT = '5080'
$env:ELYSIA_PILOT_PYTHON = 'C:\Users\Owner\Project guardian\tmp\windows-ui-mission-venv\Scripts\python.exe'
$env:ELYSIA_SYNC_ON_LAUNCH = '0'
$env:ELYSIA_LOCAL_MODEL = 'llama3.2:3b' # use an actually installed local model
Set-Location -LiteralPath $candidate
cmd /c pilot\START_ELYSIA_VERIFIED_PILOT.bat
```

The BAT launches the same product through launch_verified_pilot.py. It must
publish readiness and identify the exact candidate source, data root and process.
It must not attach to an unknown listener. Use the matching stop tool with the
same environment; mismatched interpreter ownership must fail closed.

For extraction dependencies in a disposable environment only:
`python -m pip install -r requirements.txt -r requirements-documents.txt flask-socketio requests openai pyttsx3 reportlab`.
Do not install into the existing release environment during development.

## Scenarios and evidence to capture

| # | Scenario | Required observation |
|---|---|---|
| 1 | Normal launch | Run the candidate BAT above; verify readiness/loopback identity. Actual installed shortcut and release BAT are a separate post-approval test. |
| 2 | Chat homepage | Chat is active on load; message field, Send and conversation controls visible. |
| 3 | Local model | A real response from the named installed model. Disconnect/unavailable paths must show failure; never silently use cloud. |
| 4 | Continuity | Send directly without Start new. Both roles appear in history. Stop/restart and Resume the saved identity; no grants inherited. |
| 5 | Text import | Select synthetic TXT; preview readable content; Save to memory; completed receipt and preserved byte hash. |
| 6 | PDF import | Repeat with synthetic text-based PDF, observing page/location and source reference. |
| 7 | Chunking | Inspect deterministic document-v1 chunk IDs, offsets, content hash and source_id in disposable memory. Same bytes/settings give same IDs. |
| 8 | Retrieval | Search exact phrases and reworded questions retaining document keywords; verify source/chunk metadata. No semantic embedding claim. |
| 9 | Grounding | Ask PDF departure date; compare answer to PDF (19 November 2026) and inspect host-rendered filename/page/chunk evidence. |
| 10 | Dedupe | Reimport exact original bytes; Already indexed; no new document_chunk records for that hash. Changed PDF bytes are a distinct version. |
| 11 | Restart | Stop and BAT restart; sources, chunks, history and assistant source references remain accessible. |
| 12 | Controls | Chat/new/resume/checkpoint/files/preview/save/cancel/search/refresh/navigation show results or errors. Consult controls.csv; separately audit all legacy Advanced controls before claiming completion. |
| 13 | Activity | Actual initialization/model/import/retrieval/resume/failure events; idle when no active jobs; interrupted receipt distinguished from an active worker. No private content in event feed. |
| 14 | Recovery | Malformed, empty, encrypted or unsupported file must fail visibly. Inject interrupted indexing with unit test; retry does not duplicate partial chunks. Originals and prior memory survive. |
| 15 | Security | Missing upload token and non-loopback clients denied. Embedded document commands cannot grant scopes; cloud/autonomy remain refused. Existing restricted tests must pass. |
| 16 | Preservation | Check original release identity/shortcut/data boundaries and existing intel regressions. No replace/merge/deploy without approval. |

## Reproducible HTTP and regression checks

```powershell
& $env:ELYSIA_PILOT_PYTHON -B scripts/accept_windows_documents_http.py --evidence-root 'C:\Users\Owner\Project guardian\tmp\windows-ui-mission-evidence'
# Stop/restart using the SAME root and interpreter, then:
& $env:ELYSIA_PILOT_PYTHON -B scripts/accept_windows_documents_http.py --evidence-root 'C:\Users\Owner\Project guardian\tmp\windows-ui-mission-evidence' --verify-restart
$env:PYTHONPATH = 'ci_stubs'
& $env:ELYSIA_PILOT_PYTHON -B scripts/run_windows_intel_rc_tests.py
```

The HTTP script is a live acceptance test, not a model mock. It uses synthetic
fixtures, disables requests proxy inheritance, never prints dashboard tokens,
and refuses nonliteral loopback URLs. The unit tests separately inject failures
and mocked model replies; they are not proof of real model execution. Hosted
Linux/Windows CI runs the regression slice, not the installed Windows shortcut.

## Deployment approval boundary

Present exact draft SHA, passing checks, source backup/dependency plan and this
packet for approval. Only after approval replace release source and correct the
shortcut. Repeat all 16 scenarios against the installed environment, using new
synthetic documents without deleting personal memory. Record installed source
identity and distinguish failures/incomplete scenarios from operational success.
