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
)
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
