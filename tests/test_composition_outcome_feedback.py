"""Durable composition outcome feedback and evidence-based ranking."""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

if "project_guardian" not in sys.modules:
    package = types.ModuleType("project_guardian")
    package.__path__ = [str(_ROOT / "project_guardian")]
    package.__package__ = "project_guardian"
    sys.modules["project_guardian"] = package

from project_guardian.capability_composition import (
    list_composable_capabilities,
    rank_replan_candidates,
    validate_proposed_plan,
)
from project_guardian.composition_outcome_feedback import (
    DEFAULT_MIN_ATTEMPTS,
    DEFAULT_MIN_TASK_INSTANCES,
    OutcomeFeedbackError,
    OutcomeFeedbackStore,
    build_strategy_context,
    normalize_failure_class,
    resolve_outcome_feedback_root,
)
from project_guardian.conversation_continuity import (
    ContinuityError,
    ConversationStore,
    resolve_conversation_root,
)
from project_guardian.local_documents_search import folder_fingerprint


def _receipt(n: int, capability: str, *, verified: bool = True) -> dict:
    return {
        "execution_id": f"exec_{n:016x}",
        "capability": capability,
        "verified": verified,
        "outcome": {
            "capability": capability,
            "task_class": "structured_table_extraction",
            "success": verified,
            "created_utc": "2026-10-31T00:00:00Z",
        },
    }


@pytest.fixture()
def store(tmp_path: Path) -> OutcomeFeedbackStore:
    return OutcomeFeedbackStore(
        resolve_outcome_feedback_root(tmp_path),
        min_attempts=10,
        min_task_instances=3,
    )


def test_cold_start_reliability_unknown(store: OutcomeFeedbackStore):
    ranked = store.rank_capabilities(
        list_composable_capabilities(),
        available_capabilities=list_composable_capabilities(),
        task_class="structured_table_extraction",
    )
    assert ranked
    assert all(r["reliability"] == "unknown" for r in ranked)
    assert all(r["recommendation_basis"] == "current_suitability" for r in ranked)
    assert ranked[0]["authorization_granted"] is False
    # Deterministic extract_records preferred over synthesize by suitability.
    caps = [r["capability"] for r in ranked]
    assert caps.index("compose.extract_records") < caps.index("compose.synthesize")


def test_verified_learning_threshold(store: OutcomeFeedbackStore):
    table_ctx = {
        "task_class": "structured_table_extraction",
        "required_output_type": "structured_records",
        "input_structure": "markdown_table",
        "verification_mode": "source_span",
    }
    # Below threshold: still unknown.
    for i in range(5):
        store.ingest_receipt(
            _receipt(i + 1, "compose.extract_records"),
            conversation_id=f"conv_{i:016x}",
            strategy_context=table_ctx,
            evaluation={"met": True},
        )
    stats = store.stats_for(
        "compose.extract_records",
        strategy_context=build_strategy_context(
            "compose.extract_records", explicit=table_ctx
        ),
    )
    assert stats["sample_size"] == 5
    assert stats["evidence_sufficient"] is False
    assert stats["reliability"] == "unknown"

    # Reach threshold: 10 successes across 10 instances (correlation cap = 2/instance).
    for i in range(5, 15):
        store.ingest_receipt(
            _receipt(i + 1, "compose.extract_records"),
            conversation_id=f"conv_{i:016x}",
            strategy_context=table_ctx,
            evaluation={"met": True},
        )
    stats = store.stats_for(
        "compose.extract_records",
        strategy_context=build_strategy_context(
            "compose.extract_records", explicit=table_ctx
        ),
    )
    assert stats["sample_size"] >= DEFAULT_MIN_ATTEMPTS
    assert stats["task_instance_count"] >= DEFAULT_MIN_TASK_INSTANCES
    assert stats["evidence_sufficient"] is True
    assert stats["reliability"] == "measured"

    ranked = store.rank_capabilities(
        [
            {"capability": "compose.synthesize", "expected_outcome": "draft"},
            {"capability": "compose.extract_records", "expected_outcome": "rows"},
        ],
        available_capabilities=list_composable_capabilities(),
        strategy_context=table_ctx,
    )
    assert ranked[0]["capability"] == "compose.extract_records"
    assert ranked[0]["recommendation_basis"] == "measured_history"
    assert "measured" in ranked[0]["rationale"]


