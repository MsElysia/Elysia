"""Comparable strategy contexts and real-runtime outcome learning."""
from __future__ import annotations

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

from project_guardian.capability_composition import list_composable_capabilities
from project_guardian.composition_outcome_feedback import (
    OutcomeFeedbackError,
    OutcomeFeedbackStore,
    build_strategy_context,
    capability_satisfies_output,
    contexts_comparable,
    resolve_outcome_feedback_root,
)
from project_guardian.conversation_continuity import (
    ContinuityError,
    ConversationStore,
    resolve_conversation_root,
)
from project_guardian.local_documents_search import folder_fingerprint


TABLE_CTX = {
    "task_class": "structured_table_extraction",
    "required_output_type": "structured_records",
    "input_structure": "markdown_table",
    "verification_mode": "source_span",
}

DRAFT_CTX = {
    "task_class": "grounded_synthesis",
    "required_output_type": "grounded_draft",
    "input_structure": "free_text",
    "verification_mode": "grounded_amounts",
}


@pytest.fixture()
def store(tmp_path: Path) -> OutcomeFeedbackStore:
    return OutcomeFeedbackStore(
        resolve_outcome_feedback_root(tmp_path),
        min_attempts=3,
        min_task_instances=3,
        max_observations_per_instance=2,
    )


def _mk_receipt(n: int, capability: str, *, verified: bool = True) -> dict:
    return {
        "execution_id": f"exec_{n:016x}",
        "capability": capability,
        "verified": verified,
        "host_execution_path": True,
        "outcome": {
            "capability": capability,
            "success": verified,
            "task_class": TABLE_CTX["task_class"],
        },
    }


def test_noncomparable_capabilities_cannot_outrank(store: OutcomeFeedbackStore):
    assert not capability_satisfies_output("compose.synthesize", "structured_records")
    assert capability_satisfies_output("compose.extract_records", "structured_records")
    assert not contexts_comparable(
        build_strategy_context("compose.extract_records", explicit=TABLE_CTX),
        build_strategy_context("compose.synthesize", explicit=DRAFT_CTX),
    )
    # Flood synthesize with successes in a DIFFERENT context — must not win table ranking.
    for i in range(12):
        store.ingest_receipt(
            {
                **_mk_receipt(i + 1, "compose.synthesize"),
                "outcome": {
                    "capability": "compose.synthesize",
                    "success": True,
                    "task_class": DRAFT_CTX["task_class"],
                },
            },
            conversation_id=f"conv_{(i % 4):016x}",
            strategy_context=DRAFT_CTX,
            evaluation={"met": True},
        )
    ranked = store.rank_capabilities(
        [
            {"capability": "compose.synthesize"},
            {"capability": "compose.extract_records"},
        ],
        available_capabilities=list_composable_capabilities(),
        strategy_context=TABLE_CTX,
    )
    caps = [r["capability"] for r in ranked]
    assert "compose.synthesize" not in caps  # filtered as non-applicable
    assert ranked[0]["capability"] == "compose.extract_records"
    assert ranked[0]["recommendation_basis"] == "current_suitability"
    assert ranked[0]["reliability"] == "unknown"


def test_incomplete_context_keeps_reliability_unknown(store: OutcomeFeedbackStore):
    for i in range(6):
        store.ingest_receipt(
            _mk_receipt(i + 1, "compose.extract_records"),
            conversation_id=f"conv_{(i % 3):016x}",
            strategy_context=TABLE_CTX,
            evaluation={"met": True},
        )
    ranked = store.rank_capabilities(
        [{"capability": "compose.extract_records"}],
        available_capabilities=list_composable_capabilities(),
        strategy_context={"task_class": "structured_table_extraction"},  # incomplete
    )
    assert ranked[0]["reliability"] == "unknown"
    assert ranked[0]["recommendation_basis"] == "current_suitability"


def test_correlated_retries_capped(store: OutcomeFeedbackStore):
    # One conversation with many successes must not alone satisfy threshold.
    for i in range(10):
        store.ingest_receipt(
            _mk_receipt(i + 1, "compose.extract_records"),
            conversation_id="conv_aaaaaaaaaaaaaaaa",
            strategy_context=TABLE_CTX,
            evaluation={"met": True},
        )
    stats = store.stats_for(
        "compose.extract_records",
        strategy_context=build_strategy_context(
            "compose.extract_records", explicit=TABLE_CTX
        ),
    )
    assert stats["sample_size"] <= 2
    assert stats["task_instance_count"] == 1
    assert stats["evidence_sufficient"] is False


def test_comparable_history_changes_ranking(store: OutcomeFeedbackStore):
    cold = store.rank_capabilities(
        [
            {"capability": "compose.extract_fields"},
            {"capability": "compose.extract_records"},
        ],
        available_capabilities=list_composable_capabilities(),
        strategy_context=TABLE_CTX,
    )
    assert cold[0]["recommendation_basis"] == "current_suitability"
    # extract_records is the applicable deterministic choice for tables.
    assert cold[0]["capability"] == "compose.extract_records"

    # Fail extract_fields under table context; succeed extract_records across 3 instances.
    for i in range(3):
        store.ingest_receipt(
            {
                **_mk_receipt(100 + i, "compose.extract_fields", verified=False),
                "outcome": {
                    "capability": "compose.extract_fields",
                    "success": False,
                    "failure_category": "incorrect_result",
                    "task_class": TABLE_CTX["task_class"],
                },
            },
            conversation_id=f"conv_{(i):016x}",
            strategy_context={
                **TABLE_CTX,
                "required_output_type": "structured_fields",
                "input_structure": "markdown_table",
            },
            step={
                "capability": "compose.extract_fields",
                "last_failure_category": "incorrect_result",
            },
            evaluation={"met": False, "category": "incorrect_result"},
        )
        store.ingest_receipt(
            _mk_receipt(200 + i, "compose.extract_records"),
            conversation_id=f"conv_{(i):016x}",
            strategy_context=TABLE_CTX,
            evaluation={"met": True},
        )
    warm = store.rank_capabilities(
        [
            {"capability": "compose.extract_fields"},
            {"capability": "compose.extract_records"},
        ],
        available_capabilities=list_composable_capabilities(),
        strategy_context=TABLE_CTX,
    )
    # extract_fields cannot satisfy structured_records → filtered out
    assert all(r["capability"] != "compose.extract_fields" for r in warm)
    assert warm[0]["capability"] == "compose.extract_records"
    assert warm[0]["recommendation_basis"] == "measured_history"


