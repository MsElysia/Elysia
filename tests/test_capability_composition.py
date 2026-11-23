"""General capability composition: aggregate, synthesize, plan validation."""
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

from project_guardian.capability_composition import (
    CompositionError,
    aggregate_usd_amounts,
    list_composable_capabilities,
    parse_model_plan_json,
    validate_proposed_plan,
    verify_synthesize_output,
    first_ready_pending_step,
    mark_dependent_steps_stale,
)


def test_transitive_invalidation_preserves_unrelated_verified_receipt():
    changed = "step_aaaaaaaaaaaa"
    labor = {
        "step_id": "step_bbbbbbbbbbbb",
        "capability": "calculator.labor",
        "status": "completed",
        "verification_status": "verified",
        "execution_receipt_id": "exec_" + "b" * 16,
        "result_reference": {"amount_usd": "1680.00", "stale": False},
    }
    subtotal = {
        "step_id": "step_cccccccccccc",
        "capability": "estimate.assemble",
        "status": "completed",
        "verification_status": "verified",
        "execution_receipt_id": "exec_" + "c" * 16,
        "arguments": {
            "material_step_id": changed,
            "labor_step_id": labor["step_id"],
        },
        "result_reference": {"amount_usd": "2100.00", "stale": False},
        "execution_history": [{"execution_id": "exec_" + "c" * 16}],
    }
    draft = {
        "step_id": "step_dddddddddddd",
        "capability": "estimate.draft",
        "status": "completed",
        "verification_status": "verified",
        "execution_receipt_id": "exec_" + "d" * 16,
        "arguments": {"assemble_step_id": subtotal["step_id"]},
        "result_reference": {"draft_sha256": "abc", "stale": False},
        "execution_history": [{"execution_id": "exec_" + "d" * 16}],
    }

    # Deliberately reverse dependency order to prove graph traversal is not
    # coupled to plan display order.
    steps = [draft, labor, subtotal]
    stale = mark_dependent_steps_stale(steps, changed_step_id=changed)

    assert stale == [subtotal["step_id"], draft["step_id"]]
    assert subtotal["status"] == draft["status"] == "pending"
    assert subtotal["verification_status"] == draft["verification_status"] == "failed"
    assert subtotal["execution_receipt_id"] == "exec_" + "c" * 16
    assert draft["execution_receipt_id"] == "exec_" + "d" * 16
    assert subtotal["execution_history"][0]["execution_id"] == "exec_" + "c" * 16
    assert draft["execution_history"][0]["execution_id"] == "exec_" + "d" * 16
    assert labor == {
        "step_id": "step_bbbbbbbbbbbb",
        "capability": "calculator.labor",
        "status": "completed",
        "verification_status": "verified",
        "execution_receipt_id": "exec_" + "b" * 16,
        "result_reference": {"amount_usd": "1680.00", "stale": False},
    }


def test_transitive_invalidation_handles_diamond_once_in_dependency_order():
    root = "step_aaaaaaaaaaaa"
    left = {
        "step_id": "step_bbbbbbbbbbbb",
        "capability": "compose.extract_fields",
        "status": "completed",
        "verification_status": "verified",
        "arguments": {"source_step_ids": [root]},
        "result_reference": {"stale": False},
    }
    right = {
        "step_id": "step_cccccccccccc",
        "capability": "compose.extract_records",
        "status": "completed",
        "verification_status": "verified",
        "arguments": {"source_step_ids": [root]},
        "result_reference": {"stale": False},
    }
    join = {
        "step_id": "step_dddddddddddd",
        "capability": "compose.aggregate_usd",
        "status": "completed",
        "verification_status": "verified",
        "arguments": {"source_step_ids": [right["step_id"], left["step_id"]]},
        "result_reference": {"stale": False},
    }

    stale = mark_dependent_steps_stale([join, right, left], changed_step_id=root)

    assert stale == [right["step_id"], left["step_id"], join["step_id"]]
    assert len(stale) == len(set(stale))