def test_duplicate_receipt_idempotent(store: OutcomeFeedbackStore):
    r = _receipt(1, "compose.aggregate_usd")
    a = store.ingest_receipt(r, conversation_id="conv_aaaaaaaaaaaaaaaa", task_class="deterministic_calculation")
    b = store.ingest_receipt(r, conversation_id="conv_aaaaaaaaaaaaaaaa", task_class="deterministic_calculation")
    assert a["ingested"] is True
    assert b["idempotent"] is True
    assert (
        store.stats_for(
            "compose.aggregate_usd", task_class="deterministic_calculation"
        )["sample_size"]
        == 1
    )


def test_failure_classification():
    assert normalize_failure_class("evidence_criteria_unmet") == "insufficient_evidence"
    assert normalize_failure_class("unauthorized") == "unauthorized_request"
    assert normalize_failure_class("invalid_arguments") == "invalid_input"
    assert normalize_failure_class("tool_exception") == "unsuccessful_execution"
    assert normalize_failure_class("unavailable_capability") == "unavailable_dependency"


def test_unauthorized_failure_excluded_from_reliability(store: OutcomeFeedbackStore):
    for i in range(12):
        store.ingest_receipt(
            {
                **_receipt(i + 1, "local.documents.search", verified=False),
                "outcome": {
                    "capability": "local.documents.search",
                    "task_class": "authorized_document_retrieval",
                    "success": False,
                    "failure_category": "unauthorized",
                },
            },
            conversation_id=f"conv_{(i % 4):016x}",
            task_class="authorized_document_retrieval",
            step={
                "capability": "local.documents.search",
                "last_failure_category": "unauthorized",
            },
        )
    stats = store.stats_for(
        "local.documents.search", task_class="authorized_document_retrieval"
    )
    # Auth failures do not count toward reliability samples.
    assert stats["sample_size"] == 0
    assert stats["reliability"] == "unknown"


def test_hostile_fabricated_success_rejected(store: OutcomeFeedbackStore):
    with pytest.raises(OutcomeFeedbackError, match="verified=True"):
        store.ingest_receipt(
            {
                "execution_id": "exec_abcdef0123456789",
                "capability": "compose.synthesize",
                "verified": False,
                "outcome": {"success": True, "task_class": "grounded_synthesis"},
            }
        )
    with pytest.raises(OutcomeFeedbackError, match="model-generated"):
        store.ingest_receipt(
            {
                "execution_id": "exec_abcdef0123456789",
                "capability": "compose.synthesize",
                "verified": True,
                "outcome": {
                    "success": True,
                    "provenance": "model_claim",
                    "task_class": "grounded_synthesis",
                },
            }
        )
    with pytest.raises(OutcomeFeedbackError, match="execution_id"):
        store.ingest_receipt(
            {
                "execution_id": "made_up",
                "capability": "compose.synthesize",
                "verified": True,
                "outcome": {"success": True},
            }
        )


def test_corrupt_store_recovers(tmp_path: Path):
    root = resolve_outcome_feedback_root(tmp_path)
    store = OutcomeFeedbackStore(root, min_attempts=10, min_task_instances=3)
    store.ingest_receipt(
        _receipt(1, "compose.extract_fields"),
        conversation_id="conv_bbbbbbbbbbbbbbbb",
        task_class="structured_field_extraction",
    )
    # Corrupt primary file.
    store.path.write_text("{not-json", encoding="utf-8")
    store2 = OutcomeFeedbackStore(root, min_attempts=10, min_task_instances=3)
    exported = store2.export_store()
    # Either recovered from .bak or reinitialized without crashing.
    assert exported["schema"].startswith("elysia.composition-outcome-feedback")
    assert exported["authorization_granted"] is False


def test_rank_replan_uses_outcome_store(store: OutcomeFeedbackStore):
    table_ctx = {
        "task_class": "structured_table_extraction",
        "required_output_type": "structured_records",
        "input_structure": "markdown_table",
        "verification_mode": "source_span",
    }
    for i in range(10):
        store.ingest_receipt(
            _receipt(i + 1, "compose.extract_records"),
            conversation_id=f"conv_{i:016x}",
            strategy_context=table_ctx,
            evaluation={"met": True},
        )
    ranked = rank_replan_candidates(
        [
            {"capability": "compose.synthesize", "expected_outcome": "x"},
            {"capability": "compose.extract_records", "expected_outcome": "y"},
        ],
        available_capabilities=list_composable_capabilities(),
        outcome_store=store,
        strategy_context=table_ctx,
    )
    assert ranked[0]["capability"] == "compose.extract_records"
    assert ranked[0]["evidence_sufficient"] is True


