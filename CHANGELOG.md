# Changelog (append-only)

## TASK-0001

- Initialized ops spine: CONTROL.md, SPEC.md, TASKS/, REPORTS/.

## TASK-0002

- Added acceptance runner script: scripts/acceptance.ps1
- Script detects Python/Node.js tooling and runs available checks
- Non-failing pipeline (exits 0 if no tooling configured)

## TASK-0003

- Added governance invariant tests: tests/test_invariants.py
- Tests enforce SPEC.md invariants:
  - IdentityAnchor required for external actions
  - TrustEngine gates autonomy
  - MutationFlow protects governance modules
  - PromptRouter outputs deterministic
- Invariant tests integrated into acceptance runner

## TASK-0004

- Fixed acceptance.ps1 to exit non-zero on invariant failures (governance gate)
- Upgraded invariant tests from presence checks to behavioral checks:
  - WebReader.fetch() must gate through TrustMatrix (behavioral test)
  - MutationEngine.apply() must reject governance files (behavioral test)
  - TrustMatrix.make_consultation_decision() must be callable (behavioral test)
  - PromptRouter must be deterministic (behavioral test)
- Pipeline now fails if invariants are violated

## TASK-0005

- Added TrustMatrix gating to WebReader.fetch()
- WebReader.__init__() now accepts trust_matrix parameter
- fetch() gates through TrustMatrix.validate_trust_for_action() before network calls
- Returns None if trust gate denies (no network call made)
- Updated GuardianCore to pass TrustMatrix to WebReader

## TASK-0006

- Added governance protection to MutationEngine.apply()
- Defined PROTECTED_GOVERNANCE_PATHS and PROTECTED_DIRECTORIES constants
- apply() rejects mutations to protected paths unless allow_governance_mutation=True
- Override flag requires TrustMatrix approval (system_change action, 0.9+ trust)
- Updated GuardianCore to pass TrustMatrix to MutationEngine

## TASK-0007

- Replaced ambiguous `None` return with explicit `TrustDeniedError` exception in WebReader.fetch()
- Added context parameter to TrustMatrix.validate_trust_for_action() (target, method, caller, task_id)
- WebReader.fetch() now passes context (domain, method, caller_identity, task_id) to trust gate
- Removed hardcoded 0.9 threshold from MutationEngine - now asks TrustMatrix for "governance_mutation" decision
- MutationEngine passes context (touched_paths, override_flag, caller_identity) to TrustMatrix
- Updated tests to verify explicit denials (exceptions) and context passing
- Updated GuardianCore.fetch_web_content() to handle TrustDeniedError

## TASK-0008

- Added bypass detection invariants for network/file/subprocess calls
- Scans project_guardian/ for ungated network library usage (requests, httpx, urllib, aiohttp, etc.)
- Scans for ungated file writes (open("w"/"a"), Path.write_text, shutil.move/copy)
- Scans for ungated subprocess execution (subprocess.*, os.system)
- Tests verify all external actions are gated through TrustMatrix
- Approved modules (external.py, mutation.py) are exceptions

## TASK-0009

- Added TrustDecision dataclass (allowed, decision, reason_code, message, risk_score)
- validate_trust_for_action() now returns TrustDecision (not bool)
- Decision types: "allow", "deny", "review" (for borderline trust)
- WebReader and MutationEngine use TrustDecision.decision to determine action
- Risk score calculated from trust margin
- Reason codes are machine-readable (e.g., "INSUFFICIENT_TRUST_NETWORK_ACCESS")
- No callers interpret raw trust floats - all use TrustDecision

## TASK-0010

- Replaced regex-based bypass detection with AST-based scanning
- Detects aliased imports, indirect calls, wrapper functions
- Allowlist scoped to gateway functions (not entire files)
- Network gateway: WebReader.fetch() only
- File write gateway: MutationEngine.apply() only
- Subprocess gateway: none (all denied)
- Reports violations with file:line:symbol precision

## TASK-0011

- Added FileWriter gateway module with TrustMatrix gating
- Added SubprocessRunner gateway module with TrustMatrix gating (denies by default)
- Updated bypass detection allowlist to include new gateways

## TASK-0012

