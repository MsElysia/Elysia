# Elysia restricted local console candidate

**Release STOP. Linux runtime demonstrated; native Windows acceptance pending.**
This is a runnable integration candidate, not the full personal AI or a replacement for an existing Windows installation. It uses deterministic source recall, not a language model. Memory remains fictional-only with seven learned revisions per store. Providers, network access and autonomy remain disabled.

## Start

Extract the candidate ZIP into a **new directory**. Do not overwrite another checkout or copy real memory into it. Python **3.12 or newer** must already be installed and available as `python` (or in `.venv\Scripts\python.exe`). The console has no third-party runtime dependencies.

In that directory, run one Windows command:

```bat
"Start Project Guardian.bat"
```

From PowerShell, use `& '.\Start Project Guardian.bat'`.
The terminal is the operator interface. Do not close it until `/exit` reports shutdown complete.

Try these commands:

```text
/status
/calculate (12 * 8) - 20
/teach lantern | Fictional moonberry lantern color is violet.
moonberry lantern color
/correct lantern | Fictional moonberry lantern color is amber.
/history lantern
/research Skylark Composite
/exit
```

Expected: calculation 76; violet recalled; amber saved as a second revision; both revisions retained; three controlled research sources preserved with a reported conflict; clean shutdown. Research uses bundled fictional documents, not the internet. Arithmetic accepts numbers, parentheses and + - * / only, with bounded expression size and magnitude; it does not save the expression or execute code.

Run the same launch command again and ask `moonberry lantern color`. It should recall amber. `/status` identifies the current process, exact synthetic store, revision count and disabled capabilities. `/restart` reopens the in-process recall interface; `/exit` followed by the launch command is a **fresh process restart**.

Named memory lives at `.synthetic-pilot-stores\windows-pilot` beneath this extracted copy. A second console from the same checkout is refused before writing memory. Separate copies are separate installations/stores. Ownership uses OS locks, not a PID file; no unrelated process is stopped.

For Linux verification of the same restricted script path:

```sh
python -S -B elysia.py --interactive --synthetic-store windows-pilot
```

## Evidence and limitations

The repository integration branch is `integration/windows-local-delivery-20261028`, based on `5e2ebe74152ac354202e71cd569e7284e1056658`. The packaged `SOURCE_MANIFEST.json` records the exact final source commit and SHA-256 of every included file. It identifies bytes; it does not certify Windows behavior.

Integrated: existing Windows command wrappers, restricted lifecycle, transactional fictional store, source-linked recall/research, durable acknowledgment checks, exclusive checkout ownership, truthful status, and bounded arithmetic. The earlier browser receipt repair is now enforced in the shared store used by the console too. The separate provider-chat commits `570cc36` and `6d1e74b` remain preserved on the PR161 lane and are intentionally outside this provider-disabled runtime.

Observed in actual Linux terminal sessions: calculate 76; teach violet; recall violet; correct to amber; retain both revisions; research three fixed sources; exit 0; relaunch and recall amber; duplicate launch refused with exit 2 while the owner continues. Tests additionally exercise corruption refusal, crash-release/reopen, byte preservation and uncertain ownership-release failure. The success receipt is emitted only after ownership release succeeds.

Independent review found two issues (unbounded calculator rendering and premature shutdown success); both were repaired and covered by executable regressions. The independent agent could not finish the final re-review due to its usage limit. Final verification is therefore primary-executed, not an independent final PASS.

Native Windows mutex/launcher/junction behavior, hostile filesystem swap races, power-loss durability, full Guardian/MemoryCore integration, general chat, personal-memory imports, and the desktop shortcut are **not certified** by this candidate. No existing port 5065/5066 process is used or modified.

A newer owner-local Windows candidate was reported at `4f69bd12eaa30f8aa83e3c731359d9c7ea626e50` on `cursor/windows-integration-20261028`. GitHub commit lookup and branch search did not find it, and a fetch rejected that ref. Its reported Windows success is not independently verified here. **Compare with that existing work before applying any of this candidate to the owner's installation.** This archive does not supersede it.

## Native Windows verification

With pytest available in a separate development environment, from the new extracted directory:

```bat
python -B -m pytest --noconftest tests/test_delivery_runtime.py -q -p no:cacheprovider
```

This suite invokes the real default `.bat` for the workflow on Windows and uses directly owned Python subprocesses for crash tests. It creates temporary copied closures; it does not use the named operator store. Record source commit, command, exit code and output. No skips count as Windows passes.

For the complete repository checkout, also run `python -B scripts/run_windows_offline_tests.py` and the restricted-browser regression suite if accepting that optional interface. The minimal console ZIP does not include the optional Flask browser or unrelated legacy backend.

## Recovery and rollback

If ownership is refused, close the existing console using `/exit`; do not delete locks or kill by guessed PID. After an interrupted save, relaunch the same synthetic store and inspect history before retrying; the existing transaction recovery runs before serving data. If corrupted state is refused, preserve its bytes and stop using that store; no automatic reset is performed.

Rollback of a new extracted candidate is to exit it and retain the folder for inspection. It has not replaced an existing installation. Restore source only by reverting the integration commit or returning to its recorded base after preserving later work; never delete original user memory. No merge, push, deployment or provider activation is included.
