import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from project_guardian.capability_execution import execute_capability_kind
from project_guardian.self_task_advancement import evaluate_task_advancement
from project_guardian.self_task_artifacts import save_self_task_artifact
from project_guardian.self_task_generator import SelfTaskGenerator
from project_guardian.self_task_output_contracts import (
    build_offer_pack_from_artifacts,
    validate_contract,
)


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_build_offer_pack_from_artifacts_is_contract_valid():
    payload = build_offer_pack_from_artifacts(
        revenue_payload={
            "opportunities": [
                {
                    "title": "Launch async research brief service",
                    "rationale": "Operators need one clear paid entry point instead of raw internal artifacts.",
                    "required_capability": "module:income_generator",
                    "difficulty": "medium",
                    "expected_value": "high",
                }
            ]
        },
        digest_payload={
            "top_insights": ["People respond better when Elysia presents one fixed-scope offer."],
            "why_they_matter": "A simple entry offer is easier to test with real buyers.",
        },
        improvement_payload={
            "summary": "Promote productized services instead of only internal diagnostics.",
            "recommendations": ["Show deliverables clearly", "Ask one buyer-focused question"],
        },
        source_names=["revenue_shortlist.json", "learning_digest.json"],
    )

    ok, reason = validate_contract("offer_pack", payload)
    assert ok, reason
    assert payload["product_name"]
    assert len(payload["deliverables"]) >= 3
    assert "## Pricing" in payload["listing_markdown"]