- Added ReviewQueue (file-backed JSONL) for review requests
- Added ApprovalStore (file-backed JSON) for approval records
- Added ReviewRequest dataclass schema
- Added TrustReviewRequiredError exception
- Gateways now enqueue review requests instead of hard failing on "review" decision
- Added replay mechanism: approved request_id bypasses review (with context matching)
- Context matching prevents token reuse (approve one thing, use for another)
- Tests verify review workflow: enqueue -> approve -> replay

## TASK-0013

- Added FastAPI control panel (project_guardian/ui/app.py)
- Local-only web UI (127.0.0.1:8000)
- Status dashboard: current task, pending reviews, last acceptance run
- Review queue: list pending, view detail, approve/deny with notes
- Task control: set CURRENT_TASK, run acceptance script
- Jinja2 templates for server-side rendering
- Safety: only runs acceptance script, redacts sensitive context fields
- Added start_control_panel.ps1 script

## TASK-0014

- Split UI dependencies to requirements-ui.txt (optional, not in core requirements.txt)
- acceptance.ps1 now writes durable artifacts:
  - REPORTS/acceptance_last.json (timestamp, exit_code, status, duration)
  - REPORTS/acceptance_last.log (full output, redacted)
- UI reads acceptance artifacts instead of guessing from file timestamps
- Added /acceptance-log endpoint to view last run log
- Enhanced safety: input sanitization, encoding handling, error handling
- start_control_panel.ps1 warns if UI deps missing

## TASK-0015

- **Atomic writes everywhere**: CONTROL.md, approval_store.json use tmp + os.replace() pattern
- **ReviewQueue.get_request()** returns latest record (last occurrence in JSONL)
- **ApprovalStore** uses atomic writes with single-writer assumption documented
- **UI context mutation fixed**: Redaction operates on copies, original context preserved
- **Action constants normalized**: NETWORK_ACCESS, FILE_WRITE, SUBPROCESS_EXECUTION, GOVERNANCE_MUTATION in trust.py
- All gateways updated to use action constants consistently
- **Acceptance artifact assertion**: Script fails if acceptance_last.json missing after run
- TrustMatrix trust_requirements updated to use constants
- **Bug fixes**: Fixed undefined `action` variable in external.py deny fallback, fixed hardcoded action string in subprocess_runner.py timeout, added guardrail for unknown action strings in trust.py
- **Test added**: `test_review_without_queue_denies_cleanly()` verifies review + no review_queue denies cleanly

## TASK-0016

- **TrustMatrix audit**: Fixed review decision semantics (allowed=False for review decisions)
- **Context redaction**: Enhanced to filter token/key/secret/password/api_key/auth_token
- **Guardrail improvement**: Unknown action check now uses LEGACY_ACTIONS meaningfully
- **Smoke tests**: Added `tests/test_trust_smoke.py` with behavioral tests (structure, thresholds, redaction, guardrail)
- **Documentation**: Created `SPEC_MODULES/trust.md` defining decision semantics, action policy, review workflow
- **Audit report**: Created `REPORTS/module_audit_trust.md` documenting findings and gaps

## TASK-0017

- **ReviewQueue audit**: Verified append-only integrity, latest-state correctness, restart tolerance, corruption handling
- **ApprovalStore audit**: Verified atomic writes, context-match strictness, deterministic hashing, replay attack prevention
- **Smoke tests**: Added `tests/test_review_queue_smoke.py` and `tests/test_approval_store_smoke.py` with behavioral tests
- **Documentation**: Created `SPEC_MODULES/review_queue.md` and `SPEC_MODULES/approval_store.md` defining module contracts
- **Audit reports**: Created `REPORTS/module_audit_review_queue.md` and `REPORTS/module_audit_approval_store.md`
- **Status transition policy**: Enforced monotonic transitions (pending → approved/denied only, no reversals)

## TASK-0018

- **Gateways audit**: Verified WebReader, FileWriter, SubprocessRunner allow/deny/review/replay paths
- **Context safety**: Verified only safe data stored (domain only, filename only, command name only)
- **Forbidden patterns**: Verified no shell=True, no arbitrary commands, mode restrictions enforced
- **Smoke tests**: Added `tests/test_gateways_smoke.py` with behavioral tests (12+ tests across 3 gateways)
- **Documentation**: Created `SPEC_MODULES/gateways.md` defining gateway contracts, context rules, security constraints
- **Audit report**: Created `REPORTS/module_audit_gateways.md` documenting findings and gaps

