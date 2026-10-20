# Elysia dashboard startup verification — 2026-10-20

## Baselines and scope

- Original Windows checkout: `0760798bc3ecb036c92fca456670c67e901c7ed7`.
- Original repair branch: `codex/elysia-ui-readiness`, in a separate managed worktree.
- Publishable draft baseline: remote `main`, `722d8e4fe85d7e42ac34066c2d651849d15e734c`.
- Publishable branch: `codex/elysia-ui-windows-verification`, in a second isolated worktree.
- The original checkout contains unrelated local work. Its baseline differs from remote main across 810 files. None of that unrelated history or data is included in this draft.
- Existing overlapping drafts #147 and #148 were discovered during publication checks. This draft is an independently executed alternative against main, not an instruction to combine or merge those repairs.

Inspected `project_guardian/ui_control_panel.py`, `start_ui_panel.py`, `tests/test_dashboard_listening.py`, and `tests/test_dashboard_idempotent.py` on the original baseline. The launcher constructs GuardianCore and can start broader runtime components; it was inspected but never executed. No UI redesign.

## Repair

Readiness requires HTTP 200 from `/api/ping` with this panel's random, non-secret `X-Elysia-Instance` identifier. Probes use direct HTTPConnection, bypassing proxies. A foreign listener, non-HTTP listener, failing response, or stale previous listener cannot establish readiness. Every `is_ready()` call rechecks HTTP health. Timeout remains nonfatal for slow startup; a subsequent successful probe can recover. Observed startup exceptions raise RuntimeError and release the existing retry guard. Failure and stop clear the ready event. The single-start guard and fallback port range remain.

On main, port availability now checks bind availability instead of connecting to every candidate port, matching the inspected local baseline. Listening tests reset the global guard between cases; previously one test's mock server contaminated later tests.

## Actual Windows environment

Native Windows, CPython 3.13.15 (MSC 64-bit), Flask 3.1.3, Flask-SocketIO 5.6.1, Werkzeug 3.1.8, pytest 9.1.1. Tests ran through the existing interpreter at `C:\Users\Owner\Project guardian\.venv\Scripts\python.exe`. No packages were installed. The system Python has no Flask; selecting the existing venv is necessary.

Browser verification used the Codex in-app Chromium browser against the native Windows Flask process. It was not a Linux container test or a separate Chrome/Edge compatibility sweep.

## Commands and results

From the original isolated repair worktree:

```powershell
& 'C:\Users\Owner\Project guardian\.venv\Scripts\python.exe' -m pytest tests/test_dashboard_http_readiness.py -q
```

Before repair: **6 failed, 1 passed** in 8.56s. Failures demonstrated timeout/error setting readiness, foreign HTTP 200/503 listeners accepted as Elysia, stale readiness after shutdown, and stop retaining the event. After adding lifecycle coverage and repairing readiness, the three focused files passed **20 tests** in 22.13s.

On the publishable main baseline, the production module was temporarily restored to the exact baseline bytes while retaining the new tests and test loader:

```powershell
& 'C:\Users\Owner\Project guardian\.venv\Scripts\python.exe' -m pytest tests/test_dashboard_http_readiness.py -q -k 'timeout_does_not or startup_error or other_http_server or own_http_success or stop_clears'
```

Result: **6 failed, 5 deselected** in 2.80s. The failing cases were timeout readiness, swallowed startup exception, foreign HTTP 200, foreign HTTP 503, own HTTP recovery, and stop clearing readiness. Production repair was then restored.

Final verification command on the publishable repair:

```powershell
& 'C:\Users\Owner\Project guardian\.venv\Scripts\python.exe' -m pytest tests/test_dashboard_http_readiness.py tests/test_dashboard_listening.py tests/test_dashboard_idempotent.py -q
git diff --check
```

The suite has 20 cases: 11 HTTP/lifecycle regressions, six listening/fallback cases, and three inherited idempotency cases. Final run: **20 passed in 18.95s**, no skips; `git diff --check` passed.

The new cases cover timeout, exception and retry, foreign HTTP 200/503, own HTTP success and listener loss, late startup recovery, stop signal clearing, silent TCP listeners, own HTTP 503, replacement listeners, and two real process startup/shutdown cycles with an occupied requested port. Process tests launch the base interpreter with the current dependency paths, wait for the child's own HTTP readiness marker, terminate only their owned child, and wait for port release before restart.

Intermediate verification failures were resolved: main's package import failed on missing `project_guardian.module_activity`; the verification-only loader avoids executing package startup and loads the actual dashboard module. An initial main run had five failures from guard leakage and connect-based port checks under the outbound block; fixture isolation and bind-based availability repaired those. An initial process test raced Windows port release; bounded polling and direct ownership of the base interpreter replaced the immediate check. A high ephemeral-port skip was removed by choosing a port below 65000. A PowerShell lifecycle command was rejected by automatic approval review; the owned Python subprocess test completed the check instead.

