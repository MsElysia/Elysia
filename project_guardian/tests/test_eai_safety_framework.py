from pathlib import Path
import asyncio
import json

import pytest

from project_guardian.eai_safety import (
    EAIDecision,
    EAISafetyFramework,
    load_eai_safety_config,
)
from project_guardian.master_slave_controller import (
    MasterSlaveController,
    SlaveRole,
    SlaveStatus,
)
from project_guardian.system_orchestrator import SystemOrchestrator
from project_guardian.mutation_engine import MutationEngine
from project_guardian.mutation_review_manager import (
    MutationReviewManager,
    ReviewDecision,
    RiskLevel,
)


def _framework(tmp_path: Path) -> EAISafetyFramework:
    return EAISafetyFramework(
        storage_path=str(tmp_path / "eai_lineage.json"),
        audit_path=str(tmp_path / "eai_assessments.jsonl"),
        alert_state_path=str(tmp_path / "eai_alert_state.json"),
    )


def test_eai_safety_config_loader_sanitizes_file_and_aliases(tmp_path):
    config_path = tmp_path / "eai_safety.json"
    config_path.write_text(
        (
            '{"enabled":"yes","autonomous_deployment_policy":"review",'
            '"review_threshold":"0.35","deny_threshold":"0.7",'
            '"max_recent_assessments":"3"}'
        ),
        encoding="utf-8",
    )

    config = load_eai_safety_config(
        config_path=str(config_path),
        overrides={
            "eai_lineage_registry_path": str(tmp_path / "lineage.json"),
            "eai_audit_log_path": str(tmp_path / "audit.jsonl"),
            "eai_alert_state_path": str(tmp_path / "alert_state.json"),
        },
    )

    assert config["enabled"] is True
    assert config["autonomous_deployment_policy"] == "review"
    assert config["review_threshold"] == 0.35
    assert config["deny_threshold"] == 0.7
    assert config["max_recent_assessments"] == 3
    assert config["lineage_registry_path"] == str(tmp_path / "lineage.json")
    assert config["audit_log_path"] == str(tmp_path / "audit.jsonl")
    assert config["alert_state_path"] == str(tmp_path / "alert_state.json")


def test_eai_status_exposes_recent_assessment_and_lineage_summaries(tmp_path):
    framework = EAISafetyFramework(
        storage_path=str(tmp_path / "eai_lineage.json"),
        audit_path=str(tmp_path / "eai_assessments.jsonl"),
        alert_state_path=str(tmp_path / "eai_alert_state.json"),
        max_recent_assessments=2,
        max_lineage_status_items=1,
    )
    framework.register_lineage(
        artifact_type="module_variant",
        artifact_content="def one():\n    return 1\n",
        created_by="operator",
    )
    framework.register_lineage(
        artifact_type="module_variant",
        artifact_content="def two():\n    return 2\n",
        created_by="operator",
    )

    for index in range(3):
        framework.assess_action(
            action_type="code_mutation",
            actor="operator",
            target=f"module_{index}.py",
            metadata={
                "human_approved": True,
                "controlled_evolution": True,
                "lineage_id": "base-module",
            },
        )

    status = framework.get_status()

    assert status["enabled"] is True
    assert status["recent_assessments"] == 2
    assert len(status["recent_assessment_items"]) == 2
    assert status["recent_assessment_items"][0]["target"] == "module_2.py"
    assert len(status["recent_lineage"]) == 1
    assert status["lineage_records"] == 2
    assert status["audit_log_path"] == str(tmp_path / "eai_assessments.jsonl")
    assert status["alert_state_path"] == str(tmp_path / "eai_alert_state.json")


