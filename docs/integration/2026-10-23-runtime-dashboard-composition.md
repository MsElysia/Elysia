# Elysia restricted runtime + dashboard: draft composition record (2026-10-23)

**STATE: SOURCE-COMPOSED / NOT RUNTIME-VERIFIED / NOT READY FOR MERGE.**

Control plane: Issues #11 and #112. Deliverable: Issue #139. This branch is a reversible, draft-only composition to be tested and independently reviewed, **not** a completed end-to-end application.

## Exact provenance
- Starting commit: PR #125 `e5ce90572a17041cf57657258ec4c9d2f54558f0`, tree `409d4d335b8aca3486ffb1f182fdddf56cd9d9f7` (restricted native-Windows fictional CLI).
- Dashboard source: Cursor `cursor/dashboard-ui-acceptance-2389` exact `5268c66af8780008a8dea75eb595a9ef9e84cda1`; the eight files below are copied as exact Git blobs, not cherry-picked from its unreviewed history.
- Tonight's reported Codex repair/test commit `428626d7fd7c08f8e75ef922755bcfd4320d2bc7` is **NOT PRESENT** on connected GitHub at composition time and is **NOT** included. Obtain and independently compare this exact local commit before claiming its new recovery regression is part of the composed candidate. Do not silently substitute any other SHA.
- The original sources, other draft branches and `main` are untouched. No historical archives, screenshots or report evidence were ported.

## Scoped dashboard blobs from Cursor
- `project_guardian/module_activity.py` @ `7795b83ac5f4482deec10700980f482a11c9cb54`
- `project_guardian/planner_readiness.py` @ `9503d58bdf3eab898580bbf89df1d400dd0de1be`
- `project_guardian/ui_control_panel.py` @ `f5e378c1119a6dc6c654c8fea74bee0ee7198682`
- `tests/dashboard_panel_loader.py` @ `3c2bfa3cb18f4b553d5faa56fd87a1dd82c7344f`
- `tests/test_dashboard_idempotent.py` @ `c69fe5dce900263495bf367d65e42d5ddc4f3fee`
- `tests/test_dashboard_listening.py` @ `e963a745ead43f5568d8e4b0eeb0d40f01e454c6`
- `tests/test_dashboard_status_truth.py` @ `45a39af83045066cc4baf84f7ecbc9cac0041818`
- `tests/test_project_guardian_import.py` @ `aa8f94d33f8b7809a57efabc5e2f349554d56a42`

The restricted CLI starts before legacy Guardian/provider/UI imports. Cursor's UI is a **separate** Flask/GuardianCore path. Putting both sets of files in one tree does not connect these paths. Do not route synthetic memory to the unrestricted `start_ui_panel.py` to manufacture a passing demo. A separately reviewed, explicit restricted UI bridge/entry point may be needed.

## Acceptance and follow-up
1. Verify this exact new composite SHA/tree and the eight copied blob SHAs; diff must contain only this scope plus this manifest versus PR #125. Check for unexpected changes and sensitive material before publishing further.
2. Run existing restricted offline native Windows suite: `python -B scripts/run_windows_offline_tests.py`; preserve its disabled-network/providers/autonomy policy and native restart/recovery tests.
3. In an isolated disposable environment with appropriate installed dependencies run `python -m pytest tests/test_dashboard_status_truth.py tests/test_dashboard_listening.py tests/test_dashboard_idempotent.py tests/test_project_guardian_import.py -q`. Report missing packages/skips and do not count skipped import tests as PASS. Review all 8 copied paths for collisions with PR #125 and other existing drafts.
4. Test the normal Windows launcher as a genuine fresh-process fictional teach/correct/history/rephrased-recall/restart/recovery workflow. Verify no real-data access, provider activation, network calls, duplicate writes or changed protected gates.
5. Before claiming **combined-app** PASS, prove a supported browser entry point can execute the same bounded fictional task and recall its result through the same authorized local store after restart. Verify online/offline status and errors. Do NOT claim that Cursor's fictional echo backend proves this; it does not.
6. Request independent exact-SHA composed review, reconcile the missing Codex test commit, and address any integration defects on a new reviewed draft SHA. Stop at READY_FOR_MERGE_REVIEW if all required checks pass; never merge automatically.

No credentials, external API, paid model, live provider, autonomous schedule, production activation, protected-gate edits, or archive mutation are authorized.


## Isolated hosted dashboard acceptance job
A separate Windows CI job was added to the existing restricted-pilot workflow **without modifying or relaxing its original job**. It installs isolated test dependencies and executes the four copied dashboard/package test modules at the same exact PR head. Successful tests prove tested UI import/status behaviors, NOT a live GuardianCore startup, Ollama availability, or an end-to-end browser-to-restricted-memory workflow. Treat all skipped import tests and runtime prerequisites explicitly. Original user data, live services and network model providers are outside the test scope.
