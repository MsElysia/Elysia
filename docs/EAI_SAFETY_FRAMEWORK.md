# Evolvable AI Safety Framework

Project Guardian should treat Evolvable AI risk as a control problem over three levers:
reproduction, variation, and deployment. The implementation should not create an
evolution loop. It should gate the existing places where Elysia already mutates code,
creates modules, and deploys slave instances.

## Implementation Map

- `project_guardian/eai_safety.py` provides `EAISafetyFramework`.
- `config/eai_safety.json` stores the default gate policy, thresholds, lineage
  registry location, append-only audit log location, and alert state location.
- Mutation review can attach the framework through `MutationReviewManager(eai_safety=...)`.
- Auto-created modules can attach it through `AutoModuleCreator(eai_safety=...)`.
- Master/slave deployment can attach it through `MasterSlaveController(eai_safety=...)`
  or `SlaveDeployment(eai_safety=...)`.
- The Flask API exposes `/api/eai/status`, `POST /api/eai/assess`,
  `POST /api/eai/review-request`, `/api/eai/summary`, `/api/eai/summary.md`,
  `/api/eai/alerts`, `/api/eai/audit`, `/api/eai/audit/<id>`,
  `/api/eai/lineage`, and `/api/eai/lineage/<artifact_id>`.
- The local FastAPI dashboard shows EAI gate status, deployment policy, thresholds,
  lineage count, audit event count, recent variants, a dry-run "Test EAI Action"
  panel, daily safety summary, computed EAI alerts, recent audit events, and a button
  to turn REVIEW/DENY outcomes into human review requests.

## Controls

- Replication gating: autonomous deployment, cloning, slave spawning, persistence, and
  resource acquisition require human approval or a controlled-evolution marker.
- Lineage tracking: generated modules, mutation outputs, agent packages, and model
  variants can be registered with parent IDs, content fingerprints, and provenance
  signatures.
- Robust evaluation: deception, camouflage, hidden triggers, filter avoidance, and
  test-conditional behavior become review or denial flags.
- Selection pressure review: engagement metrics, cost-only optimization, filter
  avoidance, resource competition, and persistence objectives raise risk because they
  can select for unsafe traits.
- Audit trail: real runtime assessments are appended to `audit_log_path`, while pure
  dry-runs stay out of the log. If a dry-run is converted into a human review request,
  that handoff is recorded as a `review_request` audit event with the request ID.
- Alerts: `/api/eai/alerts` computes read-only signals over recent audit events,
  including high-risk flags, repeated REVIEW/DENY pressure by actor or target,
  unverified approval-reference attempts, and actions allowed by verified human
  review. Operators can mark computed alerts acknowledged or resolved through
  `/api/eai/alerts/<alert_id>/ack` and `/api/eai/alerts/<alert_id>/resolve`.
- Daily summary: `/api/eai/summary` rolls up recent audit and alert state into
  operator-friendly counts: decisions, high-risk events, top flags, top actors,
  alert severities, and acknowledgement/resolution activity.
- Markdown report: `/api/eai/summary.md` renders the same summary as a portable
  Markdown report for operator notes, changelogs, or daily logs.
- Report export: `POST /api/eai/summary/export` writes the Markdown report to disk
  (default `REPORTS/eai_safety_summary_<timestamp>.md`) and returns the saved path.

## Intended Use

Wire a single framework instance at runtime:

```python
from project_guardian.eai_safety import configure_eai_safety_framework

eai_safety = configure_eai_safety_framework(
    guardian=guardian,
    config_path="config/eai_safety.json",
)
guardian.mutation_review_manager.eai_safety = eai_safety
guardian.master_slave_controller.eai_safety = eai_safety
```

The safe default is to deny uncontrolled autonomous deployment. Controlled lab-style
variation remains possible when it is sandboxed, reviewed, lineage-tracked, and tied to
operator approval.

Dry-run assessments should use `dry_run=True` or `POST /api/eai/assess`. They return
the same decision, flags, and controls as the runtime gate without registering lineage
or deploying anything. `POST /api/eai/review-request` repeats that dry-run assessment
and stores the context in the existing append-only review queue when the result is
REVIEW or DENY. The matching audit event can be queried from `/api/eai/audit` or
`/api/eai/audit/<audit_or_assessment_or_review_id>`.

Computed alerts are intentionally non-authoritative; enforcement still happens in the
gate. They are a dashboard and API lens for deciding what a human should inspect next.
Acknowledgement state is stored separately from the audit trail, so resolving an alert
does not rewrite or hide the underlying safety record.

At enforcement time, `request_id`, `review_id`, and `approval_id` are not trusted by
themselves. The framework only treats them as human approval when the ID is approved
in `ApprovalStore`, belongs to an `eai_safety` review request, and the queued review
context still matches the current action target, action type, metadata, and artifact
fingerprint when one was reviewed.

`GuardianCore` and `SystemOrchestrator` both attach the shared `ReviewQueue` and
`ApprovalStore` to the EAI framework so API-created review requests and later runtime
checks use the same approval records.
