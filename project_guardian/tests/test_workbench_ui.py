import json
from pathlib import Path

import pytest


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_control_panel_template_contains_workbench():
    try:
        from ..ui_control_panel import CONTROL_PANEL_TEMPLATE
    except ImportError:
        pytest.skip("Flask not available for UI testing")

    assert "Operator Workbench" in CONTROL_PANEL_TEMPLATE
    assert "refreshWorkbench" in CONTROL_PANEL_TEMPLATE
    assert "dashboard-opportunity" in CONTROL_PANEL_TEMPLATE
    assert "dashboard-artifact" in CONTROL_PANEL_TEMPLATE
    assert "dashboard-sales-launch" in CONTROL_PANEL_TEMPLATE
    assert "external-moltbook-details" in CONTROL_PANEL_TEMPLATE
    assert "external-openclaw-details" in CONTROL_PANEL_TEMPLATE
    assert "external-storage-details" in CONTROL_PANEL_TEMPLATE
    assert "externalStorageBadgeState" in CONTROL_PANEL_TEMPLATE
    assert "renderExternalActivity" in CONTROL_PANEL_TEMPLATE
    assert "workbench-sales-launch" in CONTROL_PANEL_TEMPLATE
    assert "Start Here" in CONTROL_PANEL_TEMPLATE
    assert "dashboard-quick-ask" in CONTROL_PANEL_TEMPLATE
    assert "dashboard-quick-answer" in CONTROL_PANEL_TEMPLATE
    assert "quickAskElysia" in CONTROL_PANEL_TEMPLATE
    assert "quickFindOpportunities" in CONTROL_PANEL_TEMPLATE
    assert "quickLearnFrom('twitter')" in CONTROL_PANEL_TEMPLATE
    assert "quickShowChanges" in CONTROL_PANEL_TEMPLATE


def test_workbench_summary_endpoint_aggregates_artifacts_and_tasks(guardian_core, tmp_path: Path):
    try:
        from ..ui_control_panel import UIControlPanel
    except ImportError:
        pytest.skip("Flask not available for UI testing")

    data_root = tmp_path / "ui_data"
    docs_root = tmp_path / "ui_docs"
    guardian_core.ui_data_roots = [data_root]
    guardian_core.ui_doc_roots = [docs_root]

    _write_json(
        data_root / "revenue_briefs" / "sample_revenue_shortlist.json",
        {
            "task_id": "st_rev_1",
            "contract_id": "revenue_shortlist",
            "payload": {
                "opportunities": [
                    {
                        "title": "Launch async research brief service",
                        "rationale": "Operators keep producing artifacts but the offer is not packaged yet.",
                        "required_capability": "module:income_generator",
                        "difficulty": "medium",
                        "expected_value": "high",
                    }
                ]
            },
        },
    )
    _write_json(
        data_root / "generated_reports" / "sample_digest.json",
        {
            "task_id": "st_digest_1",
            "contract_id": "learned_digest",
            "payload": {
                "top_insights": [
                    "People need clearer productized services from Elysia."
                ],
                "why_they_matter": "A cleaner offer helps the system feel useful to real operators.",
                "recommended_followup_tasks": ["generate_revenue_shortlist"],
            },
        },
    )
    _write_json(
        data_root / "generated_reports" / "sample_improvement.json",
        {
            "task_id": "st_improve_1",
            "contract_id": "system_improvement_proposal",
            "payload": {
                "summary": "Promote artifact-first work in the interface.",
                "recommendations": [
                    "Highlight top opportunities",
                    "Show active self-tasks",
                ],
            },
        },
    )
    _write_json(
        data_root / "generated_reports" / "sample_offer_pack.json",
        {
            "task_id": "st_offer_1",
            "contract_id": "offer_pack",
            "payload": {
                "product_name": "Capability Gap Remediation Sprint",
                "one_liner": "Turn one workflow blocker into a fixed-scope sprint with a clear next step.",
                "why_buy_now": "A small fixed offer is easier to test than a broad consulting pitch.",
                "validation_prompt": "Would this be worth paying for this week if it solved one real blocker?",
                "recommended_next_step": "Create one live $79 Signal Test payment link and send it to 3 prospects.",
                "pricing_options": [
                    {"name": "Signal Test", "price": "$79", "includes": ["brief"]},
                    {"name": "Operator Sprint", "price": "$199", "includes": ["brief", "plan"]},
                ],
            },
        },
    )
    _write_json(
        data_root / "self_task_queue.json",
        {
            "tasks": [
                {
                    "task_id": "st_active_1",
                    "title": "Package operator offer page",
                    "goal": "Turn the best opportunity into an offer pack.",
                    "status": "pending",
                    "category": "service_design",
                    "priority": 0.91,
                    "created_at": "2026-04-20T18:20:00+00:00",
                },
                {
                    "task_id": "st_done_1",
                    "title": "Publish useful digest",
                    "goal": "Summarize useful findings for the operator.",
                    "status": "completed",
                    "category": "learning",
                    "priority": 0.75,
                    "updated_at": "2026-04-20T18:21:00+00:00",
                    "output_contract_id": "learned_digest",
                },
            ]
        },
    )
    (docs_root / "STRIPE_PAYMENT_LINK_SETUP.md").parent.mkdir(parents=True, exist_ok=True)
    (docs_root / "STRIPE_PAYMENT_LINK_SETUP.md").write_text(
        "# Stripe Payment Link Setup\n\nCreate one live $79 Signal Test payment link first.",
        encoding="utf-8",
    )
    (docs_root / "FIRST_OFFER_LAUNCH_BUNDLE.md").write_text(
        "# First Offer Launch Bundle\n\nUse the listing copy and outreach message to publish the first offer.",
        encoding="utf-8",
    )

    panel = UIControlPanel(guardian_core)
    with panel.app.test_client() as client:
        response = client.get("/api/workbench/summary")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True

    workbench = data["workbench"]
    assert workbench["counts"]["opportunities_total"] == 1
    assert workbench["counts"]["active_self_tasks"] == 1
    assert workbench["counts"]["artifacts_total"] == 4

    opportunity = workbench["top_opportunities"][0]
    assert opportunity["title"] == "Launch async research brief service"
    assert opportunity["required_capability"] == "module:income_generator"

    active_task = workbench["active_self_tasks"][0]
    assert active_task["title"] == "Package operator offer page"
    assert active_task["status"] == "pending"

    digest = workbench["learning_digests"][0]
    assert digest["summary"] == "A cleaner offer helps the system feel useful to real operators."
    assert digest["top_insights"] == ["People need clearer productized services from Elysia."]

    improvement = workbench["improvement_briefs"][0]
    assert improvement["summary"] == "Promote artifact-first work in the interface."
    assert improvement["key_points"] == ["Highlight top opportunities", "Show active self-tasks"]

    sales_launch = workbench["sales_launch"]
    assert sales_launch["recommended_path"] == "Stripe Payment Links"
    assert sales_launch["offer_name"] == "Capability Gap Remediation Sprint"
    assert sales_launch["price_points"] == ["Signal Test: $79", "Operator Sprint: $199"]
    assert any(doc["title"] == "Stripe Payment Link Setup" for doc in sales_launch["docs"])


