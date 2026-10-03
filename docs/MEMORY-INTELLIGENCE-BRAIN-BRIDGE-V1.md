# Read-only Memory Intelligence -> Brain/TDA Retrieval Bridge v1

Task: Issue #95 follow-up selected by Issue #11 checkpoint correction
`5970432215` (2026-10-03). This is an isolated local implementation, not a
governance release or integration of the other runtime branches.

Base: PR #97 exact `9c35991715eb4160e346ecda286ef73a0ffd7577`.
Branch: `codex/issue95-readonly-brain-bridge`.

## Behavior and scope

`ReadOnlyMemoryIntelligenceBridge` wraps the existing ingestion destination and
query/expansion implementation. It does not create a database or write method.
The explicitly opted-in `BrainPipeline(read_only_retrieval=bridge)` uses the
normal context/planner/tool-route/risk/TDA stages with a fixed dry-run context,
no Guardian, no injected module/executor hooks, offline routing and no trace,
learning or self-improvement persistence. Ordinary Brain callers retain their
existing behavior. Global configuration and startup paths remain unchanged.

The existing heuristic planner remains heuristic. The bridge adds a descriptive
evidence-review step to the plan, with source/chunk/highlight IDs and validated
recall reasons. The unified export records this exact plan effect. TDA receives
the same chunk IDs through its existing `relevant_context_ids` field. This
proves evidence-review reachability; it does not prove improved reasoning,
adaptive ranking, semantic interpretation of recalled text, or TDA action
selection based on recalled content. No recalled text becomes a capability,
executable command, permission or approval.

Strict summary validation is explicitly enabled only by this bridge. A persisted
summary must equal the deterministic summary of its validated source chunk
before it can influence recall or appear as evidence. The default query behavior
outside this lane is preserved. All failed retrievals clear prior recall.
Expansion re-queries and validates provenance before returning one currently
recalled highlight, surrounding context and the complete raw source.

## Non-test caller

`scripts/preview_memory_intelligence_brain.py` invokes the existing Brain/TDA
pipeline through `run_memory_intelligence_preview`. It requires an explicit
existing ingestion destination; it does not load operator memory or activate a
runtime. Use an already populated disposable profile for verification:

```sh
python scripts/preview_memory_intelligence_brain.py \
  --dest-dir /path/to/disposable-profile --query "drywall quote"
```

Optional `--expand-highlight ID` explicitly includes raw source in the JSON
printed to stdout. The default output contains highlights/context and source
references. No output file is written. Malformed provenance exits with code 2
and emits no successful JSON export. Returned memories are evidence, not proof
of human authorization; these Python objects are not credentials or trust tokens.

## Required verification

Run the committed bridge tests and related existing suites:

```sh
python -m pytest -q \
  project_guardian/tests/test_memory_intelligence_brain_bridge.py \
  project_guardian/tests/test_memory_intelligence_ingestion.py \
  project_guardian/tests/test_brain_tda_integration.py \
  project_guardian/tests/test_brain_pipeline.py \
  tests/test_project_guardian_optional_numpy.py
python scripts/run_safe_stack_smoke_tests.py
```

The bridge suite is mandatory in Safe Stack. It covers real ChatGPT preview/apply
to the non-test CLI, restart equivalence, byte-exact raw expansion, NumPy-blocked
package/CLI reachability, malformed tags/source offsets/raw data, forged summary,
stale-evidence clearing, rejected execution/persistence contexts, recalled prompt
injection, and unchanged destination bytes/files after preview. Trace IDs and
timestamps are intentionally fresh; deterministic recall and plan evidence are
compared across fresh processes instead of requiring identical whole traces.

## Remaining handoff and gates

After local tests and code review, report the exact resulting product SHA, files,
base ancestry, test counts and limitations. Fresh independent Vega falsification
and exact-head hosted CI remain required for that new SHA. PR #97's PASS does not
transfer. Local independent code review is not Vega verification.

Keep #29/#30/#31/#33 human-governance gates active and #23/#36/#37 semantics
frozen. Keep #39 CI evidence and #40/#43 exact-SHA/checkpoint rules scoped to
their own contracts. The #98 governance-storage lane remains separate. No
TaskLedger/executor wiring, trusted-authentication claim, combined-runtime
integration, live-memory mutation, provider/autonomy activation, merge,
deployment, permission expansion, GitHub posting or governance release is
included in this task.
