"""Smoke tests for API/orchestrator compatibility wiring."""

import asyncio

from project_guardian.api_server import APIServer
from project_guardian.approval_store import ApprovalStore
from project_guardian.review_queue import ReviewQueue
from project_guardian.system_orchestrator import SystemOrchestrator


class _GuardianStub:
    def get_startup_verification(self):
        return {"status": "ok", "checks": []}

    def get_runtime_health(self):
        return {"status": "healthy"}

    def get_runtime_health_history(self, limit=None):
        return [{"limit": limit, "status": "healthy"}]


def _build_orchestrator(tmp_path, config_overrides=None):
    guardian = _GuardianStub()
    config = {
        "storage_path": str(tmp_path),
        "timeline_db_path": str(tmp_path / "timeline.db"),
        "guardian_core": guardian,
        "ui_enabled": False,
    }
    if config_overrides:
        config.update(config_overrides)
    orchestrator = SystemOrchestrator(
        config=config
    )
    initialized = asyncio.run(
        orchestrator.initialize(
            initialize_components=False,
            auto_register_modules=False,
        )
    )
    assert initialized is True
    return orchestrator, guardian


def test_system_orchestrator_initializes_api_compatibility_components(tmp_path):
    orchestrator, guardian = _build_orchestrator(tmp_path)

    try:
        assert orchestrator.guardian_core is guardian
        assert orchestrator.mutation_engine is not None
        assert orchestrator.trust_registry is not None
        assert orchestrator.master_slave_controller is not None
        assert orchestrator.revenue_sharing is not None
        assert orchestrator.franchise_manager is not None
        assert orchestrator.task_assignment_engine is not None
        assert orchestrator.implementer_core is not None
        assert orchestrator.mutation_sandbox is None
        assert orchestrator.tool_executor is None
        assert orchestrator.digital_safehouse is None
        assert orchestrator.dream_engine is None
        assert orchestrator.ai_mutation_validator is None
        assert orchestrator.income_executor is None
        assert orchestrator.intelligent_task_distribution is None
        assert orchestrator.proposal_api is None
        assert orchestrator.slave_deployment is None
        assert orchestrator.credit_spend_log is None
        assert orchestrator.error_handler is None
        assert orchestrator.chatgpt_export_import is None
        assert orchestrator.feedback_loop_core is None
        assert orchestrator.file_writer is None
        assert orchestrator.mutation_autonomy_sandbox is None
        assert orchestrator.review_queue is not None
        assert orchestrator.approval_store is not None
        assert orchestrator.eai_safety_framework.review_queue is orchestrator.review_queue
        assert orchestrator.eai_safety_framework.approval_store is orchestrator.approval_store

        task_id = orchestrator.submit_task(lambda: {"ok": True}, priority=4, module="test")

        assert task_id
        assert orchestrator.task_queue.get_queue_size() == 1
    finally:
        asyncio.run(orchestrator.shutdown())


