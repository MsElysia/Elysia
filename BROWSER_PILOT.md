# Restricted browser pilot — isolated draft

This is an opt-in interface to PR125's **fictional** transactional learning store.
It is separate from UIControlPanel. It does not import GuardianCore, MemoryCore,
provider SDKs, credential managers, Socket.IO, or the legacy dashboard.
Existing launchers and the original offline CLI remain the default.

## Start in a disposable checkout

Use Python 3.12 and an isolated environment containing Flask 3.1.3 and pytest 8.4.2.
Do not install the full optional AI dependency graph just to run this pilot.

    python -B -m pytest --noconftest tests/test_restricted_browser_bridge.py -q -rs -p no:cacheprovider
    python -B elysia_restricted_browser.py --port 5077 --store acceptance

The second command requires a local terminal. Choose a temporary password of
16–256 characters at its hidden prompt, then open http://127.0.0.1:5077/ and enter
the same password. The password is not supplied through arguments, URLs, environment,
HTML, configuration, memory, or application logs. It lives only in the operator's
input and the server's in-memory verifier. Do not reuse a real account password.
Stop with Ctrl+C; startup never kills another process or takes over an occupied port.

Data is confined to `.synthetic-pilot-stores/browser-acceptance` under this checkout.
The `--store` argument is a short name, never an arbitrary filesystem path. Reusing
the same name reopens that synthetic store. A changed name creates a separate store.
Do not copy user data or production memory into these directories.

## Workflow

1. Connect using the temporary password.
2. Save key `lantern`, text `Fictional moonberry lantern color is violet.`
3. Recall `What color is the moonberry lantern?`
4. Correct the same key to `Fictional moonberry lantern color is amber.`
5. Inspect history; both revisions must appear.
6. Ctrl+C in the terminal; verify this owned server exited and its port was released.
7. Restart using the same store name, establish a new browser session, then recall
   `Tell me the moonberry lantern color.` It must return amber with source evidence.

This is deterministic source recall, not a general language model. Facts must begin
`Fictional ` and the inherited pilot allows seven learned revisions per store.
Unsupported information is refused. This is not personal-memory migration approval.

## Boundaries

The server accepts only 127.0.0.1 clients and the exact configured Host/port. Every
POST requires the exact local Origin and JSON. Memory operations additionally need
an HttpOnly SameSite=Strict opaque session cookie and a CSRF header. Sessions expire
after 30 minutes and are lost on server restart. Password guessing is bounded to
five failures per minute. Eight simultaneous sessions is the fixed limit.
There are no external scripts, permissive CORS, privileged legacy routes, model
configuration, task execution, or credential-write endpoints. CSP restricts assets
and connections to the same origin. The cookie is local HTTP; this is not a remote
hosting configuration or isolation from a malicious process under the same OS account.

Every memory request uses a fresh `python -S -B` worker, a fixed script, a scrubbed
environment and a fixed synthetic store name. The worker reuses SyntheticLearningStore,
RestrictedElysia and the existing offline audit guard/transaction implementation.
Parent requests have a 15-second worker timeout and no automatic retry. If a write
has an uncertain result, inspect history before retrying. Existing duplicate detection
prevents repeated identical fictional facts from creating another revision.

The only inherited product edit handles Linux directory descriptors in the offline
guard, needed by safe transaction cleanup. Outside descriptors still fail closed.
Unsupported descriptor resolution is denied. Windows junctions are refused by the
worker; native Windows execution of that case remains a required acceptance step.
Filesystem guarantees remain for cooperating writers, not hostile OS-level races or
physical power loss. Corruption causes failure, never silent deletion or reinitialization.

## Verification and rollback

Linux isolated route/worker tests and portable inherited suites are described in the
accompanying evidence packet. No network listener or real browser was used for those
tests. Fresh worker processes and a recreated Flask app prove that subset of reopening;
they do not certify actual Windows shortcut/server/browser shutdown and restart.
Independent exact-commit review, native Windows tests and actual browser acceptance
are still required. Do not claim the legacy dashboard itself was repaired.

Required inherited Windows command, in this disposable checkout:

    python -B scripts/run_windows_offline_tests.py

Do not merge, deploy, enable providers/autonomy, change credentials or protected gates,
or touch the legacy pilot on port 5065. Rollback is to abandon this isolated checkout
or reverse the five-path patch after checking for subsequent overlapping changes.
Keep its fictional store/evidence until a deliberate retention decision.