def test_artifact_synthesizer_generates_offer_pack_from_local_artifacts(tmp_path: Path):
    data_root = tmp_path / "ui_data"
    _write_json(
        data_root / "revenue_briefs" / "sample_revenue_shortlist.json",
        {
            "task_id": "st_rev_1",
            "contract_id": "revenue_shortlist",
            "payload": {
                "opportunities": [
                    {
                        "title": "Launch async research brief service",
                        "rationale": "Operators keep generating useful summaries, but nothing is packaged to buy.",
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
                "top_insights": ["People need clearer productized services from Elysia."],
                "why_they_matter": "A clearer offer is the fastest way to test demand.",
                "recommended_followup_tasks": ["package_operator_offer_pack"],
            },
        },
    )

    guardian = type("G", (), {"_modules": {}, "ui_data_roots": [data_root]})()
    out = execute_capability_kind(
        guardian,
        "tool",
        "artifact_synthesizer",
        {"self_task_archetype": "package_operator_offer_pack"},
    )

    assert out["success"] is True
    payload = out.get("result") or {}
    ok, reason = validate_contract("offer_pack", payload)
    assert ok, reason
    assert payload["product_name"]
    assert any("sample_revenue_shortlist.json" in src for src in payload["source_artifacts"])


def test_opportunity_ranker_scores_revenue_artifacts(tmp_path: Path):
    data_root = tmp_path / "ui_data"
    _write_json(
        data_root / "revenue_briefs" / "ranked_revenue_shortlist.json",
        {
            "contract_id": "revenue_shortlist",
            "payload": {
                "opportunities": [
                    {
                        "title": "Low value housekeeping",
                        "rationale": "Useful but not buyer-facing.",
                        "required_capability": "module:income_generator",
                        "difficulty": "low",
                        "expected_value": "low",
                    },
                    {
                        "title": "Buyer audit sprint",
                        "rationale": "Clear paid service with immediate operator value.",
                        "required_capability": "tool:artifact_synthesizer",
                        "difficulty": "medium",
                        "expected_value": "$500",
                    },
                ]
            },
        },
    )

    guardian = type("G", (), {"_modules": {}, "ui_data_roots": [data_root]})()
    with patch("project_guardian.capability_execution._artifact_search_roots", return_value=[data_root]):
        out = execute_capability_kind(guardian, "tool", "opportunity_ranker", {})

    assert out["success"] is True
    ranked = out["result"]["ranked"]
    assert ranked[0]["title"] == "Buyer audit sprint"
    assert ranked[0]["rank_score"] > ranked[1]["rank_score"]
    assert "ranked_revenue_shortlist.json" in out["result"]["source_file"]


def test_revenue_executor_selects_best_artifact_opportunity(tmp_path: Path):
    data_root = tmp_path / "ui_data"
    _write_json(
        data_root / "revenue_briefs" / "execution_revenue_shortlist.json",
        {
            "contract_id": "revenue_shortlist",
            "payload": {
                "opportunities": [
                    {
                        "title": "Generic visibility work",
                        "rationale": "Could help later.",
                        "required_capability": "module:income_generator",
                        "difficulty": "low",
                        "expected_value": "visibility",
                    },
                    {
                        "title": "Operator dashboard audit offer",
                        "rationale": "Concrete buyer-facing package.",
                        "required_capability": "tool:artifact_synthesizer",
                        "difficulty": "low",
                        "expected_value": "high",
                    },
                ]
            },
        },
    )

    class _IncomeGenerator:
        def get_income_summary(self):
            return {"active_streams": 1, "monthly_target": 1000}

    guardian = type(
        "G",
        (),
        {
            "_modules": {"income_generator": _IncomeGenerator()},
            "ui_data_roots": [data_root],
        },
    )()
    with patch("project_guardian.capability_execution._artifact_search_roots", return_value=[data_root]):
        out = execute_capability_kind(
            guardian,
            "tool",
            "revenue_executor",
            {"self_task_archetype": "execute_best_opportunity"},
        )

    assert out["success"] is True
    result = out["result"]
    assert result["artifact_backed"] is True
    assert result["selected_opportunity"]["title"] == "Operator dashboard audit offer"
    assert result["execution_plan"]["required_capability"] == "tool:artifact_synthesizer"
    assert "execution_revenue_shortlist.json" in result["source_file"]


def test_self_task_generator_emits_offer_pack_task():
    guardian = type(
        "G",
        (),
        {"_modules": {"tool_registry": object(), "income_generator": object()}},
    )()
    generator = SelfTaskGenerator(
        {"max_operator_value_tasks_per_cycle": 8, "max_generate_per_cycle": 10}
    )
    ctx = {
        "stale_self_task_archetypes": [],
        "stale_monetization_loop": False,
        "learning_digest_worthy": False,
        "financial_idle": False,
        "module_underuse": False,
        "underused_modules": [],
    }
    tasks = []

    generator._add_operator_value_tasks(
        guardian, ctx, tasks, lambda name: name in guardian._modules
    )

    offer_task = next(t for t in tasks if t.get("archetype") == "package_operator_offer_pack")
    assert offer_task["title"] == "Package operator offer page"
    assert offer_task["output_contract_id"] == "offer_pack"
    assert offer_task["recommended_capabilities"] == ["tool:artifact_synthesizer"]


def test_workbench_summary_surfaces_offer_pack_artifact(guardian_core, tmp_path: Path):
    try:
        from ..ui_control_panel import UIControlPanel
    except ImportError:
        pytest.skip("Flask not available for UI testing")

    data_root = tmp_path / "ui_data"
    guardian_core.ui_data_roots = [data_root]
    payload = build_offer_pack_from_artifacts(
        revenue_payload={
            "opportunities": [
                {
                    "title": "Async opportunity brief sprint",
                    "rationale": "Turn internal Elysia artifacts into a testable buyer deliverable.",
                    "required_capability": "tool:artifact_synthesizer",
                    "difficulty": "low",
                    "expected_value": "medium",
                }
            ]
        },
        digest_payload={
            "top_insights": ["A single packaged offer feels more buyable than a broad capability list."],
            "why_they_matter": "Specific packaging makes demand testing simpler.",
        },
        source_names=["sample_revenue_shortlist.json"],
    )
    _write_json(
        data_root / "generated_reports" / "sample_offer_pack.json",
        {
            "task_id": "st_offer_1",
            "contract_id": "offer_pack",
            "payload": payload,
        },
    )

    panel = UIControlPanel(guardian_core)
    with panel.app.test_client() as client:
        response = client.get("/api/workbench/summary")

    assert response.status_code == 200
    data = response.get_json()["workbench"]
    artifact = data["recent_artifacts"][0]
    assert artifact["artifact_type"] == "Offer pack"
    assert artifact["headline"] == payload["product_name"]
    assert artifact["summary"] == payload["one_liner"]


def test_offer_pack_advances_objective_and_marks_operator_ready():
    payload = build_offer_pack_from_artifacts(
        revenue_payload={
            "opportunities": [
                {
                    "title": "Capability gap remediation sprint",
                    "rationale": "Package one concrete operator-facing fix instead of another internal note.",
                    "required_capability": "module:tool_registry",
                    "difficulty": "medium",
                    "expected_value": "high",
                }
            ]
        },
        digest_payload={
            "top_insights": ["A packaged offer is easier to validate with buyers than a raw capability list."],
            "why_they_matter": "This creates a concrete thing to test demand for immediately.",
        },
        source_names=["revenue_shortlist.json", "learning_digest.json"],
    )

    result = evaluate_task_advancement(
        archetype="package_operator_offer_pack",
        execution_tier="strong",
        contract_ok=True,
        contract_id="offer_pack",
        payload=payload,
        objective_id="obj_offer_1",
        store={},
        guardian=None,
    )

    assert result["objective_advanced"] is True
    assert result["operator_ready"] is True
    assert result["advancement_score"] >= 0.38
    assert "offer_pack" in result["readiness_reason"]


def test_save_self_task_artifact_mirrors_offer_pack_to_external_storage(tmp_path: Path, monkeypatch):
    from project_guardian import self_task_artifacts as artifacts_mod

    project_root = tmp_path / "project"
    external_data_dir = tmp_path / "thumbdrive" / "ProjectGuardian" / "data"
    (project_root / "config").mkdir(parents=True, exist_ok=True)
    (project_root / "config" / "external_storage.json").write_text(
        json.dumps(
            {
                "use_external_storage": True,
                "data_dir": str(external_data_dir),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(artifacts_mod, "PROJECT_ROOT", project_root)

    payload = build_offer_pack_from_artifacts(source_names=["seed.json"])
    saved_path = save_self_task_artifact(
        task_id="st_offer_123",
        archetype="package_operator_offer_pack",
        contract_id="offer_pack",
        payload=payload,
        execution_tier="strong",
    )

    local_path = project_root / "data" / "generated_reports" / "st_offer_123_package_operator_offer_pack.json"
    mirrored_path = external_data_dir / "generated_reports" / "st_offer_123_package_operator_offer_pack.json"

    assert saved_path == local_path
    assert local_path.exists()
    assert mirrored_path.exists()


def test_save_self_task_artifact_prunes_old_generated_reports(tmp_path: Path, monkeypatch):
    from project_guardian import self_task_artifacts as artifacts_mod

    project_root = tmp_path / "project"
    reports = project_root / "data" / "generated_reports"
    reports.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(artifacts_mod, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(artifacts_mod, "_GENERATED_REPORTS_MAX_FILES", 4)

    base = time.time() - 600
    for i in range(6):
        p = reports / f"old_{i}_x.json"
        p.write_text("{}", encoding="utf-8")
        os.utime(p, (base + i, base + i))

    payload = {"ok": True}
    saved = artifacts_mod.save_self_task_artifact(
        task_id="st_new",
        archetype="package_operator_offer_pack",
        contract_id="offer_pack",
        payload=payload,
        execution_tier="strong",
    )
    assert saved is not None
    remaining = sorted(reports.glob("*.json"))
    assert len(remaining) == 4
    names = {p.name for p in remaining}
    assert "st_new_package_operator_offer_pack.json" in names