def test_ready_projection_ignores_display_order_and_rejects_cycle_before_mutation():
    root = {
        "step_id": "step_aaaaaaaaaaaa",
        "capability": "calculator.labor",
        "status": "completed",
        "execution_status": "succeeded",
        "verification_status": "verified",
        "execution_receipt_id": "exec_" + "a" * 16,
        "completion_source": "operator_verified_execution",
        "completed_at_revision": 2,
        "result_reference": {
            "execution_id": "exec_" + "a" * 16,
            "amount_usd": "480.00",
            "stale": False,
        },
        "execution_history": [
            {
                "execution_id": "exec_" + "a" * 16,
                "verified": True,
                "checkpoint_revision": 2,
            }
        ],
    }
    direct = {
        "step_id": "step_bbbbbbbbbbbb",
        "capability": "compose.aggregate_usd",
        "status": "pending",
        "verification_status": "failed",
        "arguments": {"source_step_ids": [root["step_id"]]},
        "result_reference": {"stale": True},
    }
    downstream = {
        "step_id": "step_cccccccccccc",
        "capability": "compose.synthesize",
        "status": "pending",
        "verification_status": "failed",
        "arguments": {"evidence_step_ids": [direct["step_id"]]},
        "result_reference": {"stale": True},
    }
    assert first_ready_pending_step([downstream, direct, root]) is direct
    unknown = {
        "step_id": "step_ffffffffffff",
        "capability": "compose.aggregate_usd",
        "status": "pending",
        "verification_status": "failed",
        "arguments": {"source_step_ids": ["step_999999999999"]},
        "result_reference": {"stale": True},
    }
    assert first_ready_pending_step([unknown, root]) is None

    left = {
        "step_id": "step_dddddddddddd",
        "capability": "compose.aggregate_usd",
        "status": "completed",
        "verification_status": "verified",
        "arguments": {"source_step_ids": ["step_eeeeeeeeeeee"]},
        "result_reference": {"stale": False},
    }
    right = {
        "step_id": "step_eeeeeeeeeeee",
        "capability": "compose.synthesize",
        "status": "completed",
        "verification_status": "verified",
        "arguments": {"evidence_step_ids": [left["step_id"]]},
        "result_reference": {"stale": False},
    }
    with pytest.raises(CompositionError, match="cycle"):
        mark_dependent_steps_stale([left, right], changed_step_id=left["step_id"])
    assert left["result_reference"]["stale"] is False
    assert right["result_reference"]["stale"] is False
from project_guardian.conversation_continuity import (
    ContinuityError,
    ConversationStore,
    resolve_conversation_root,
)
from project_guardian.local_documents_search import folder_fingerprint


@pytest.fixture()
def store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(resolve_conversation_root(tmp_path))


@pytest.fixture()
def event_docs(tmp_path: Path) -> Path:
    folder = tmp_path / "community-event-budget"
    folder.mkdir()
    (folder / "venue-rental.md").write_text(
        "# Venue\nRental fee: USD 850.00\n", encoding="utf-8"
    )
    (folder / "catering.md").write_text(
        "# Catering\nQuoted catering: USD 1200.00\n", encoding="utf-8"
    )
    return folder


@pytest.fixture()
def research_docs(tmp_path: Path) -> Path:
    folder = tmp_path / "research-notes"
    folder.mkdir()
    (folder / "study-alpha.md").write_text(
        "# Study Alpha\nFinding: blue jays prefer oak nesting sites.\n"
        "Sample size: 42 nests observed.\n",
        encoding="utf-8",
    )
    (folder / "study-beta.md").write_text(
        "# Study Beta\nFinding: blue jays prefer pine nesting sites.\n"
        "Sample size: 18 nests observed.\n",
        encoding="utf-8",
    )
    return folder


def test_aggregate_usd_deterministic():
    out = aggregate_usd_amounts(
        components=[
            {"amount_usd": "850.00", "label": "venue"},
            {"amount_usd": "1200", "label": "catering"},
        ],
        bundle_label="event line-item subtotal",
        missing_categories=["contingency"],
    )
    assert out["subtotal_usd"] == "2050.00"
    assert out["components"]["venue"] == "850.00"
    assert out["components"]["catering"] == "1200.00"


def test_synthesize_rejects_invented_amount():
    draft = (
        "DRAFT / NOT APPROVED FOR CUSTOMER DELIVERY\n"
        "Venue 850.00 Catering 1200.00 Subtotal 2050.00\n"
        "Also budget 7777.00 for surprise fireworks.\n"
    )
    with pytest.raises(CompositionError, match="unsupported figure"):
        verify_synthesize_output(
            draft,
            banner="DRAFT / NOT APPROVED FOR CUSTOMER DELIVERY",
            required_amounts=["850.00", "1200.00", "2050.00"],
        )


def test_plan_validation_rejects_unknown_capability():
    caps = list_composable_capabilities()
    with pytest.raises(CompositionError, match="unavailable"):
        validate_proposed_plan(
            {
                "objective": "Do something",
                "steps": [
                    {
                        "capability": "cloud.magic.write",
                        "expected_outcome": "invent results",
                    }
                ],
            },
            caps,
        )