## TASK-0019

- **MutationEngine hardening**: Replaced string-return outcomes with explicit exceptions + MutationResult dataclass
- **Bypass removal**: Disabled `review_with_gpt()` (bypasses governance, always rejects now)
- **Core truthiness fix**: Fixed Core to use TrustDecision.decision semantics (not truthiness)
- **ReviewQueue integration**: Aligned governance override flow with ReviewQueue + ApprovalStore (same pattern as gateways)
- **Smoke tests**: Added `tests/test_mutation_smoke.py` with behavioral tests (7+ tests covering deny/review/replay/success)
- **Documentation**: Created `SPEC_MODULES/mutation.md` defining MutationEngine contracts, decision semantics, forbidden patterns
- **Audit report**: Created `REPORTS/module_audit_mutation.md` documenting fixes and remaining gaps

## TASK-0020

- **GuardianCore audit**: Audited Core for completeness and correct integration with TrustMatrix, ReviewQueue, ApprovalStore, Gateways, MutationEngine
- **Initialization order fix**: Fixed bug where MutationEngine was initialized before TrustMatrix
- **run_once() method**: Added deterministic single-step entrypoint for testing
- **WebReader integration**: Fixed WebReader initialization to include ReviewQueue and ApprovalStore
- **Smoke tests**: Added `tests/test_core_smoke.py` with behavioral tests (6+ tests covering construction, review/deny propagation, mutation integration)
- **Documentation**: Created `SPEC_MODULES/core.md` defining Core responsibilities, boundaries, integration points, invariants
- **Audit report**: Created `REPORTS/module_audit_core.md` documenting findings, fixes, and remaining gaps

## TASK-0021

- **CONTROL.md integration**: Core now reads CONTROL.md and routes current task deterministically
- **Task contract loading**: Added `load_task_contract()` to load and validate task contracts from TASKS/
- **Structured results**: `run_once()` now returns structured dict results (idle/ready/error) instead of ambiguous strings
- **Task router tests**: Added `tests/test_core_task_router.py` with deterministic tests (6+ tests)
- **Documentation**: Updated `SPEC_MODULES/core.md` and `REPORTS/module_audit_core.md` with CONTROL.md integration details

## TASK-0022

- **Task execution engine**: Added minimal task execution layer with whitelisted task types (RUN_ACCEPTANCE, CLEAR_CURRENT_TASK)
- **Task contract validation**: Added strict validation for TASK_TYPE directive (exactly one, whitelisted types only)
- **RUN_ACCEPTANCE execution**: Executes acceptance script safely via known subprocess path
- **CLEAR_CURRENT_TASK execution**: Atomically sets CONTROL.md to NONE
- **Task execution tests**: Added `tests/test_task_execution.py` with deterministic tests (6+ tests)
- **Documentation**: Updated `SPEC_MODULES/core.md` and `REPORTS/module_audit_core.md` with task execution model

## TASK-0023

- **APPLY_MUTATION task type**: Added whitelisted task type for executing mutations via MutationEngine
- **Mutation payload format**: Added strict JSON payload format in `MUTATIONS/` directory with path safety validation
- **Task contract validation**: Extended contract validation to support APPLY_MUTATION directives (MUTATION_FILE, ALLOW_GOVERNANCE_MUTATION, REQUEST_ID)
- **Review/approve/replay support**: APPLY_MUTATION supports deny/review/approve/replay flows with structured results
- **Mutation execution tests**: Added `tests/test_apply_mutation_task.py` with deterministic tests (6+ tests)
- **MUTATIONS directory**: Created `MUTATIONS/.gitkeep` for mutation payload files
- **Documentation**: Updated `SPEC_MODULES/core.md`, `SPEC_MODULES/mutation.md`, `REPORTS/module_audit_core.md`, and `REPORTS/module_audit_mutation.md` with APPLY_MUTATION details

## TASK-0024

