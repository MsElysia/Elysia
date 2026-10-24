# Restricted Windows development pilot

Double-click `Start Project Guardian.bat`. An existing Python 3 installation
must be on PATH. The launcher runs the restricted interactive application;
it does not start providers, HTTP services, models or background schedulers.

Use fictional data only. The named synthetic store is
`.synthetic-pilot-stores/windows-pilot` in this checkout, separate from real
user data. Exit with `/exit`, then launch the same batch file again to recall
committed information.

Example session:

```text
water seedlings
/teach lantern | Fictional moonberry lantern color is violet.
What color is the moonberry lantern?
/correct lantern | Fictional moonberry lantern color is amber.
/history lantern
/research Skylark Composite
What did you learn about protecting Skylark Composite?
Skylark Composite price
/exit
```

After relaunch, ask `Tell me the moonberry lantern color` and
`Skylark Composite protective treatment`. Current facts exclude superseded
revisions; `/history` retains them. Research preserves exact synthetic fixture
bytes, identifiers, hashes and source history. It reports conflicting claims
and unavailable information. These are deterministic evidence-based excerpts,
not general model reasoning or live internet research. Research currently
supports the bounded Skylark fixtures; conversational history has an existing
limit of seven learned revisions plus three initial sample records.

The authoritative writers are `SyntheticLearningStore` for conversational
records and correction indexes, `run_offline_research` for research evidence,
and `offline_research_pilot` for derived mission receipts. They reuse the same
memory-intelligence format and `ApplyTransaction` while retaining separate
conversation and research destinations. No replacement database was added.

Run the complete applicable suite with the existing development Python:

```text
python -B scripts/run_windows_offline_tests.py
```

The runner includes actual Windows launcher/restart/failure tests, evidence
and transaction regressions, and main's existing orchestration tests with
stub providers. It disables repository-wide legacy fixtures and live network
operations. Windows asyncio's own temporary loopback socketpair is permitted
only in the outer test harness; the application guard is unchanged. This is
the restricted application's suite, not full historical CI or merge approval.

Main's orchestration, consensus, FractalMind and legacy runtime bodies remain
preserved. Full Brain preview, legacy services, live learning and autonomous
execution remain outside this pilot. Protected activation and merge gates
remain closed.
