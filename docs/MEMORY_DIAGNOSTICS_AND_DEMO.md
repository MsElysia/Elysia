# Memory Diagnostics and Demo Workspace

This guide covers the local-only diagnostics and demo workspace commands for Elysia memory work.

The commands here do not enable autonomy, do not use live execution, do not call models or embeddings, do not access accounts, and do not write live runtime memory or a vector database. All writes, when requested, stay inside the operator-provided demo destination.

## Memory Doctor

Run a read-only inspection of a local memory workspace:

```powershell
python scripts/memory_doctor.py --dest-dir .\tmp\memory-demo
python scripts/memory_doctor.py --dest-dir .\tmp\memory-demo --json
```

The doctor reports known local-memory artifact counts:

- import sessions
- ChatGPT export import sessions
- email export import sessions
- pending review candidates
- review decisions
- approved and rejected decisions
- approved export presence
- approved memory store presence and readable record count
- context bundle presence

Verdicts are intentionally simple:

- `EMPTY_WORKSPACE`
- `READY_FOR_IMPORT`
- `HAS_PENDING_REVIEW`
- `HAS_APPROVED_MEMORY`
- `HAS_CONTEXT_BUNDLE`
- `NEEDS_ATTENTION`

Malformed optional JSONL files are reported as warnings instead of crashing the command.

## Demo Workspace

Preview the files that would be created:

```powershell
python scripts/create_memory_demo_workspace.py --dest-dir .\tmp\memory-demo
```

Create fake sample inputs:

```powershell
python scripts/create_memory_demo_workspace.py --dest-dir .\tmp\memory-demo --apply
```

Create fake sample inputs and run the local pipeline on them:

```powershell
python scripts/create_memory_demo_workspace.py --dest-dir .\tmp\memory-demo --apply --run-pipeline
```

The demo generator writes only under `--dest-dir` and rejects dangerous destinations such as the filesystem root, the home directory itself, and the repository root itself.

The sample data is fake:

- a transcription text file
- a ChatGPT-style `conversations.json`
- an email `.eml`
- a README explaining the workspace

The optional pipeline run uses the existing local preview, apply, review, export, store, search, and context bundle functions on that fake data only.

## Health Smoke

Run the end-to-end diagnostics/demo smoke:

```powershell
python scripts/run_memory_health_smoke.py --json
python scripts/run_memory_health_smoke.py --json --keep-temp
```

The smoke creates a temporary demo workspace, runs the fake-data pipeline, runs memory doctor, checks pending/approved/search/context behavior, and removes the temporary workspace unless `--keep-temp` is supplied.

Expected safety flags remain false:

- `model_called`
- `embeddings_used`
- `live_memory_written`
- `autonomy_enabled`

## Static Page

The static diagnostics page at `project_guardian/ui/static/memory_diagnostics.html` is documentation-only. It has no scripts, no external assets, no fetch/XHR/WebSocket calls, and no backend route links.