- **Preflight for APPLY_MUTATION**: Added preflight phase that validates all paths and checks TrustMatrix BEFORE any writes occur
- **No partial apply guarantee**: Preflight ensures all-or-nothing mutation application (no partial writes)
- **Preflight logic**: If ALLOW_GOVERNANCE_MUTATION=false and any path protected → deny immediately; if true → check TrustMatrix once for entire batch
- **Replay handling**: Preflight checks ApprovalStore first if REQUEST_ID provided (bypasses TrustMatrix if approved)
- **End-to-end workflow tests**: Added `tests/test_e2e_workflow.py` with deterministic tests (4+ tests covering review→approve→replay, preflight partial prevention, protected path denial)
- **Documentation**: Updated `SPEC_MODULES/core.md`, `SPEC_MODULES/mutation.md`, `REPORTS/module_audit_core.md`, and `REPORTS/module_audit_mutation.md` with preflight details

## TASK-0025

- **Subprocess surface unification**: Eliminated direct `subprocess.run` usage from Core
- **SubprocessRunner integration**: All subprocess execution (including acceptance) now goes through SubprocessRunner gateway
- **SubprocessRunner initialization**: Core constructs SubprocessRunner with shared TrustMatrix, ReviewQueue, ApprovalStore (same pattern as WebReader)
- **Acceptance execution via gateway**: RUN_ACCEPTANCE task uses SubprocessRunner with fixed command list and 300-second timeout
- **SubprocessRunner timeout support**: Added configurable timeout parameter (default: 30s, acceptance: 300s)
- **Test updates**: Updated `tests/test_task_execution.py` to mock SubprocessRunner instead of subprocess.run
- **Documentation**: Updated `SPEC_MODULES/core.md`, `SPEC_MODULES/gateways.md`, `REPORTS/module_audit_core.md`, and `REPORTS/module_audit_gateways.md` with subprocess surface unification details

## TASK-0026

- **Control Panel MVP Expansion**: Expanded FastAPI control panel with task creation, mutation payload creation, and run_once() execution
- **Run Once endpoint**: Added `POST /control/run-once` to execute GuardianCore.run_once() and save artifact (REPORTS/run_once_last.json)
- **Task Builder UI**: Added task creation form (`GET /tasks/new`) and endpoint (`POST /tasks/create`) supporting RUN_ACCEPTANCE, CLEAR_CURRENT_TASK, APPLY_MUTATION
- **Mutation Builder UI**: Added mutation payload creation form (`GET /mutations/new`) and endpoint (`POST /mutations/create`) with strict path and schema validation
- **Dashboard updates**: Added last run_once result display and new action buttons (Run Once, Clear Current Task, Create Task, Create Mutation Payload)
- **Validation**: Strict validation for task_id format, task_type whitelist, mutation file paths, and payload schema
- **Atomic writes**: All file writes use tmp + os.replace() pattern (task files, mutation payloads, run_once artifact)
- **Tests**: Added `tests/test_ui_smoke.py` with minimal FastAPI TestClient tests
- **Documentation**: Created `SPEC_MODULES/ui.md` and `REPORTS/module_audit_ui.md` with UI specification and audit report

## TASK-0027

- **Control Panel Observability**: Added read-only observability features to control panel
- **Execution history**: Added history retention for run_once and acceptance runs with timestamped files in `REPORTS/run_once_history/` and `REPORTS/acceptance_history/`
- **History pages**: Added `/history` list view and `/history/run-once/{filename}` and `/history/acceptance/{filename}` detail views
- **Review history**: Updated `/reviews` endpoint to support status filtering (pending/approved/denied/all) with counts
- **Mutation payload browser**: Added `/mutations` list view and `/mutations/{filename}` detail view
- **Diff viewer**: Added `/diff?mutation=<file>&path=<path>` endpoint for viewing unified diffs between mutation payload and current files
- **History retention**: Run once and acceptance artifacts automatically copied to history directories with atomic writes
- **Validation**: All file reads validated (no .., no arbitrary paths), diff viewer validates path is in mutation touched_paths
- **Safety**: Diff output HTML escaped, diff size limited to 2000 lines
- **Tests**: Added `tests/test_ui_observability.py` with minimal tests for history, mutations, and diff viewer
- **Documentation**: Updated `SPEC_MODULES/ui.md` and `REPORTS/module_audit_ui.md` with observability features

## TASK-0028