def test_api_server_routes_use_wired_components(tmp_path):
    orchestrator, _guardian = _build_orchestrator(tmp_path)

    try:
        mutation_id = orchestrator.mutation_engine.propose_mutation(
            target_module="project_guardian/example.py",
            mutation_type="feature_add",
            description="Add compatibility smoke test mutation",
            proposed_code="print('hello')\n",
            original_code="",
        )
        orchestrator.trust_registry.register_node("node-alpha", initial_trust=0.9)
        lineage_record = orchestrator.eai_safety_framework.register_lineage(
            artifact_type="module_variant",
            artifact_content="print('hello')\n",
            created_by="api-test",
        )
        orchestrator.review_queue = ReviewQueue(queue_file=tmp_path / "REPORTS" / "review_queue.jsonl")
        orchestrator.approval_store = ApprovalStore(store_file=tmp_path / "REPORTS" / "approval_store.json")
        orchestrator.eai_safety_framework.review_queue = orchestrator.review_queue
        orchestrator.eai_safety_framework.approval_store = orchestrator.approval_store

        server = APIServer(orchestrator=orchestrator, enable_cors=False)
        client = server.app.test_client()

        response = client.get("/api/eai/status")
        assert response.status_code == 200
        eai_status = response.get_json()
        assert eai_status["enabled"] is True
        assert eai_status["lineage_records"] >= 1

        lineage_count = len(orchestrator.eai_safety_framework.list_lineage(limit=100))
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
        assess_payload = response.get_json()
        assert assess_payload["dry_run"] is True
        assert assess_payload["lineage_mutated"] is False
        assert assess_payload["decision"] == "deny"
        assert "filter_avoidance" in assess_payload["flags"]
        assert len(orchestrator.eai_safety_framework.list_lineage(limit=100)) == lineage_count

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
        review_payload = response.get_json()
        assert review_payload["created"] is True
        request = orchestrator.review_queue.get_request(review_payload["request_id"])
        assert request is not None
        assert request.context["eai_decision"] == "deny"
        assert review_payload["audit_id"]

        response = client.get("/api/eai/audit?limit=5")
        assert response.status_code == 200
        audit_payload = response.get_json()
        assert audit_payload["events"][0]["event_type"] == "review_request"
        assert audit_payload["events"][0]["review_request_id"] == review_payload["request_id"]

        response = client.get(f"/api/eai/audit/{review_payload['audit_id']}")
        assert response.status_code == 200
        assert response.get_json()["review_request_id"] == review_payload["request_id"]

        response = client.get("/api/eai/alerts?limit=5")
        assert response.status_code == 200
        alerts_payload = response.get_json()
        assert alerts_payload["alerts"]
        assert alerts_payload["alerts"][0]["rule"] == "high_risk_flag"
        alert_id = alerts_payload["alerts"][0]["alert_id"]

        response = client.post(
            f"/api/eai/alerts/{alert_id}/ack",
            json={"actor": "operator", "notes": "reviewing"},
        )
        assert response.status_code == 200
        assert response.get_json()["state"]["status"] == "acknowledged"

        response = client.post(
            f"/api/eai/alerts/{alert_id}/resolve",
            json={"actor": "operator", "notes": "handled"},
        )
        assert response.status_code == 200
        assert response.get_json()["state"]["status"] == "resolved"

        response = client.get("/api/eai/alerts?include_resolved=true")
        assert response.status_code == 200
        assert any(
            alert["alert_id"] == alert_id and alert["state"] == "resolved"
            for alert in response.get_json()["alerts"]
        )

        response = client.get("/api/eai/summary")
        assert response.status_code == 200
        summary_payload = response.get_json()
        assert summary_payload["events"]["review_requests"] >= 1
        assert summary_payload["events"]["high_risk"] >= 1
        assert summary_payload["alerts"]["resolved_in_window"] >= 1

        response = client.get("/api/eai/summary.md")
        assert response.status_code == 200
        assert response.content_type.startswith("text/markdown")
        assert response.get_data(as_text=True).startswith("# EAI Safety Daily Summary")

        response = client.post(
            "/api/eai/summary/export",
            json={
                "days": 1,
                "output_dir": str(tmp_path / "REPORTS"),
                "filename": "../api summary.md",
            },
        )
        assert response.status_code == 201
        export_payload = response.get_json()
        assert export_payload["filename"] == "api_summary.md"
        assert (tmp_path / "REPORTS" / "api_summary.md").exists()

        response = client.post(
            "/api/eai/summary/export",
            json={"output_dir": str(tmp_path.parent / "outside")},
        )
        assert response.status_code == 400
        assert "output_dir must stay within configured storage" in response.get_json()["error"]

        assert orchestrator.approval_store.approve(
            review_payload["request_id"],
            context=request.context,
        )
        approved_assessment = orchestrator.eai_safety_framework.assess_action(
            action_type="deploy_slave",
            actor="Elysia-Self",
            target="external-host:8080",
            metadata={
                "autonomous": True,
                "objective": "maximize engagement while avoiding filters",
                "request_id": review_payload["request_id"],
            },
            dry_run=True,
        )
        assert approved_assessment.approval_verified is True

        response = client.get("/api/eai/lineage?limit=1")
        assert response.status_code == 200
        lineage_payload = response.get_json()
        assert lineage_payload["limit"] == 1
        assert lineage_payload["records"][0]["artifact_id"] == lineage_record.artifact_id

        response = client.get(f"/api/eai/lineage/{lineage_record.artifact_id}")
        assert response.status_code == 200
        assert response.get_json()["artifact_id"] == lineage_record.artifact_id

        response = client.get("/api/mutations")
        assert response.status_code == 200
        assert response.get_json()["mutations"][0]["mutation_id"] == mutation_id

        response = client.get(f"/api/mutations/{mutation_id}")
        assert response.status_code == 200
        assert response.get_json()["mutation_id"] == mutation_id

        response = client.get("/api/trust/nodes")
        assert response.status_code == 200
        assert response.get_json()["nodes"][0]["node_id"] == "node-alpha"

        response = client.get("/api/trust/nodes/node-alpha")
        assert response.status_code == 200
        assert response.get_json()["node_id"] == "node-alpha"

        response = client.get("/api/franchises")
        assert response.status_code == 200
        assert response.get_json()["franchises"] == []

        response = client.get("/api/revenue/summary")
        assert response.status_code == 200
        assert response.get_json()["total_revenue"] == 0.0

        response = client.get("/api/config/validation")
        assert response.status_code == 200
        assert response.get_json()["status"] == "ok"

        response = client.get("/api/health/runtime")
        assert response.status_code == 200
        assert response.get_json()["status"] == "healthy"

        response = client.post(
            "/api/tasks",
            json={
                "function": "register_node",
                "module": "trust_registry",
                "priority": 7,
                "kwargs": {"node_id": "node-beta", "initial_trust": 0.72},
            },
        )
        assert response.status_code == 201
        assert response.get_json()["success"] is True
        assert response.get_json()["resolved_function"] == "trust_registry.register_node"

        task_id = response.get_json()["task_id"]
        queued_task = orchestrator.task_queue.get_task(task_id)
        assert queued_task is not None
        assert queued_task.func(*queued_task.args, **queued_task.kwargs) == "node-beta"
        assert orchestrator.trust_registry.get_node("node-beta") is not None

        response = client.post(
            "/api/tasks",
            json={
                "function": "get_routing_stats",
                "module": "task_assignment_engine",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "task_assignment_engine.get_routing_stats"
        routing_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert routing_task is not None
        routing_stats = routing_task.func(*routing_task.args, **routing_task.kwargs)
        assert "nodes_registered" in routing_stats

        response = client.post(
            "/api/tasks",
            json={
                "function": "list_approved_proposals",
                "module": "implementer_core",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "implementer_core.list_approved_proposals"
        implementer_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert implementer_task is not None
        assert implementer_task.func(*implementer_task.args, **implementer_task.kwargs) == []
    finally:
        asyncio.run(orchestrator.shutdown())


def test_api_server_rejects_unknown_task_target(tmp_path):
    orchestrator, _guardian = _build_orchestrator(tmp_path)

    try:
        server = APIServer(orchestrator=orchestrator, enable_cors=False)
        client = server.app.test_client()

        response = client.post(
            "/api/tasks",
            json={"function": "not_a_real_function", "priority": 5},
        )

        assert response.status_code == 400
        assert "Task function not found" in response.get_json()["error"]
    finally:
        asyncio.run(orchestrator.shutdown())


def test_mutation_workflow_components_are_opt_in_and_api_routable(tmp_path):
    orchestrator, _guardian = _build_orchestrator(
        tmp_path,
        config_overrides={"enable_mutation_workflow_components": True},
    )

    try:
        assert orchestrator.mutation_review_manager is not None
        assert orchestrator.mutation_router is not None
        assert orchestrator.mutation_publisher is not None

        server = APIServer(orchestrator=orchestrator, enable_cors=False)
        client = server.app.test_client()

        response = client.post(
            "/api/tasks",
            json={
                "function": "get_statistics",
                "module": "mutation_review_manager",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "mutation_review_manager.get_statistics"
        review_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert review_task is not None
        review_stats = review_task.func(*review_task.args, **review_task.kwargs)
        assert "total_reviews" in review_stats

        response = client.post(
            "/api/tasks",
            json={
                "function": "get_pending_human_reviews",
                "module": "mutation_router",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "mutation_router.get_pending_human_reviews"
        router_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert router_task is not None
        assert isinstance(router_task.func(*router_task.args, **router_task.kwargs), list)

        response = client.post(
            "/api/tasks",
            json={
                "function": "get_statistics",
                "module": "mutation_publisher",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "mutation_publisher.get_statistics"
        publisher_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert publisher_task is not None
        publish_stats = publisher_task.func(*publisher_task.args, **publisher_task.kwargs)
        assert "total_published" in publish_stats
    finally:
        asyncio.run(orchestrator.shutdown())


def test_mutation_sandbox_and_tool_executor_are_opt_in_and_api_routable(tmp_path):
    orchestrator, _guardian = _build_orchestrator(
        tmp_path,
        config_overrides={
            "enable_mutation_workflow_components": True,
            "enable_mutation_sandbox": True,
            "enable_tool_executor": True,
        },
    )

    try:
        assert orchestrator.mutation_sandbox is not None
        assert orchestrator.tool_executor is not None

        server = APIServer(orchestrator=orchestrator, enable_cors=False)
        client = server.app.test_client()

        response = client.post(
            "/api/tasks",
            json={
                "function": "get_statistics",
                "module": "mutation_sandbox",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "mutation_sandbox.get_statistics"
        sandbox_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert sandbox_task is not None
        sandbox_stats = sandbox_task.func(*sandbox_task.args, **sandbox_task.kwargs)
        assert "total_tests" in sandbox_stats

        response = client.post(
            "/api/tasks",
            json={
                "function": "get_allowed_tools",
                "module": "tool_executor",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "tool_executor.get_allowed_tools"
        allowed_tools_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert allowed_tools_task is not None
        allowed_tools = allowed_tools_task.func(*allowed_tools_task.args, **allowed_tools_task.kwargs)
        assert "ask_user" in allowed_tools

        response = client.post(
            "/api/tasks",
            json={
                "function": "execute_action",
                "module": "tool_executor",
                "priority": 5,
                "kwargs": {
                    "action": {
                        "tool": "ask_user",
                        "args": {"message": "Need confirmation"},
                    }
                },
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "tool_executor.execute_action"
        execute_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert execute_task is not None
        execute_result = execute_task.func(*execute_task.args, **execute_task.kwargs)
        assert execute_result["status"] == "deferred"
    finally:
        asyncio.run(orchestrator.shutdown())


def test_medium_runtime_components_are_opt_in_and_api_routable(tmp_path):
    orchestrator, _guardian = _build_orchestrator(
        tmp_path,
        config_overrides={
            "enable_digital_safehouse": True,
            "enable_dream_engine": True,
            "enable_ai_mutation_validator": True,
        },
    )

    try:
        assert orchestrator.digital_safehouse is not None
        assert orchestrator.dream_engine is not None
        assert orchestrator.ai_mutation_validator is not None

        server = APIServer(orchestrator=orchestrator, enable_cors=False)
        client = server.app.test_client()

        response = client.post(
            "/api/tasks",
            json={
                "function": "list_backups",
                "module": "digital_safehouse",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "digital_safehouse.list_backups"
        safehouse_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert safehouse_task is not None
        assert isinstance(safehouse_task.func(*safehouse_task.args, **safehouse_task.kwargs), list)

        response = client.post(
            "/api/tasks",
            json={
                "function": "get_dream_statistics",
                "module": "dream_engine",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "dream_engine.get_dream_statistics"
        dream_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert dream_task is not None
        dream_stats = dream_task.func(*dream_task.args, **dream_task.kwargs)
        assert "total_dreams" in dream_stats

        response = client.post(
            "/api/tasks",
            json={
                "function": "get_statistics",
                "module": "ai_mutation_validator",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "ai_mutation_validator.get_statistics"
        validator_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert validator_task is not None
        validator_stats = validator_task.func(*validator_task.args, **validator_task.kwargs)
        assert "total_validations" in validator_stats
    finally:
        asyncio.run(orchestrator.shutdown())


def test_income_distribution_and_proposal_components_are_opt_in_and_api_routable(tmp_path):
    proposal_dir = tmp_path / "proposals" / "proposal-1"
    proposal_dir.mkdir(parents=True, exist_ok=True)
    (proposal_dir / "metadata.json").write_text(
        '{"proposal_id":"proposal-1","title":"Seed","status":"research","created_at":"2026-01-01T00:00:00"}',
        encoding="utf-8",
    )

    orchestrator, _guardian = _build_orchestrator(
        tmp_path,
        config_overrides={
            "enable_income_executor": True,
            "enable_intelligent_task_distribution": True,
            "enable_proposal_api": True,
            "proposal_api_proposals_root": str(tmp_path / "proposals"),
        },
    )

    try:
        assert orchestrator.income_executor is not None
        assert orchestrator.intelligent_task_distribution is not None
        assert orchestrator.proposal_api is not None

        server = APIServer(orchestrator=orchestrator, enable_cors=False)
        client = server.app.test_client()

        response = client.post(
            "/api/tasks",
            json={
                "function": "get_statistics",
                "module": "income_executor",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "income_executor.get_statistics"
        income_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert income_task is not None
        income_stats = income_task.func(*income_task.args, **income_task.kwargs)
        assert "total_revenue" in income_stats

        response = client.post(
            "/api/tasks",
            json={
                "function": "get_statistics",
                "module": "intelligent_task_distribution",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "intelligent_task_distribution.get_statistics"
        distribution_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert distribution_task is not None
        distribution_stats = distribution_task.func(*distribution_task.args, **distribution_task.kwargs)
        assert "total_distributions" in distribution_stats

        response = client.post(
            "/api/tasks",
            json={
                "function": "list_proposals",
                "module": "proposal_api",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "proposal_api.list_proposals"
        proposal_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert proposal_task is not None
        proposals = proposal_task.func(*proposal_task.args, **proposal_task.kwargs)
        assert len(proposals) == 1
        assert proposals[0]["proposal_id"] == "proposal-1"

        response = client.post(
            "/api/tasks",
            json={
                "function": "get_status_report",
                "module": "proposal_api",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "proposal_api.get_status_report"
        status_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert status_task is not None
        status_report = status_task.func(*status_task.args, **status_task.kwargs)
        assert "ProposalSurface" in status_report
    finally:
        asyncio.run(orchestrator.shutdown())


def test_slave_deployment_component_is_opt_in_and_api_routable(tmp_path):
    orchestrator, _guardian = _build_orchestrator(
        tmp_path,
        config_overrides={"enable_slave_deployment": True},
    )

    try:
        assert orchestrator.slave_deployment is not None

        server = APIServer(orchestrator=orchestrator, enable_cors=False)
        client = server.app.test_client()

        response = client.post(
            "/api/tasks",
            json={
                "function": "get_statistics",
                "module": "slave_deployment",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "slave_deployment.get_statistics"
        stats_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert stats_task is not None
        stats = stats_task.func(*stats_task.args, **stats_task.kwargs)
        assert "total_slaves" in stats

        response = client.post(
            "/api/tasks",
            json={
                "function": "list_slaves",
                "module": "slave_deployment",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "slave_deployment.list_slaves"
        list_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert list_task is not None
        assert isinstance(list_task.func(*list_task.args, **list_task.kwargs), list)
    finally:
        asyncio.run(orchestrator.shutdown())


def test_api_server_ui_launcher_surface_is_opt_in(tmp_path):
    orchestrator, _guardian = _build_orchestrator(tmp_path)
    try:
        server = APIServer(orchestrator=orchestrator, enable_cors=False, enable_ui_launcher=True)
        client = server.app.test_client()

        response = client.get("/api/ui/status")
        assert response.status_code == 200
        payload = response.get_json()
        assert "available" in payload
        assert "routes" in payload

        response = client.post(
            "/api/tasks",
            json={
                "function": "get_status",
                "module": "ui_app_launcher",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "ui_app_launcher.get_status"
        task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert task is not None
        status = task.func(*task.args, **task.kwargs)
        assert "available" in status
    finally:
        asyncio.run(orchestrator.shutdown())


def test_utility_components_are_opt_in_and_api_routable(tmp_path):
    export_source = tmp_path / "chatgpt-export"
    export_source.mkdir(parents=True, exist_ok=True)
    (export_source / "conversations.json").write_text(
        (
            '[{"conversation_id":"conv-1","title":"Chat","current_node":"n2","mapping":{'
            '"n1":{"id":"n1","parent":null,"message":{"author":{"role":"user"},"content":{"parts":["hello"]},"create_time":1}},'
            '"n2":{"id":"n2","parent":"n1","message":{"author":{"role":"assistant"},"content":{"parts":["hi"]},"create_time":2}}'
            "}}]"
        ),
        encoding="utf-8",
    )

    orchestrator, _guardian = _build_orchestrator(
        tmp_path,
        config_overrides={
            "enable_credit_spend_log": True,
            "enable_error_handler": True,
            "enable_chatgpt_export_import": True,
            "chatgpt_export_import_output_dir": str(tmp_path / "chatlogs"),
        },
    )

    try:
        assert orchestrator.credit_spend_log is not None
        assert orchestrator.error_handler is not None
        assert orchestrator.chatgpt_export_import is not None

        server = APIServer(orchestrator=orchestrator, enable_cors=False)
        client = server.app.test_client()

        response = client.post(
            "/api/tasks",
            json={
                "function": "get_statistics",
                "module": "credit_spend_log",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "credit_spend_log.get_statistics"
        credit_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert credit_task is not None
        credit_stats = credit_task.func(*credit_task.args, **credit_task.kwargs)
        assert "total_transactions" in credit_stats

        response = client.post(
            "/api/tasks",
            json={
                "function": "get_error_summary",
                "module": "error_handler",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "error_handler.get_error_summary"
        error_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert error_task is not None
        error_summary = error_task.func(*error_task.args, **error_task.kwargs)
        assert "total_errors" in error_summary

        response = client.post(
            "/api/tasks",
            json={
                "function": "import_export",
                "module": "chatgpt_export_import",
                "priority": 5,
                "kwargs": {
                    "src_path": str(export_source),
                    "dry_run": True,
                },
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "chatgpt_export_import.import_export"
        import_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert import_task is not None
        import_result = import_task.func(*import_task.args, **import_task.kwargs)
        assert import_result["written"] == 1
        assert import_result["dry_run"] is True
    finally:
        asyncio.run(orchestrator.shutdown())


def test_feedback_file_writer_and_sandbox_are_opt_in_and_api_routable(tmp_path):
    orchestrator, _guardian = _build_orchestrator(
        tmp_path,
        config_overrides={
            "enable_feedback_loop_core": True,
            "feedback_loop_core_storage_path": str(tmp_path / "feedback_loop.json"),
            "enable_file_writer": True,
            "file_writer_repo_root": str(tmp_path),
            "enable_mutation_autonomy_sandbox": True,
            "mutation_autonomy_sandbox_path": str(tmp_path / "sandbox.py"),
        },
    )

    try:
        assert orchestrator.feedback_loop_core is not None
        assert orchestrator.file_writer is not None
        assert orchestrator.mutation_autonomy_sandbox is not None

        (tmp_path / "sandbox.py").write_text("SANDBOX_VERSION = 123\n", encoding="utf-8")

        server = APIServer(orchestrator=orchestrator, enable_cors=False)
        client = server.app.test_client()

        response = client.post(
            "/api/tasks",
            json={
                "function": "get_learning_insights",
                "module": "feedback_loop_core",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "feedback_loop_core.get_learning_insights"
        insights_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert insights_task is not None
        insights = insights_task.func(*insights_task.args, **insights_task.kwargs)
        assert "insights" in insights

        response = client.post(
            "/api/tasks",
            json={
                "function": "get_status",
                "module": "file_writer",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "file_writer.get_status"
        writer_status_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert writer_status_task is not None
        writer_status = writer_status_task.func(*writer_status_task.args, **writer_status_task.kwargs)
        assert "repo_root" in writer_status

        response = client.post(
            "/api/tasks",
            json={
                "function": "validate_path",
                "module": "file_writer",
                "priority": 5,
                "kwargs": {"file_path": "../escape.txt"},
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "file_writer.validate_path"
        path_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert path_task is not None
        path_result = path_task.func(*path_task.args, **path_task.kwargs)
        assert path_result["valid"] is False

        response = client.post(
            "/api/tasks",
            json={
                "function": "get_status",
                "module": "mutation_autonomy_sandbox",
                "priority": 5,
            },
        )
        assert response.status_code == 201
        assert response.get_json()["resolved_function"] == "mutation_autonomy_sandbox.get_status"
        sandbox_task = orchestrator.task_queue.get_task(response.get_json()["task_id"])
        assert sandbox_task is not None
        sandbox_status = sandbox_task.func(*sandbox_task.args, **sandbox_task.kwargs)
        assert sandbox_status["exists"] is True
    finally:
        asyncio.run(orchestrator.shutdown())