def test_environment_outage_excluded(store: OutcomeFeedbackStore):
    for i in range(6):
        store.ingest_receipt(
            {
                **_mk_receipt(i + 1, "local.documents.search", verified=False),
                "outcome": {
                    "capability": "local.documents.search",
                    "success": False,
                    "failure_category": "upstream_stale",
                },
            },
            conversation_id=f"conv_{(i % 3):016x}",
            strategy_context={
                "task_class": "authorized_document_retrieval",
                "required_output_type": "document_excerpts",
                "input_structure": "free_text",
                "verification_mode": "evidence_criteria",
            },
            step={
                "capability": "local.documents.search",
                "last_failure_category": "upstream_stale",
            },
            evaluation={"met": False, "category": "stale_upstream"},
        )
    stats = store.stats_for(
        "local.documents.search",
        strategy_context=build_strategy_context(
            "local.documents.search",
            explicit={
                "task_class": "authorized_document_retrieval",
                "required_output_type": "document_excerpts",
                "input_structure": "free_text",
                "verification_mode": "evidence_criteria",
            },
        ),
    )
    assert stats["sample_size"] == 0


def test_external_ingest_requires_host_path(store: OutcomeFeedbackStore):
    with pytest.raises(OutcomeFeedbackError, match="host_execution_path"):
        store.ingest_receipt(
            {
                "execution_id": "exec_abcdef0123456789",
                "capability": "compose.extract_records",
                "verified": True,
                "outcome": {"success": True},
            },
            require_host_path=True,
        )


def test_real_execution_ingests_comparable_context(tmp_path: Path):
    docs = tmp_path / "tables"
    docs.mkdir()
    (docs / "stock.md").write_text(
        "| Item | Qty |\n| --- | --- |\n| Cedar | 3 |\n| Maple | 1 |\n",
        encoding="utf-8",
    )
    cs = ConversationStore(
        resolve_conversation_root(tmp_path),
        outcome_store=OutcomeFeedbackStore(
            resolve_outcome_feedback_root(tmp_path),
            min_attempts=3,
            min_task_instances=3,
        ),
    )
    before = cs.outcome_store.export_store()["entry_count"]
    conv = cs.create(
        objective="Extract inventory table rows",
        completion_condition="Verified structured records from markdown table",
    )
    cid = conv["conversation_id"]
    saved = cs.commit_operator_task_state(
        cid,
        expected_revision=0,
        outstanding_steps=["search", "extract records"],
        next_safe_action="search",
    )
    search_id, rec_id = [s["step_id"] for s in saved["conversation"]["task_steps"]]
    rev = int(saved["conversation"]["checkpoint_revision"])
    fp = folder_fingerprint(str(docs))
    bound = cs.bind_operator_step(
        cid,
        step_id=search_id,
        expected_revision=rev,
        capability="local.documents.search",
        arguments={
            "query": "Cedar",
            "min_matches": 1,
            "required_substring": "Maple",
            "expected_relative_path": "stock.md",
            "folder_label": docs.name,
            "folder_fingerprint": fp,
        },
    )
    rev = int(bound["conversation"]["checkpoint_revision"])
    exe = cs.execute_verified_bound_step(
        cid,
        step_id=search_id,
        expected_revision=rev,
        authorize_documents_search=True,
        authorize_record_completion=True,
        documents_folder=str(docs),
    )
    assert exe["verified"] is True
    rev = int(exe["conversation"]["checkpoint_revision"])
    schema = {
        "schema_id": "inv",
        "record_key_field": "item",
        "fields": [
            {
                "id": "item",
                "type": "string",
                "required": True,
                "labels": ["Item"],
                "max_length": 40,
            },
            {
                "id": "qty",
                "type": "integer",
                "required": True,
                "labels": ["Qty"],
                "min": 1,
                "max": 100,
            },
        ],
    }
    bound = cs.bind_operator_step(
        cid,
        step_id=rec_id,
        expected_revision=rev,
        capability="compose.extract_records",
        arguments={"schema": schema, "evidence_step_ids": [search_id]},
    )
    rev = int(bound["conversation"]["checkpoint_revision"])
    rec = cs.execute_verified_bound_step(
        cid,
        step_id=rec_id,
        expected_revision=rev,
        authorize_compose_extract_records=True,
        authorize_record_completion=True,
    )
    assert rec["verified"] is True
    after = cs.outcome_store.export_store()
    assert after["entry_count"] > before
    # Entries carry comparison keys from real execution.
    entries = after["entries"]
    rec_entries = [e for e in entries if e.get("capability") == "compose.extract_records"]
    assert rec_entries
    assert rec_entries[-1].get("comparison_key", "").startswith("ck_")
    assert rec_entries[-1].get("host_execution_path") is True
    assert rec_entries[-1].get("strategy_context", {}).get("required_output_type") == (
        "structured_records"
    )