- **History Retention Policy**: Added retention policy to prevent disk growth from history files
- **File-count retention**: Prunes to keep newest 200 run_once and 200 acceptance history files (after each write)
- **Age-based retention**: Also prunes files older than 30 days
- **Log copy caps**: Only copies acceptance logs if size <= 1MB; marks in JSON if too large
- **Retention helpers**: Added `_ensure_dir()` and `_prune_history_dir()` helpers with safety constraints
- **Safety**: Only deletes files in history directories, matching expected patterns; never deletes `*_last.*` files
- **Best-effort**: Pruning failures are logged but don't crash UI
- **UI display**: Shows retention policy info on `/history` page
- **Tests**: Added `tests/test_ui_retention.py` with tests for count-based pruning, log copy caps, and safety constraints
- **Documentation**: Updated `SPEC_MODULES/ui.md` and `REPORTS/module_audit_ui.md` with retention policy details

## TASK-0029

- **Mutation Payload Base Hashing**: Added base hash computation at payload creation time
- **Base hash storage**: Each mutation payload now includes `base` object with SHA256 hash, byte count, and timestamp for each touched file
- **Missing file handling**: Files that don't exist at creation time are marked as "MISSING" in base info
- **Diff viewer mismatch warnings**: Diff viewer now computes current file hash and compares with base hash, showing warning banner when file changed since payload creation
- **Legacy payload support**: Payloads without base info are handled gracefully with "No base recorded" message
- **Mutation detail hash display**: Mutation detail page shows base hash, current hash, and status indicator (MATCH/MISMATCH/MISSING/NEW_FILE/DELETED/LEGACY/ERROR) for each touched path
- **Backward compatibility**: Base hashing is optional in payload schema; legacy payloads work without errors
- **Tests**: Added `tests/test_ui_diff_basehash.py` with tests for payload creation base hashes, diff viewer mismatch warnings, and legacy payload handling
- **Documentation**: Updated `SPEC_MODULES/ui.md` and `REPORTS/module_audit_ui.md` with base hashing details and remaining risks (base content not stored)

## TASK-0030

- **Local-Only Access Enforcement**: Added application-layer enforcement to prevent accidental remote exposure
- **Loopback guard**: FastAPI middleware rejects non-loopback client hosts with HTTP 403
- **Loopback detection**: `is_loopback()` function checks for `127.0.0.1`, `::1`, `localhost`
- **No trust in forwarded headers**: Uses `request.client.host` only; does NOT trust `X-Forwarded-For`
- **Misbind warning**: Dashboard shows local-only banner and red warning if `UI_BIND_HOST` is set to non-loopback
- **API status flags**: `/api/status` includes `local_only_enforced: true` and `bind_host_warning` flags
- **Start script hardening**: `start_control_panel.ps1` enforces `--host 127.0.0.1` with security warnings
- **Error page**: Updated error.html template to show proper error messages for blocked requests
- **Tests**: Added `tests/test_ui_local_only.py` with tests for loopback detection, middleware enforcement, and bind host warnings
- **Documentation**: Updated `SPEC_MODULES/ui.md` and `REPORTS/module_audit_ui.md` with local-only enforcement details

## TASK-0031

- **Module Completeness Matrix**: Created automated module completeness analysis tool
- **Script**: Added `scripts/module_matrix.py` to scan all modules and generate completeness reports
- **Reports**: Generated `REPORTS/module_completeness_matrix.json` and `REPORTS/module_completeness_matrix.md`
- **Completeness checks**: Analyzes modules for spec, audit, tests, core wiring, and bypass compliance
- **Task contracts**: Auto-generated follow-on task contracts (TASK-0032 through TASK-0036) for identified gaps
- **Heuristics**: Deterministic heuristics for test detection, core wiring detection, and bypass detection
- **Tests**: Added `tests/test_module_matrix.py` with minimal tests for matrix generation
- **Documentation**: Updated `CHANGELOG.md` and `REPORTS/AGENT_REPORT.md` with TASK-0031 entry

## TASK-0036

