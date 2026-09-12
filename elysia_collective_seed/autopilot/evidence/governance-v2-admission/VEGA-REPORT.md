# Independent Vega Breaker Report — Governance v2 Trusted Admission

## Verdict

**VEGA PASS** for exact immutable candidate `7b076548751e72879d0632c1ec687e087e43a7b8` only.

I did not find a way for an unauthorized worker to become a trusted root or to change objective/action admission without a fail-closed block. I also did not find a material specification defect in the admission and migration contract at this commit.

This verdict covers the specification-and-test boundary. It does not assert that production runtime enforcement, release authorization, external-write enforcement, or a human trust anchor exists.

## Isolation and provenance

- Source repository: `C:\Users\Owner\Project guardian`
- Candidate branch named by the assignment: `codex/governance-v2-trusted-admission`
- Exact reviewed commit: `7b076548751e72879d0632c1ec687e087e43a7b8`
- Commit subject: `fix(governance): validate exact v1 migration inputs`
- Review worktree: `C:\Users\Owner\guardian-v2-admission-vega-7b07654`
- Worktree state: detached at the exact commit and clean after verification
- Independent evidence: `C:\Users\Owner\guardian-v2-admission-vega-evidence-7b07654`

I did not edit the candidate, candidate branch, or candidate files. I did not activate runtime behavior, change Issue 23 or PR 34 semantics, merge, release, or deploy.

Earlier Vega reports for `a4cc2f82...`, `518f9f85...`, and `caf735ba...` remain historical FAIL evidence. Their verdicts were not transferred to this commit. Every prior breaker was rerun against this exact candidate, together with new repair-focused attacks.

## Material reviewed

I independently read the applicable `AGENTS.md` instructions, the candidate commit stack and diff, the governance v2 specification and handoff, the v1 and v2 JSON schemas, the authority manifest schema, the admission/migration implementation, the checkpoint reference implementation, and the candidate tests.

The preserved v1 schema was also compared to the original PR 32 Git object. Both resolve to blob `b5aa1fed58ff86b5a79ef49f51049476e8c14473`; the comparison returned `exact_v1_schema_match=True`.

## Independent breaker results

The external breaker corpus contains four files under `breaker_tests` and is outside the candidate worktree:

- `test_round1_breakers.py`
- `test_round2_repair_edges.py`
- `test_round3_exact_v1_and_root.py`
- `test_final_repair_probes.py`

Result: **151 passed in 0.79s**.

The corpus exercised the following failure surfaces:

- Unknown, downgrade, and forward schema versions.
- Strict source, manifest, and target version typing, including booleans, floats, and strings.
- Snapshot generation rollback and malformed minimum-generation inputs.
- Stale or wrong source digests and stale worker-supplied pins.
- Malformed JSON-like legacy snapshots, manifests, admissions, authorities, lineage records, gates, evidence, and entity identifiers.
- Empty legacy entity sets and incomplete legacy blocked-action coverage.
- Exact v1-schema preservation and enforcement, including unknown fields and malformed lineage.
- Duplicate or conflicting authorities, gates, admissions, root evidence, and graph records.
- Validation of every supplied authority record, including malformed authorities not selected by an admission.
- Malformed manifest authority references and unregistered per-admission authorities.
- Missing parents, cycles, disconnected invalid records, missing gates, and dropped objectives or lineage.
- Missing or malformed root evidence, including wrong container/member types, blank strings, whitespace-only strings, and duplicates.
- RFC 3339 timezone requirements, offset bounds, calendar bounds, hours, minutes, seconds, leap seconds, and ASCII-only digits.
- Worker proposals attempting to alter trusted root, objective, action, or authority limitations.
- No-match authorization and semantic-probe behavior.
- Independent Git-lineage and governance-lineage restacks.
- Release-unavailable, external-enforcement, and repository-lineage claims.
- All consequential migrated actions: semantic code write, repository write, integration, merge, deploy, external write, permission change, and private-data access.

All malformed public migration inputs in this corpus were normalized to documented `AdmissionError` results. No `KeyError`, `TypeError`, `ValueError`, or `RecursionError` escaped the public migration boundary.

## Security conclusions

The current contract fails closed in the tested threat model:

1. A worker-supplied digest or authority identifier is data, not proof of trust. Trust must resolve through the validated authority manifest and evidence chain.
2. Exact v1 validation occurs before conversion. A shape that merely resembles a legacy snapshot cannot acquire v2 meaning through migration.
3. Every supplied authority is schema-validated, and duplicate identifiers are rejected. Invalid unused records cannot hide in the manifest.
4. The migrated target is schema-validated and semantically probed through the admission evaluator. Invalid disconnected graph records are not skipped.
5. Missing gates, objectives, parents, repository lineage, or governance lineage block admission rather than weakening it.
6. Root evidence is explicitly typed and constrained. Empty, blank, duplicated, or non-string references do not establish a trusted root.
7. Version comparison is type-strict, so JSON booleans and floats cannot exploit Python numeric equivalence.
8. Timestamp validation requires an RFC 3339 timezone, checks offset/calendar bounds, and restricts date/time digits to ASCII.
9. No matching admission remains a denial. The contract does not infer authorization from absence of a blocking record.
10. Release remains unavailable and external enforcement remains unenforced unless a separate implemented boundary supplies them.

## Candidate baseline and static verification

Candidate baseline command used the required interpreter:

`C:\Users\Owner\guardian-governance-checkpoint-contract\.venv\Scripts\python.exe`

Result: **414 passed in 4.62s**.

Static checks:

- Contract `compileall`: PASS
- Parse all contract JSON: PASS, 65 files
- Preserved v1 schema Git-object comparison: PASS
- `git diff --check`: PASS
- Detached worktree cleanliness: PASS
- Exact candidate HEAD check: PASS

Environment recorded in the evidence:

- Python 3.13.15
- pytest 9.1.1
- jsonschema 4.26.0

## Evidence files

- `breaker-output.txt` — full independent breaker result
- `full-suite-output.txt` — full candidate baseline result
- `static-checks-output.txt` — compile, JSON, schema identity, diff, HEAD, and cleanliness results
- `breaker_tests/` — independently maintained adversarial tests

## Boundary and next gate

This PASS supports advancing the exact commit to independent architecture review. It is not integration or activation approval. The candidate still documents production enforcement as `NOT_IMPLEMENTED`, the human trust anchor as `UNRESOLVED`, external write enforcement as `NOT_ENFORCED`, and release validation as `UNAVAILABLE`.

Any change to the candidate commit invalidates this verdict and requires a fresh breaker run.