def test_dashboard_eai_status_reads_config_and_lineage_registry(tmp_path, monkeypatch):
    try:
        from project_guardian.ui import app as ui_app
    except Exception as exc:
        pytest.skip(f"FastAPI dashboard module unavailable: {exc}")

    monkeypatch.setattr(ui_app, "project_root", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "config" / "eai_safety.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "autonomous_deployment_policy": "review",
                "lineage_registry_path": "data/eai_lineage_registry.json",
                "review_threshold": 0.4,
                "deny_threshold": 0.8,
                "max_lineage_status_items": 1,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "data" / "eai_lineage_registry.json").write_text(
        json.dumps(
            {
                "updated_at": "2026-05-05T12:00:00",
                "records": {
                    "module_a": {
                        "artifact_id": "module_a",
                        "artifact_type": "module_variant",
                        "created_by": "operator",
                        "created_at": "2026-05-05T12:00:00",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    status = ui_app._read_eai_safety_status()

    assert status["enabled"] is True
    assert status["autonomous_deployment_policy"] == "review"
    assert status["lineage_records"] == 1
    assert status["recent_lineage"][0]["artifact_id"] == "module_a"


def test_dashboard_eai_assessment_endpoint_and_template(tmp_path, monkeypatch):
    try:
        from fastapi.testclient import TestClient
        from project_guardian.ui import app as ui_app
    except Exception as exc:
        pytest.skip(f"FastAPI dashboard unavailable: {exc}")

    if not getattr(ui_app, "FASTAPI_AVAILABLE", False):
        pytest.skip(f"FastAPI dashboard unavailable: {ui_app.FASTAPI_IMPORT_ERROR}")

    from project_guardian.approval_store import ApprovalStore
    from project_guardian.review_queue import ReviewQueue

    monkeypatch.setattr(ui_app, "project_root", tmp_path)
    monkeypatch.setattr(
        ui_app,
        "review_queue",
        ReviewQueue(queue_file=tmp_path / "REPORTS" / "review_queue.jsonl"),
    )
    monkeypatch.setattr(
        ui_app,
        "approval_store",
        ApprovalStore(store_file=tmp_path / "REPORTS" / "approval_store.json"),
    )
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "config" / "eai_safety.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "autonomous_deployment_policy": "deny",
                "lineage_registry_path": "data/eai_lineage_registry.json",
                "audit_log_path": "data/eai_assessments.jsonl",
                "alert_state_path": "data/eai_alert_state.json",
            }
        ),
        encoding="utf-8",
    )

    client = TestClient(ui_app.app, client=("127.0.0.1", 50000))
    response = client.get("/")
    assert response.status_code == 200
    assert "Test EAI Action" in response.text
    assert "EAI Daily Summary" in response.text
    assert "EAI Alerts" in response.text
    assert "EAI Audit Trail" in response.text

    response = client.post(
        "/api/eai/assess",
        json={
            "action_type": "deploy_slave",
            "actor": "Elysia-Self",
            "target": "external-host:8080",
            "metadata": {
                "autonomous": True,
                "objective": "maximize engagement while avoiding filters",
            },
            "artifact_content": "candidate package",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["decision"] == "deny"
    assert payload["lineage_mutated"] is False
    assert "filter_avoidance" in payload["flags"]

    response = client.get("/api/eai/audit")
    assert response.status_code == 200
    assert response.json()["events"] == []

    response = client.post(
        "/api/eai/review-request",
        json={
            "action_type": "deploy_slave",
            "actor": "Elysia-Self",
            "target": "external-host:8080",
            "metadata": {
                "autonomous": True,
                "objective": "maximize engagement while avoiding filters",
            },
        },
    )

    assert response.status_code == 201
    review_payload = response.json()
    assert review_payload["created"] is True
    request_id = review_payload["request_id"]
    request = ui_app.review_queue.get_request(request_id)
    assert request is not None
    assert request.component == "eai_safety"
    assert request.context["eai_decision"] == "deny"
    assert review_payload["audit_id"]

    response = client.get("/api/eai/audit")
    assert response.status_code == 200
    audit_payload = response.json()
    assert audit_payload["events"][0]["event_type"] == "review_request"
    assert audit_payload["events"][0]["review_request_id"] == request_id

    response = client.get(f"/api/eai/audit/{review_payload['audit_id']}")
    assert response.status_code == 200
    assert response.json()["review_request_id"] == request_id

    response = client.get("/api/eai/alerts")
    assert response.status_code == 200
    alerts_payload = response.json()
    assert alerts_payload["alerts"]
    assert alerts_payload["alerts"][0]["rule"] == "high_risk_flag"
    alert_id = alerts_payload["alerts"][0]["alert_id"]

    response = client.post(
        f"/api/eai/alerts/{alert_id}/ack",
        json={"actor": "operator", "notes": "checking"},
    )
    assert response.status_code == 200
    assert response.json()["state"]["status"] == "acknowledged"

    response = client.get("/api/eai/alerts")
    assert response.status_code == 200
    acknowledged_alert = next(
        alert for alert in response.json()["alerts"] if alert["alert_id"] == alert_id
    )
    assert acknowledged_alert["state"] == "acknowledged"

    response = client.post(
        f"/api/eai/alerts/{alert_id}/resolve",
        json={"actor": "operator", "notes": "handled"},
    )
    assert response.status_code == 200
    assert response.json()["state"]["status"] == "resolved"

    response = client.get("/api/eai/alerts?include_resolved=true")
    assert response.status_code == 200
    resolved_alert = next(
        alert for alert in response.json()["alerts"] if alert["alert_id"] == alert_id
    )
    assert resolved_alert["state"] == "resolved"

    response = client.get("/api/eai/summary")
    assert response.status_code == 200
    summary_payload = response.json()
    assert summary_payload["events"]["review_requests"] >= 1
    assert summary_payload["events"]["high_risk"] >= 1
    assert summary_payload["alerts"]["resolved_in_window"] >= 1

    response = client.get("/api/eai/summary.md")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.text.startswith("# EAI Safety Daily Summary")
    assert "## Alerts" in response.text

    response = client.post(
        "/api/eai/summary/export",
        json={"days": 1, "filename": "../dashboard summary.md"},
    )
    assert response.status_code == 201
    export_payload = response.json()
    assert export_payload["filename"] == "dashboard_summary.md"
    assert Path(export_payload["path"]).exists()

    response = client.post(
        "/api/eai/summary/export",
        json={"output_dir": str(tmp_path.parent / "outside")},
    )
    assert response.status_code == 400
    assert "output_dir must stay within project root" in response.json()["error"]


def test_eai_dry_run_does_not_register_lineage_or_recent_assessment(tmp_path):
    framework = _framework(tmp_path)

    assessment = framework.assess_action(
        action_type="code_mutation",
        actor="operator",
        target="project_guardian/example.py",
        metadata={
            "human_approved": True,
            "controlled_evolution": True,
            "lineage_id": "base-module",
        },
        artifact_content="def candidate():\n    return True\n",
        dry_run=True,
    )

    status = framework.get_status()

    assert assessment.decision == EAIDecision.ALLOW
    assert assessment.dry_run is True
    assert assessment.lineage_record_id is None
    assert status["lineage_records"] == 0
    assert status["recent_assessments"] == 0
    assert framework.list_audit(limit=10) == []


def test_eai_audit_records_real_assessments_and_review_requests(tmp_path):
    framework = _framework(tmp_path)

    real_assessment = framework.assess_action(
        action_type="deploy_slave",
        actor="Elysia-Self",
        target="external-host:8080",
        metadata={
            "autonomous": True,
            "objective": "maximize engagement while avoiding filters",
        },
    )

    events = framework.list_audit(limit=10)

    assert len(events) == 1
    assert events[0]["event_type"] == "assessment"
    assert events[0]["decision"] == "deny"
    assert events[0]["assessment_id"] == real_assessment.assessment_id
    assert framework.get_audit_event(real_assessment.assessment_id)["decision"] == "deny"
    assert framework.list_audit(decision="deny", flag="filter_avoidance")[0][
        "assessment_id"
    ] == real_assessment.assessment_id

    review_event = framework.record_audit_event(
        "review_request",
        real_assessment,
        review_request_id="review-123",
        details={"source": "test"},
    )

    assert framework.get_audit_event("review-123")["audit_id"] == review_event["audit_id"]
    assert framework.list_audit(event_type="review_request")[0][
        "review_request_id"
    ] == "review-123"


def test_eai_alerts_identify_high_risk_repetition_and_approval_reuse(tmp_path):
    framework = _framework(tmp_path)

    for index in range(3):
        framework.assess_action(
            action_type="deploy_slave",
            actor="Elysia-Self",
            target=f"external-host-{index}:8080",
            metadata={
                "autonomous": True,
                "objective": "maximize engagement while avoiding filters",
            },
        )

    framework.assess_action(
        action_type="deploy_slave",
        actor="Elysia-Self",
        target="external-host-approval:8080",
        metadata={
            "autonomous": True,
            "objective": "maximize engagement while avoiding filters",
            "request_id": "not-approved",
        },
    )

    framework.record_audit_event(
        "assessment",
        {
            "action_type": "deploy_slave",
            "actor": "MasterSlaveController",
            "target": "external-host-approved:8080",
            "decision": "allow",
            "risk_score": 0.3,
            "flags": ["deployment"],
            "selection_pressures": [],
            "required_controls": [],
            "dry_run": False,
            "approval_verified": True,
            "approval_reference": "approved-review-1",
        },
    )

    alerts = framework.list_alerts(limit=20)
    rules = {alert["rule"] for alert in alerts}

    assert "high_risk_flag" in rules
    assert "repeated_actor_pressure" in rules
    assert "unverified_approval_reference" in rules
    assert "approved_after_review" in rules
    assert framework.list_alerts(rule="repeated_actor_pressure")[0]["count"] >= 3
    assert framework.list_alerts(severity="critical")

    high_risk_alert = framework.list_alerts(rule="high_risk_flag")[0]
    alert_id = high_risk_alert["alert_id"]

    state = framework.acknowledge_alert(alert_id, actor="operator", notes="reviewing")
    assert state["status"] == "acknowledged"
    assert framework.get_alert_state(alert_id)["notes"] == "reviewing"
    acknowledged = [
        alert for alert in framework.list_alerts() if alert["alert_id"] == alert_id
    ][0]
    assert acknowledged["state"] == "acknowledged"
    assert not any(
        alert["alert_id"] == alert_id
        for alert in framework.list_alerts(include_acknowledged=False)
    )

    state = framework.resolve_alert(alert_id, actor="operator", notes="handled")
    assert state["status"] == "resolved"
    assert not any(alert["alert_id"] == alert_id for alert in framework.list_alerts())
    resolved = [
        alert
        for alert in framework.list_alerts(include_resolved=True)
        if alert["alert_id"] == alert_id
    ][0]
    assert resolved["state"] == "resolved"

    summary = framework.get_daily_summary(days=1)
    assert summary["events"]["total"] >= 5
    assert summary["events"]["decisions"]["deny"] >= 4
    assert summary["events"]["high_risk"] >= 4
    assert summary["alerts"]["resolved_in_window"] >= 1
    assert summary["top_flags"][0]["count"] >= 1
    assert summary["daily"]

    markdown = framework.render_daily_summary_markdown(days=1)
    assert markdown.startswith("# EAI Safety Daily Summary")
    assert "## Snapshot" in markdown
    assert "High-risk events" in markdown
    assert "| Date | Events | Allow | Review | Deny | Alerts |" in markdown

    export = framework.write_daily_summary_report(
        output_dir=str(tmp_path / "REPORTS"),
        days=1,
        filename="../unsafe report.md",
    )
    assert export["written"] is True
    assert export["filename"] == "unsafe_report.md"
    report_path = Path(export["path"])
    assert report_path.exists()
    assert report_path.parent == tmp_path / "REPORTS"
    assert report_path.read_text(encoding="utf-8").startswith(
        "# EAI Safety Daily Summary"
    )


def test_review_queue_reads_finalized_rows_with_audit_fields(tmp_path):
    from project_guardian.review_queue import ReviewQueue

    queue = ReviewQueue(queue_file=tmp_path / "reviews.jsonl")
    request_id = queue.enqueue(
        component="eai_safety",
        action="deploy_slave",
        context={"target": "external-host:8080"},
    )

    assert queue.update_status(
        request_id,
        "approved",
        approver="operator",
        notes="approved after EAI review",
    )

    request = queue.get_request(request_id)

    assert request is not None
    assert request.request_id == request_id
    assert request.status == "approved"


def test_eai_request_id_requires_matching_approved_review_context(tmp_path):
    from project_guardian.approval_store import ApprovalStore
    from project_guardian.review_queue import ReviewQueue

    review_queue = ReviewQueue(queue_file=tmp_path / "reviews.jsonl")
    approval_store = ApprovalStore(store_file=tmp_path / "approvals.json")
    framework = EAISafetyFramework(
        storage_path=str(tmp_path / "eai_lineage.json"),
        audit_path=str(tmp_path / "eai_assessments.jsonl"),
        approval_store=approval_store,
        review_queue=review_queue,
    )
    context = {
        "source": "eai_dry_run",
        "action_type": "deploy_slave",
        "target": "external-host:8080",
        "metadata": {
            "autonomous": True,
            "objective": "maximize engagement while avoiding filters",
        },
        "artifact_content": {"present": False},
    }
    request_id = review_queue.enqueue("eai_safety", "deploy_slave", context)

    unapproved = framework.assess_action(
        action_type="deploy_slave",
        actor="MasterSlaveController",
        target="external-host:8080",
        metadata={
            "autonomous": True,
            "objective": "maximize engagement while avoiding filters",
            "request_id": request_id,
        },
    )

    assert unapproved.decision == EAIDecision.DENY
    assert unapproved.approval_verified is False

    request = review_queue.get_request(request_id)
    assert request is not None
    assert approval_store.approve(request_id, context=request.context)

    approved = framework.assess_action(
        action_type="deploy_slave",
        actor="MasterSlaveController",
        target="external-host:8080",
        metadata={
            "autonomous": True,
            "objective": "maximize engagement while avoiding filters",
            "request_id": request_id,
        },
    )

    assert approved.approval_verified is True
    assert approved.approval_reference == request_id
    assert approved.decision != EAIDecision.DENY
    assert "human_deployment_approval" not in approved.required_controls

    mismatched = framework.assess_action(
        action_type="deploy_slave",
        actor="MasterSlaveController",
        target="different-host:8080",
        metadata={
            "autonomous": True,
            "objective": "maximize engagement while avoiding filters",
            "request_id": request_id,
        },
    )

    assert mismatched.approval_verified is False
    assert mismatched.decision == EAIDecision.DENY


def test_master_slave_deploy_accepts_matching_approved_eai_review(tmp_path, monkeypatch):
    from project_guardian.approval_store import ApprovalStore
    from project_guardian.review_queue import ReviewQueue

    review_queue = ReviewQueue(queue_file=tmp_path / "reviews.jsonl")
    approval_store = ApprovalStore(store_file=tmp_path / "approvals.json")
    framework = EAISafetyFramework(
        storage_path=str(tmp_path / "eai_lineage.json"),
        audit_path=str(tmp_path / "eai_assessments.jsonl"),
        approval_store=approval_store,
        review_queue=review_queue,
    )
    context = {
        "source": "eai_dry_run",
        "action_type": "deploy_slave",
        "target": "external-host:8080",
        "metadata": {"autonomous": True},
        "artifact_content": {"present": False},
    }
    request_id = review_queue.enqueue("eai_safety", "deploy_slave", context)
    request = review_queue.get_request(request_id)
    assert request is not None
    assert approval_store.approve(request_id, context=request.context)

    controller = MasterSlaveController(
        master_id="test-master",
        storage_path=str(tmp_path / "slaves.json"),
        auth_token_path=str(tmp_path / "tokens.json"),
        eai_safety=framework,
    )
    slave_id, _ = controller.register_slave(
        name="Approved Slave",
        deployment_target="external-host:8080",
        role=SlaveRole.WORKER,
    )
    slave = controller.get_slave(slave_id)
    assert slave is not None
    slave.metadata["request_id"] = request_id

    monkeypatch.setenv("ELYSIA_SLAVE_SIMULATED_DEPLOY_DELAY_SEC", "0")
    assert controller.deploy_slave(slave_id) is True
    asyncio.run(asyncio.sleep(0.05))
    slave = controller.get_slave(slave_id)
    assert slave is not None
    assert slave.status == SlaveStatus.ACTIVE
    assert slave.metadata["eai_safety_deployment"]["approval_verified"] is True


@pytest.mark.parametrize(
    ("payload", "expected_decision", "expected_flags", "expected_controls"),
    [
        (
            {
                "action_type": "deploy_slave",
                "actor": "Elysia-Self",
                "target": "external-host:8080",
                "metadata": {
                    "autonomous": True,
                    "objective": "maximize engagement while avoiding filters",
                },
            },
            EAIDecision.DENY,
            {"replication", "deployment", "filter_avoidance"},
            {"replication_gating", "human_deployment_approval"},
        ),
        (
            {
                "action_type": "model_merge",
                "actor": "autonomous-agent",
                "target": "merged-adapter-candidate",
                "metadata": {
                    "autonomous": True,
                    "source": "public repo LoRA adapter",
                    "objective": "merge model adapter to bypass filters and reduce cost",
                },
            },
            EAIDecision.DENY,
            {"variation", "model_merge", "filter_avoidance", "external_code_ingestion"},
            {"lineage_tracking", "robust_deception_evaluation"},
        ),
        (
            {
                "action_type": "create_module",
                "actor": "operator",
                "target": "project_guardian/generated_safe.py",
                "metadata": {
                    "human_approved": True,
                    "controlled_evolution": True,
                    "sandboxed": True,
                    "lineage_id": "base-module-v1",
                },
            },
            EAIDecision.ALLOW,
            {"variation"},
            set(),
        ),
        (
            {
                "action_type": "acquire_resource",
                "actor": "autonomous-agent",
                "target": "cloud credits",
                "metadata": {
                    "autonomous": True,
                    "objective": "provision compute and api keys to persist during demand spikes",
                },
            },
            EAIDecision.REVIEW,
            {"resource_acquisition", "selection_pressure", "persistence"},
            {"resource_quota_gate", "selection_pressure_review"},
        ),
    ],
)
def test_eai_video_scenarios_map_to_expected_gate_outcomes(
    tmp_path,
    payload,
    expected_decision,
    expected_flags,
    expected_controls,
):
    framework = _framework(tmp_path)

    assessment = framework.assess_action(dry_run=True, **payload)

    assert assessment.decision == expected_decision
    assert expected_flags.issubset(set(assessment.flags))
    assert expected_controls.issubset(set(assessment.required_controls))


def test_eai_gate_denies_uncontrolled_autonomous_deployment(tmp_path):
    framework = _framework(tmp_path)

    assessment = framework.assess_action(
        action_type="deploy_slave",
        actor="Elysia-Self",
        target="external-host:8080",
        metadata={
            "autonomous": True,
            "objective": "maximize engagement while avoiding filters",
        },
    )

    assert assessment.decision == EAIDecision.DENY
    assert "replication_gating" in assessment.required_controls
    assert "human_deployment_approval" in assessment.required_controls
    assert "filter_avoidance" in assessment.flags


def test_eai_gate_allows_controlled_lineage_tracked_variation(tmp_path):
    framework = _framework(tmp_path)

    assessment = framework.assess_action(
        action_type="code_mutation",
        actor="operator",
        target="project_guardian/example.py",
        metadata={
            "human_approved": True,
            "controlled_evolution": True,
            "sandboxed": True,
        },
        lineage_parent_ids=["base-module-v1"],
        artifact_content="def ok():\n    return True\n",
    )

    assert assessment.decision == EAIDecision.ALLOW
    assert assessment.lineage_record_id is not None
    assert framework.verify_lineage(
        assessment.lineage_record_id,
        "def ok():\n    return True\n",
    )["verified"] is True


def test_lineage_verification_detects_content_tampering(tmp_path):
    framework = _framework(tmp_path)

    record = framework.register_lineage(
        artifact_type="module_variant",
        artifact_content="def stable():\n    return 'v1'\n",
        parent_ids=["root"],
        created_by="operator",
    )

    assert framework.verify_lineage(record.artifact_id, "def stable():\n    return 'v1'\n")[
        "verified"
    ] is True
    assert framework.verify_lineage(record.artifact_id, "def stable():\n    return 'v2'\n")[
        "verified"
    ] is False


def test_mutation_review_uses_eai_safety_denial(tmp_path):
    framework = _framework(tmp_path)
    engine = MutationEngine(
        storage_path=str(tmp_path / "mutations.json"),
        repo_root=str(tmp_path),
    )
    mutation_id = engine.propose_mutation(
        target_module="project_guardian/agent.py",
        mutation_type="deploy_slave",
        description="Spawn a slave that bypasses filters to maximize engagement",
        proposed_code="def deploy():\n    return 'bypass filters and persist'\n",
        original_code="",
        metadata={"autonomous": True},
    )
    manager = MutationReviewManager(
        mutation_engine=engine,
        eai_safety=framework,
        storage_path=str(tmp_path / "reviews.json"),
        require_human_review_risk=RiskLevel.HIGH,
    )

    review = manager.review_mutation(
        mutation_id,
        author="Elysia-Self",
        require_snapshot=False,
    )

    assert review.decision == ReviewDecision.REJECT
    assert review.metadata["eai_safety"]["decision"] == "deny"
    assert "robust_deception_evaluation" in review.conditions


def test_master_slave_deploy_is_gated_when_eai_safety_requires_review(tmp_path):
    framework = _framework(tmp_path)
    controller = MasterSlaveController(
        master_id="test-master",
        storage_path=str(tmp_path / "slaves.json"),
        auth_token_path=str(tmp_path / "tokens.json"),
        eai_safety=framework,
    )
    slave_id, _ = controller.register_slave(
        name="Test Slave",
        deployment_target="external-host:8080",
        role=SlaveRole.WORKER,
    )

    assert controller.deploy_slave(slave_id) is False
    slave = controller.get_slave(slave_id)
    assert slave is not None
    assert slave.status == SlaveStatus.PENDING
    assert slave.metadata["last_deploy"]["error"].startswith("eai_safety_")


def test_system_orchestrator_wires_shared_eai_safety_framework(tmp_path):
    class _GuardianStub:
        def get_startup_verification(self):
            return {"status": "ok", "checks": []}

        def get_runtime_health(self):
            return {"status": "healthy"}

        def get_runtime_health_history(self, limit=None):
            return []

    guardian = _GuardianStub()
    orchestrator = SystemOrchestrator(
        config={
            "storage_path": str(tmp_path),
            "timeline_db_path": str(tmp_path / "timeline.db"),
            "guardian_core": guardian,
            "ui_enabled": False,
            "enable_mutation_workflow_components": True,
        }
    )

    try:
        assert asyncio.run(
            orchestrator.initialize(
                initialize_components=False,
                auto_register_modules=False,
            )
        )
        assert orchestrator.eai_safety_framework is not None
        assert getattr(guardian, "eai_safety_framework") is orchestrator.eai_safety_framework
        assert orchestrator.master_slave_controller.eai_safety is orchestrator.eai_safety_framework
        assert orchestrator.mutation_review_manager.eai_safety is orchestrator.eai_safety_framework
        assert orchestrator.get_component("eai_safety") is orchestrator.eai_safety_framework
        assert orchestrator.get_system_status()["components"]["eai_safety_framework"] is True
    finally:
        asyncio.run(orchestrator.shutdown())