- **Bypass Findings Resolution**: Resolved bypass findings by documenting exceptions for modules that cannot route through gateways
- **Documented exceptions**: Added BYPASS DOCUMENTATION comments to 5 modules explaining why they bypass gateways:
  - `gumroad_client.py`: Master-only financial API requiring POST/PUT/JSON (WebReader only supports GET)
  - `slave_deployment.py`: Master-only deployment requiring async subprocess (SubprocessRunner is synchronous)
  - `metacoder.py`: Code mutation engine requiring subprocess for tests and shutil for backups
  - `ai_tool_registry_engine.py`: Tool registry requiring POST requests with JSON (WebReader only supports GET)
  - `webscout_agent.py`: Web research agent requiring async HTTP operations (WebReader is synchronous)
- **Invariant test updates**: Updated `tests/test_invariants.py` to allowlist documented exceptions (modules with BYPASS DOCUMENTATION comments)
- **Exception verification**: Invariant tests verify that documented exceptions actually have BYPASS DOCUMENTATION comments
- **Tests**: All bypass detection tests pass with documented exceptions allowlisted
- **Documentation**: Updated `CHANGELOG.md` and `REPORTS/AGENT_REPORT.md` with TASK-0036 entry

## TASK-0037

- **Gateway Enhancement**: Eliminated comment-based bypass allowlist by implementing missing gateway capabilities
- **WebReader.request_json()**: Added POST/PUT/PATCH/DELETE support with JSON payloads:
  - Supports all HTTP methods (GET, POST, PUT, PATCH, DELETE)
  - JSON body support (dict or list)
  - Custom headers with automatic redaction of sensitive values
  - JSON response parsing (best-effort)
  - Full TrustMatrix gating with context (method, domain, has_body, content_type)
  - Review/replay support
- **SubprocessRunner.run_command_background()**: Added non-blocking background execution:
  - Uses subprocess.Popen for non-blocking execution
  - Returns pid, started flag, and command string
  - Full TrustMatrix gating with background flag in context
  - Review/replay support
  - Enforces shell=False (STRICTLY FORBIDDEN)
- **Module Refactoring**: Refactored 5 modules to use gateways:
  - `gumroad_client.py`: All HTTP calls route through WebReader.request_json (removed requests dependency)
  - `ai_tool_registry_engine.py`: POST JSON calls route through WebReader.request_json (removed requests dependency)
  - `webscout_agent.py`: All HTTP calls route through WebReader (removed httpx dependency, converted async to sync)
  - `slave_deployment.py`: Subprocess calls route through SubprocessRunner (converted async subprocess to sync gateway)
  - `metacoder.py`: File writes route through FileWriter, subprocess routes through SubprocessRunner (removed shutil/subprocess direct usage)
- **Bypass Allowlist Removal**: Removed DOCUMENTED_BYPASS_EXCEPTIONS and _is_documented_exception from invariant tests
- **Gateway Allowlist Updates**: Added new gateway methods to allowlist:
  - WebReader.request_json
  - SubprocessRunner.run_command_background
- **Tests**: Added comprehensive tests:
  - `tests/test_webreader_post_json.py`: Tests for POST/JSON support (deny, review, replay, context, JSON parsing)
  - `tests/test_subprocess_runner_background.py`: Tests for background mode (deny, review, replay, pid, context, shell=False enforcement)
- **Documentation**: Updated `SPEC_MODULES/gateways.md` with request_json and run_command_background contracts
- **Acceptance**: All tests pass, bypass detection is strict again (no exceptions)

## TASK-0038

- **SSRF Safety Floor**: Added minimum SSRF safety floor to WebReader to prevent access to internal targets
- **Scheme Validation**: Only `http://` and `https://` schemes allowed (raises `TrustDeniedError` with `UNSUPPORTED_URL_SCHEME` for other schemes)
- **Internal Target Blocking**: Blocks access to:
  - Loopback IPs: `127.0.0.0/8`, `::1`
  - Link-local IPs: `169.254.0.0/16` (includes cloud metadata IP `169.254.169.254`)
  - Private RFC1918 IPs: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
  - IPv6 ULA: `fc00::/7`
  - IPv6 link-local: `fe80::/10`
  - Hostnames: `localhost`, any hostname ending with `.local`, empty host
- **Override Path**: Added `allow_internal=True` parameter to `fetch()` and `request_json()`:
  - Internal targets with `allow_internal=True` are not immediately blocked
  - Still require TrustMatrix review/approval (cannot auto-allow)
  - Scheme validation still applies (http/https only)
  - Context includes `allow_internal=True` and `blocked_reason="TARGET_BLOCKED_INTERNAL"` for audit