def test_validate_plan_exposes_selection(store: OutcomeFeedbackStore):
    docs_ctx = {
        "task_class": "authorized_document_retrieval",
        "required_output_type": "document_excerpts",
        "input_structure": "free_text",
        "verification_mode": "evidence_criteria",
    }
    for i in range(10):
        store.ingest_receipt(
            _receipt(i + 1, "local.documents.search"),
            conversation_id=f"conv_{i:016x}",
            strategy_context=docs_ctx,
            evaluation={"met": True},
        )
    validated = validate_proposed_plan(
        {
            "objective": "Find orchard notes",
            "steps": [
                {
                    "capability": "compose.synthesize",
                    "expected_outcome": "guess",
                },
                {
                    "capability": "local.documents.search",
                    "expected_outcome": "retrieve notes",
                },
            ],
        },
        list_composable_capabilities(),
        outcome_store=store,
        strategy_context=docs_ctx,
    )
    assert validated["executable"] is False
    assert validated["authorization_granted"] is False
    assert validated["selected_next_capability"] == "local.documents.search"
    assert validated["recommendation_basis"] == "measured_history"


def test_execution_ingests_and_survives_restart(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "note.md").write_text("Variety: Cedar Belle\n", encoding="utf-8")
    conv_root = resolve_conversation_root(tmp_path)
    cs = ConversationStore(conv_root)
    assert cs.outcome_store is not None
    conv = cs.create(objective="Find variety")
    cid = conv["conversation_id"]
    saved = cs.commit_operator_task_state(
        cid,
        expected_revision=0,
        outstanding_steps=["search variety"],
        next_safe_action="search variety",
    )
    step_id = saved["conversation"]["task_steps"][0]["step_id"]
    rev = int(saved["conversation"]["checkpoint_revision"])
    fp = folder_fingerprint(str(docs))
    bound = cs.bind_operator_step(
        cid,
        step_id=step_id,
        expected_revision=rev,
        capability="local.documents.search",
        arguments={
            "query": "Cedar Belle",
            "min_matches": 1,
            "required_substring": "Cedar Belle",
            "expected_relative_path": "note.md",
            "folder_label": docs.name,
            "folder_fingerprint": fp,
        },
    )
    rev = int(bound["conversation"]["checkpoint_revision"])
    ok = cs.execute_verified_bound_step(
        cid,
        step_id=step_id,
        expected_revision=rev,
        authorize_documents_search=True,
        authorize_record_completion=True,
        documents_folder=str(docs),
    )
    assert ok["verified"] is True
    stats = cs.outcome_store.stats_for("local.documents.search")
    assert stats["verified_success_count"] >= 1

    # Restart: new store instance reads same durable file.
    cs2 = ConversationStore(conv_root)
    stats2 = cs2.outcome_store.stats_for("local.documents.search")
    assert stats2["verified_success_count"] == stats["verified_success_count"]
    exported = cs2.outcome_store.export_store()
    assert exported["authorization_granted"] is False


def test_missing_search_failure_ingested(tmp_path: Path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "note.md").write_text("hello\n", encoding="utf-8")
    cs = ConversationStore(resolve_conversation_root(tmp_path))
    conv = cs.create(objective="Find missing")
    cid = conv["conversation_id"]
    saved = cs.commit_operator_task_state(
        cid,
        expected_revision=0,
        outstanding_steps=["search"],
        next_safe_action="search",
    )
    step_id = saved["conversation"]["task_steps"][0]["step_id"]
    rev = int(saved["conversation"]["checkpoint_revision"])
    bound = cs.bind_operator_step(
        cid,
        step_id=step_id,
        expected_revision=rev,
        capability="local.documents.search",
        arguments={"query": "zzz-no-match", "min_matches": 1, "folder_label": docs.name},
    )
    rev = int(bound["conversation"]["checkpoint_revision"])
    with pytest.raises(ContinuityError, match="evidence criteria unmet"):
        cs.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_documents_search=True,
            authorize_record_completion=True,
            documents_folder=str(docs),
        )
    stats = cs.outcome_store.stats_for("local.documents.search")
    assert stats["failure_count"] >= 1
    classes = stats["failure_class_counts"]
    assert "insufficient_evidence" in classes