## Browser and endpoint observations

Start from the isolated worktree with the same dependencies:

```powershell
& 'C:\Users\Owner\Project guardian\.venv\Scripts\python.exe' scripts/verify_dashboard_windows.py
```

Wait for `FICTIONAL_READ_ONLY_READY http://127.0.0.1:5000`, then navigate to the three URLs. Ctrl+C ends the owned process. Port fallback is printed in that marker; do not assume 5000 when it is occupied.

| Endpoint | Original-baseline repair | Main-based draft repair |
| --- | --- | --- |
| `/` | HTTP 200; real existing HTML | HTTP 200; real existing HTML |
| `/api/ping` | HTTP 200; Elysia service, port 5000 | HTTP 200; Elysia service, port 5000 |
| `/api/status` | HTTP 500 with orchestrator absent | HTTP 500 with orchestrator absent |

Existing defects observed, deliberately left outside the repair:

1. Original checkout: Python's non-raw HTML template turns `lines.join('\n')` into a literal newline inside a JavaScript string (near template source line 1947). Browser reports `SyntaxError: Invalid or unexpected token`; Node 24.20.0 `--check` on the rendered inline script confirms it. Initialization remains stuck. Clicking Toggle Theme reports `ReferenceError: toggleTheme is not defined`. The parse failure prevents that entire script's button handlers from registering; other buttons were not individually activated. This newer-template defect is absent from the older main template used for publication.
2. Both baselines: `/api/status` without an orchestrator throws `UnboundLocalError` for `datetime`. A function-local import occurs only in the start-time branch; both the no-orchestrator response and its exception fallback reference the unbound local. This is an actual HTTP failure, not a mocked status response.
3. Main browser: UI displays **Running** and a running event loop despite `/api/status` returning 500 and no orchestrator. It is not a trustworthy operational-health indicator. HTTP readiness here means the panel's ping works, not that all dashboard features work.
4. `stop()` still clears flags without shutting down Flask's listener. Reliable shutdown/restart in this verification is at the owned process boundary. No claim of repaired in-process Socket.IO shutdown is made. A normally returning Socket.IO server can also leave the existing global start guard reserved; #148 separately addresses that path. Exception retry and process restart were verified here.
5. Normal package/launcher startup on remote main fails because `project_guardian.module_activity` is missing. The dashboard-only loader explicitly bypasses package initialization; it does not repair or certify GuardianCore startup.

## Disabled operations and data evidence

The verification script uses no orchestrator, no GuardianCore construction, no providers, no autonomy, and no protected actions. It removes credential-like environment variables in its process, redirects known dashboard state paths to an empty temporary directory, disables gateway probing, denies outbound socket connections except the selected loopback dashboard, and allows only GET `/`, `/api/ping`, `/api/status`, and favicon. All other routes return 403 before dispatch. Browser CSP blocks external resources, including both CDNs. Those intentionally blocked integrations are not evidence of broken production endpoints. No learning, chat, task submission, credential, or write-capable smoke operations were invoked. No application credentials were read or configured; GitHub's existing authenticated connection is used only for the requested draft publication.

SHA-256 comparison of **3,526 existing original-checkout files** under data/config, plus the existing memory/browser state/review queue paths, found **zero changes** across the conflict/restart verification interval. Final comparison: 3,526 before and after, zero modified/deleted, zero added. The manifest contains paths and hashes only and stays outside Git. It was taken after initial browser inspection, so it is not retroactive proof for earlier reads. Original tracked-work status remained its pre-existing review-queue modification; all repair and test artifacts live in separate worktrees. No writes to the original runtime were requested. Final port check: no listener on 5000.

## Changed files and rollback

- `project_guardian/ui_control_panel.py`: HTTP identity/readiness and bind availability.
- `tests/test_dashboard_http_readiness.py`: regression and owned-process verification.
- `tests/test_dashboard_listening.py`: reset test guard between cases.
- `scripts/dashboard_verification_loader.py`: verification-only dashboard import without GuardianCore initialization.
- `scripts/verify_dashboard_windows.py`: fictional, read-only local launch harness.
- This report.

The original-baseline worktree retains its separate three-file repair: `project_guardian/ui_control_panel.py`, `tests/test_dashboard_http_readiness.py`, and `scripts/verify_dashboard_windows.py`. It is not part of the main-based PR ancestry.

No merge or deployment. Rollback is to close/abandon the draft and stop any owned verification process; the original checkout is unaffected. For an applied repair commit, revert that commit on the isolated branch. To reproduce the red tests without touching other work, use a disposable worktree at the pinned publishable baseline, copy only the new tests and verification loader, and run the baseline command above. Independently verify the exact draft head SHA before considering integration.