- **Context Enhancement**: Context now includes `scheme`, `allow_internal`, and `blocked_reason` fields
- **Tests**: Added comprehensive tests (`tests/test_webreader_target_validation.py`):
  - Scheme validation tests (file:// denied, http/https allowed)
  - Internal IP blocking tests (loopback, link-local, private IPs)
  - Hostname blocking tests (localhost, .local)
  - External host allowed path (with TrustMatrix allow/deny)
  - Override path tests (allow_internal with TrustMatrix deny/review/allow)
  - Context validation tests
- **Documentation**: Updated `SPEC_MODULES/gateways.md` with SSRF safety floor documentation
- **Audit**: Updated `REPORTS/module_audit_gateways.md` with SSRF safety improvements and known limitations (no DNS resolution)
- **Acceptance**: All tests pass, SSRF safety floor enforced

## TASK-0039

- **Background Subprocess Audit Trail**: Added append-only audit log for background subprocess launches
- **Audit Log File**: `REPORTS/subprocess_background.jsonl` (append-only JSONL format)
- **Audit Record Fields**: Each background launch appends one JSON line with:
  - `ts`: ISO8601 timestamp (UTC)
  - `pid`: Process ID
  - `command`: Command and arguments list (sensitive args redacted)
  - `cwd`: Current working directory (str | null)
  - `timeout_s`: Always null for background processes
  - `caller_identity`: Caller identifier (str | "unknown")
  - `task_id`: Task ID (str | "unknown")
  - `request_id`: Request ID if replay-approved (str | null)
  - `action`: Action constant (SUBPROCESS_EXECUTION)
  - `decision`: Always "allow" (background runs only occur when allowed or replay-approved)
  - `notes`: "background"
- **Command Argument Redaction**: Arguments containing sensitive keywords (token, key, secret, password, api_key, auth) are redacted to `"***REDACTED***"`
- **Integration**: Audit log append occurs after successful process launch (PID known)
- **Failure Behavior**: Audit write failures do not crash subprocess calls (best-effort logging)
- **Deny/Review Paths**: Do not write audit lines (only successful launches are logged)
- **Tests**: Added comprehensive tests (`tests/test_subprocess_background_audit.py`):
  - Background launch writes audit line
  - Review/deny do not write audit
  - Command argument redaction
  - Replay-approved writes audit with request_id
  - Append-only behavior (multiple launches)
  - Audit write failure does not crash
- **Documentation**: Updated `SPEC_MODULES/gateways.md` with background audit log format and location
- **Audit**: Updated `REPORTS/module_audit_gateways.md` with background audit trail improvements
- **Acceptance**: All tests pass, background launches are auditable

## TASK-0041

- **FileWriter Path Safety**: Added strict path safety validation to prevent path traversal attacks
- **Repo Root Resolution**: FileWriter now accepts `repo_root` parameter (defaults to project root computed from `__file__`)
- **Path Validation Rules**:
  - Rejects absolute paths (raises `TrustDeniedError` with `PATH_TRAVERSAL_BLOCKED`)
  - Rejects paths containing `..` (traversal detection)
  - Enforces all paths must resolve within repo root (checked via `Path.relative_to()`)
  - Rejects writing directly to directories
- **Validation Order**: Path safety validation occurs **before** TrustMatrix gating (defense-in-depth)
- **Symlink Protection**: Paths that escape via symlinks are blocked by resolve() + relative_to() check
- **Atomic Writes**: Implemented atomic write behavior (write to temp file then `os.replace`)
- **Context Enhancement**: Context now includes relative path (not absolute), `bytes` (content length), and `allow_overwrite` (boolean)
- **Tests**: Added comprehensive tests (`tests/test_file_writer_path_safety.py`):
  - Blocks absolute paths (POSIX and Windows)
  - Blocks traversal (`../outside.txt`, `project_guardian/../outside.txt`)
  - Allows safe relative paths (`REPORTS/test.txt`, `project_guardian/_tmp.txt`)
  - Blocks paths via symlink (if supported)
  - Blocks writing to directories
  - Verifies gating not called on invalid paths
  - Verifies atomic write behavior
  - Verifies context uses relative paths
- **Documentation**: Updated `SPEC_MODULES/gateways.md` with path safety rules
- **Audit**: Updated `REPORTS/module_audit_gateways.md` with path traversal protection improvements
- **Acceptance**: All tests pass, path traversal attacks blocked

## TASK-0042

- **MutationEngine Path Safety Parity**: Added path safety validation to MutationEngine to match FileWriter
- **Repo Root Resolution**: MutationEngine now accepts `repo_root` parameter (defaults to project root computed from `__file__`)
- **Path Validation Helper**: Added `_validate_and_resolve_path()` method that:
  - Rejects absolute paths (raises `MutationDeniedError` with `PATH_TRAVERSAL_BLOCKED`)
  - Rejects paths containing `..` (traversal detection)
  - Enforces all paths must resolve within repo root (checked via `Path.relative_to()`)
  - Rejects writing directly to directories (raises `MutationDeniedError` with `PATH_IS_DIRECTORY`)
  - Blocks symlink escape (via resolve() + relative_to() check)
- **Validation Order**: Path safety validation occurs **before** governance/protection checks (defense-in-depth)
- **Core Preflight Integration**: Core's preflight now validates all paths using MutationEngine's validation **before any writes**
- **Path Normalization**: All paths are normalized to relative paths from repo root, used in context for TrustMatrix and ApprovalStore
- **Preflight Guarantee**: Invalid paths cause denial before any writes/backups occur (no partial mutation applies)
- **Tests**: Added comprehensive tests (`tests/test_mutation_path_safety.py`):
  - Blocks absolute paths (POSIX and Windows)
  - Blocks traversal (`../outside.txt`, `a/../outside.txt`)
  - Blocks symlink escape (if supported)
  - Denies before writing anything (mixed batch test)
  - Allows safe paths
  - Blocks writing to directories
  - Verifies validation occurs before governance checks
  - Verifies normalized paths in context
- **Documentation**: Updated `SPEC_MODULES/mutation.md` with path safety rules and preflight guarantee
- **Audit**: Updated `REPORTS/module_audit_mutation.md` with path safety parity improvements
- **Acceptance**: All tests pass, path traversal attacks blocked, parity with FileWriter achieved

## TASK-0043

- **No Side-Effects Negative Tests**: Added end-to-end negative tests that prove deny/review decisions create no side-effects
- **Network Tests** (`tests/test_no_side_effects_network.py`):
  - SSRF denial does not call network (urllib not called)
  - Internal target review override enqueues only (no network call)
  - External target deny/review does not call network
- **Subprocess Tests** (`tests/test_no_side_effects_subprocess.py`):
  - Review does not launch process (Popen not called) and does not write audit
  - Deny does not launch process and does not write audit
  - Sync subprocess review/deny does not execute (subprocess.run not called)
- **Mutation Tests** (`tests/test_no_side_effects_mutation.py`):
  - Invalid path mutation does not write or create backups
  - Review does not write or create backups (ReviewQueue enqueue allowed)
  - Deny does not write or create backups
  - Protected path without override does not write (TrustMatrix not called)
- **Task Engine Tests** (`tests/test_no_side_effects_task_engine.py`):
  - APPLY_MUTATION review does not write or create backups
  - APPLY_MUTATION deny (invalid path) does not write or create backups
  - APPLY_MUTATION trust deny does not write or create backups
- **Test Coverage**: All tests verify:
  - No file writes on deny/review
  - No backup creation on deny/review
  - No network calls on deny/review (network tests)
  - No subprocess execution on deny/review (subprocess tests)
  - ReviewQueue enqueue is allowed (permitted side-effect)
- **Acceptance**: All tests pass, invariants locked, no violations found

- **Gateways audit**: Verified WebReader, FileWriter, SubprocessRunner allow/deny/review/replay paths
- **Context safety**: Verified only safe data stored (domain only, filename only, command name only)
- **Forbidden patterns**: Verified no shell=True, no arbitrary commands, mode restrictions enforced
- **Smoke tests**: Added `tests/test_gateways_smoke.py` with behavioral tests (12+ tests across 3 gateways)
- **Documentation**: Created `SPEC_MODULES/gateways.md` defining gateway contracts, context rules, security constraints
- **Audit report**: Created `REPORTS/module_audit_gateways.md` documenting findings and gaps