def test_status_endpoint_exposes_external_activity(guardian_core, tmp_path: Path, monkeypatch):
    try:
        from ..ui_control_panel import UIControlPanel
        from .. import ui_control_panel as ui_mod
    except ImportError:
        pytest.skip("Flask not available for UI testing")

    browser_state = tmp_path / "browser_agent_state.json"
    openclaw_state = tmp_path / "data" / "runtime" / "openclaw_activity.json"

    _write_json(
        browser_state,
        {
            "sessions": [
                {
                    "goal": "Observe MoltBook for useful operator-facing AI activity.",
                    "summary": "Observed a fresh MoltBook front-page scan with AI and automation threads.",
                    "stop_reason": "completed",
                    "ts": 1776894181.8977315,
                    "steps": [{"url": "https://www.moltbook.com/"}],
                }
            ],
            "findings_log": [
                {
                    "url": "https://www.moltbook.com/",
                    "snippet": "Trending AI and automation posts were visible on the front page.",
                    "relevance": 0.94,
                    "ts": 1776894181.8977315,
                }
            ],
        },
    )
    _write_json(
        openclaw_state,
        {
            "updated_at": "2026-04-22T17:45:00-04:00",
            "request_count": 3,
            "last_model": "elysia/main",
            "last_status": "ok",
            "last_request_preview": "What should I ship next for operators?",
            "last_reply_preview": "Package the strongest offer into a small fixed-scope sprint.",
            "recent_requests": [
                {
                    "ts": "2026-04-22T17:45:00-04:00",
                    "status": "ok",
                    "model": "elysia/main",
                    "message_preview": "What should I ship next for operators?",
                    "reply_preview": "Package the strongest offer into a small fixed-scope sprint.",
                }
            ],
        },
    )

    monkeypatch.setattr(ui_mod, "BROWSER_AGENT_STATE_PATH", browser_state)
    monkeypatch.setattr(ui_mod, "OPENCLAW_ACTIVITY_PATH", openclaw_state)
    monkeypatch.setattr(ui_mod, "_is_tcp_endpoint_reachable", lambda host, port, timeout=0.15: True)

    panel = UIControlPanel(guardian_core)
    with panel.app.test_client() as client:
        response = client.get("/api/status")

    assert response.status_code == 200
    data = response.get_json()
    assert "external" in data
    assert "storage" in data["external"]
    assert isinstance(data["external"]["storage"], dict)

    moltbook = data["external"]["moltbook"]
    assert moltbook["available"] is True
    assert moltbook["goal"] == "Observe MoltBook for useful operator-facing AI activity."
    assert "front-page scan" in (moltbook.get("summary") or "")
    assert moltbook["latest_url"] == "https://www.moltbook.com/"

    openclaw = data["external"]["openclaw"]
    assert openclaw["available"] is True
    assert openclaw["gateway_reachable"] is True
    assert openclaw["request_count"] == 3
    assert openclaw["last_model"] == "elysia/main"
    assert openclaw["last_request_preview"] == "What should I ship next for operators?"