def test_plan_parse_and_validate_ok():
    raw = (
        '{"objective":"Event budget","steps":['
        '{"capability":"local.documents.search","expected_outcome":"venue cost"},'
        '{"capability":"compose.aggregate_usd","expected_outcome":"subtotal","depends_on":[0]}'
        "]}"
    )
    proposed = parse_model_plan_json(raw)
    assert proposed is not None
    validated = validate_proposed_plan(proposed, list_composable_capabilities())
    assert validated["ok"] is True
    assert validated["executable"] is False
    assert validated["authorization_inherited"] is False
    assert len(validated["steps"]) == 2


def test_event_budget_compose_without_domain_module(store, event_docs):
    conv = store.create(objective="Prepare a fictional community event budget")
    cid = conv["conversation_id"]
    saved = store.commit_operator_task_state(
        cid,
        expected_revision=0,
        outstanding_steps=[
            "Retrieve venue rental cost",
            "Retrieve catering cost",
            "Aggregate verified event costs",
            "Summarize grounded budget",
        ],
        next_safe_action="Retrieve venue rental cost",
    )
    steps = saved["conversation"]["task_steps"]
    venue_id, catering_id, agg_id, syn_id = [s["step_id"] for s in steps]
    rev = int(saved["conversation"]["checkpoint_revision"])
    fp = folder_fingerprint(str(event_docs))

    bound = store.bind_operator_step(
        cid,
        step_id=venue_id,
        expected_revision=rev,
        capability="local.documents.search",
        arguments={
            "query": "venue rental",
            "min_matches": 1,
            "required_substring": "850.00",
            "expected_relative_path": "venue-rental.md",
            "folder_label": event_docs.name,
            "folder_fingerprint": fp,
        },
    )
    rev = int(bound["conversation"]["checkpoint_revision"])
    with pytest.raises(ContinuityError, match="not authorized"):
        store.execute_verified_bound_step(
            cid,
            step_id=venue_id,
            expected_revision=rev,
            authorize_documents_search=False,
            authorize_record_completion=True,
            documents_folder=str(event_docs),
        )
    venue = store.execute_verified_bound_step(
        cid,
        step_id=venue_id,
        expected_revision=rev,
        authorize_documents_search=True,
        authorize_record_completion=True,
        documents_folder=str(event_docs),
    )
    assert venue["verified"] is True
    rev = int(venue["conversation"]["checkpoint_revision"])

    bound = store.bind_operator_step(
        cid,
        step_id=catering_id,
        expected_revision=rev,
        capability="local.documents.search",
        arguments={
            "query": "catering",
            "min_matches": 1,
            "required_substring": "1200.00",
            "expected_relative_path": "catering.md",
            "folder_label": event_docs.name,
            "folder_fingerprint": fp,
        },
    )
    rev = int(bound["conversation"]["checkpoint_revision"])
    catering = store.execute_verified_bound_step(
        cid,
        step_id=catering_id,
        expected_revision=rev,
        authorize_documents_search=True,
        authorize_record_completion=True,
        documents_folder=str(event_docs),
    )
    rev = int(catering["conversation"]["checkpoint_revision"])

    bound = store.bind_operator_step(
        cid,
        step_id=agg_id,
        expected_revision=rev,
        capability="compose.aggregate_usd",
        arguments={
            "source_step_ids": [venue_id, catering_id],
            "component_labels": ["venue", "catering"],
            "domain_template": "event_budget",
        },
    )
    rev = int(bound["conversation"]["checkpoint_revision"])
    with pytest.raises(ContinuityError, match="not authorized"):
        store.execute_verified_bound_step(
            cid,
            step_id=agg_id,
            expected_revision=rev,
            authorize_compose_aggregate=False,
            authorize_record_completion=True,
        )
    aggregated = store.execute_verified_bound_step(
        cid,
        step_id=agg_id,
        expected_revision=rev,
        authorize_compose_aggregate=True,
        authorize_record_completion=True,
    )
    assert aggregated["receipt"]["subtotal_usd"] == "2050.00"
    rev = int(aggregated["conversation"]["checkpoint_revision"])

    class _MockModel:
        def generate(self, messages, *, json_mode=False):
            return (
                '{"draft":"DRAFT / NOT APPROVED FOR CUSTOMER DELIVERY\\n'
                "Venue USD 850.00 from venue-rental.md. "
                "Catering USD 1200.00 from catering.md. "
                'Event line-item subtotal USD 2050.00. Missing contingency."}'
            )

    bound = store.bind_operator_step(
        cid,
        step_id=syn_id,
        expected_revision=rev,
        capability="compose.synthesize",
        arguments={
            "evidence_step_ids": [venue_id, catering_id],
            "aggregate_step_id": agg_id,
            "mode": "summary",
            "domain_template": "event_budget",
            "required_phrases": ["venue-rental.md", "catering.md"],
        },
    )
    rev = int(bound["conversation"]["checkpoint_revision"])
    done = store.execute_verified_bound_step(
        cid,
        step_id=syn_id,
        expected_revision=rev,
        authorize_compose_synthesize=True,
        authorize_record_completion=True,
        draft_model=_MockModel(),
    )
    assert done["verified"] is True
    assert "2050.00" in done["conversation"]["estimate_draft"]["text"]
    assert done["conversation"]["estimate_draft"]["approved"] is False


def test_research_comparison_compose(store, research_docs):
    conv = store.create(objective="Compare fictional nest-site findings")
    cid = conv["conversation_id"]
    saved = store.commit_operator_task_state(
        cid,
        expected_revision=0,
        outstanding_steps=[
            "Retrieve study alpha evidence",
            "Retrieve study beta evidence",
            "Compare verified findings",
        ],
        next_safe_action="Retrieve study alpha evidence",
    )
    a_id, b_id, syn_id = [s["step_id"] for s in saved["conversation"]["task_steps"]]
    rev = int(saved["conversation"]["checkpoint_revision"])
    fp = folder_fingerprint(str(research_docs))

    for step_id, query, path, phrase in (
        (a_id, "oak nesting", "study-alpha.md", "oak nesting sites"),
        (b_id, "pine nesting", "study-beta.md", "pine nesting sites"),
    ):
        bound = store.bind_operator_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            capability="local.documents.search",
            arguments={
                "query": query,
                "min_matches": 1,
                "required_substring": phrase,
                "expected_relative_path": path,
                "folder_label": research_docs.name,
                "folder_fingerprint": fp,
            },
        )
        rev = int(bound["conversation"]["checkpoint_revision"])
        result = store.execute_verified_bound_step(
            cid,
            step_id=step_id,
            expected_revision=rev,
            authorize_documents_search=True,
            authorize_record_completion=True,
            documents_folder=str(research_docs),
        )
        rev = int(result["conversation"]["checkpoint_revision"])

    class _MockModel:
        def generate(self, messages, *, json_mode=False):
            return (
                '{"draft":"COMPARISON DRAFT / SOURCE-GROUNDED ONLY\\n'
                "Agreements: both study blue jays. "
                "Differences: study-alpha.md reports oak nesting sites; "
                'study-beta.md reports pine nesting sites. Unsupported: cause."}'
            )

    bound = store.bind_operator_step(
        cid,
        step_id=syn_id,
        expected_revision=rev,
        capability="compose.synthesize",
        arguments={
            "evidence_step_ids": [a_id, b_id],
            "mode": "comparison",
            "domain_template": "research_comparison",
            "required_phrases": ["study-alpha.md", "study-beta.md", "oak", "pine"],
            "banner": "COMPARISON DRAFT / SOURCE-GROUNDED ONLY",
        },
    )
    rev = int(bound["conversation"]["checkpoint_revision"])
    done = store.execute_verified_bound_step(
        cid,
        step_id=syn_id,
        expected_revision=rev,
        authorize_compose_synthesize=True,
        authorize_record_completion=True,
        draft_model=_MockModel(),
    )
    text = done["conversation"]["estimate_draft"]["text"]
    assert "study-alpha.md" in text and "study-beta.md" in text
    assert done["conversation"]["estimate_draft"]["capability"] == "compose.synthesize"


def test_model_claim_cannot_complete_without_verification(store, event_docs):
    """Model-shaped text alone must not mark a compose step verified."""
    conv = store.create(objective="Invent a verified budget")
    cid = conv["conversation_id"]
    saved = store.commit_operator_task_state(
        cid,
        expected_revision=0,
        outstanding_steps=["Aggregate without evidence", "Done"],
        next_safe_action="Aggregate without evidence",
    )
    agg_id = saved["conversation"]["task_steps"][0]["step_id"]
    rev = int(saved["conversation"]["checkpoint_revision"])
    # Binding with fake upstream ids is rejected at execute via resolve.
    fake_a = "step_" + "a" * 12
    fake_b = "step_" + "b" * 12
    bound = store.bind_operator_step(
        cid,
        step_id=agg_id,
        expected_revision=rev,
        capability="compose.aggregate_usd",
        arguments={"source_step_ids": [fake_a, fake_b]},
    )
    rev = int(bound["conversation"]["checkpoint_revision"])
    with pytest.raises(ContinuityError, match="upstream step not found|failed"):
        store.execute_verified_bound_step(
            cid,
            step_id=agg_id,
            expected_revision=rev,
            authorize_compose_aggregate=True,
            authorize_record_completion=True,
        )
    step = next(
        s
        for s in store.get(cid)["task_steps"]
        if s["step_id"] == agg_id
    )
    assert step["status"] == "pending"
