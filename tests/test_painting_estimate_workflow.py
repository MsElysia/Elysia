"""Multi-tool painting estimate assembly, draft checks, and cross-step flow."""
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

from project_guardian.conversation_continuity import (
    ContinuityError,
    ConversationStore,
    resolve_conversation_root,
)
from project_guardian.local_documents_search import folder_fingerprint
from project_guardian.painting_estimate_workflow import (
    EstimateWorkflowError,
    assemble_estimate_subtotal,
    mark_dependent_steps_stale,
    verify_draft_amounts,
)


@pytest.fixture()
def store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(resolve_conversation_root(tmp_path))


@pytest.fixture()
def estimates(tmp_path: Path) -> Path:
    folder = tmp_path / "construction-estimates"
    folder.mkdir()
    (folder / "paint-estimate-duration.md").write_text(
        "Brand: Duration exterior paint\nMaterial cost: USD 482.50\n",
        encoding="utf-8",
    )
    return folder


def test_assemble_subtotal_deterministic():
    out = assemble_estimate_subtotal(
        material_usd="482.50",
        labor_usd="1680",
        material_link={"step_id": "step_aaaaaaaaaaaa"},
        labor_link={"step_id": "step_bbbbbbbbbbbb"},
    )
    assert out["subtotal_usd"] == "2162.50"
    assert out["components"]["materials"] == "482.50"
    assert out["components"]["labor"] == "1680.00"
    assert "markup" in " ".join(out["missing_cost_categories"]).casefold()


def test_draft_verify_rejects_invented_total():
    draft = (
        "DRAFT / NOT APPROVED FOR CUSTOMER DELIVERY\n"
        "Materials 482.50 Labor 1680.00 Subtotal 2162.50\n"
        "Also charge 9999.00 contingency.\n"
    )
    with pytest.raises(EstimateWorkflowError, match="unsupported figure"):
        verify_draft_amounts(
            draft, materials_usd="482.50", labor_usd="1680.00", subtotal_usd="2162.50"
        )


def test_draft_verify_accepts_clean_draft():
    draft = (
        "DRAFT / NOT APPROVED FOR CUSTOMER DELIVERY\n"
        "Materials USD 482.50 from paint-estimate-duration.md.\n"
        "Labor USD 1680.00 (2 painters x 3 days x 8 hours).\n"
        "Materials + labor subtotal USD 2162.50.\n"
        "Missing: taxes, markup, contingency.\n"
    )
    check = verify_draft_amounts(
        draft, materials_usd="482.50", labor_usd="1680.00", subtotal_usd="2162.50"
    )
    assert check["ok"] is True


def _run_materials_and_labor(store, estimates):
    conv = store.create(objective="Prepare a painting estimate")
    cid = conv["conversation_id"]
    saved = store.commit_operator_task_state(
        cid,
        expected_revision=0,
        outstanding_steps=[
            "Find material costs from previous estimates",
            "Calculate labor requirements",
            "Combine verified materials and labor",
            "Draft estimate for operator review",
        ],
        next_safe_action="Find material costs from previous estimates",
    )
    steps = saved["conversation"]["task_steps"]
    mat_id, labor_id, assemble_id, draft_id = [s["step_id"] for s in steps]
    rev = int(saved["conversation"]["checkpoint_revision"])
    bound = store.bind_operator_step(
        cid,
        step_id=mat_id,
        expected_revision=rev,
        capability="local.documents.search",
        arguments={
            "query": "Duration exterior paint",
            "min_matches": 1,
            "required_substring": "482.50",
            "expected_relative_path": "paint-estimate-duration.md",
            "folder_label": estimates.name,
            "folder_fingerprint": folder_fingerprint(str(estimates)),
        },
    )
    rev = int(bound["conversation"]["checkpoint_revision"])
    exe = store.execute_verified_bound_step(
        cid,
        step_id=mat_id,
        expected_revision=rev,
        authorize_documents_search=True,
        authorize_record_completion=True,
        documents_folder=str(estimates),
        execution_id="exec_" + "a" * 16,
    )
    assert exe["conversation"]["task_steps"][0]["result_reference"]["amount_usd"] == "482.50"
    rev = int(exe["conversation"]["checkpoint_revision"])
    bound = store.bind_operator_step(
        cid,
        step_id=labor_id,
        expected_revision=rev,
        capability="calculator.labor",
        arguments={"hourly_rate_usd": "35", "painters": 2, "days": 3, "hours_per_day": 8},
    )
    rev = int(bound["conversation"]["checkpoint_revision"])
    exe = store.execute_verified_bound_step(
        cid,
        step_id=labor_id,
        expected_revision=rev,
        authorize_calculator=True,
        authorize_record_completion=True,
        execution_id="exec_" + "b" * 16,
    )
    assert exe["receipt"]["result"] == "1680"
    rev = int(exe["conversation"]["checkpoint_revision"])
    return cid, mat_id, labor_id, assemble_id, draft_id, rev


def test_end_to_end_assemble_without_manual_reentry(store, estimates):
    cid, mat_id, labor_id, assemble_id, draft_id, rev = _run_materials_and_labor(
        store, estimates
    )
    bound = store.bind_operator_step(
        cid,
        step_id=assemble_id,
        expected_revision=rev,
        capability="estimate.assemble",
        arguments={"material_step_id": mat_id, "labor_step_id": labor_id},
    )
    rev = int(bound["conversation"]["checkpoint_revision"])
    with pytest.raises(ContinuityError, match="not authorized"):
        store.execute_verified_bound_step(
            cid,
            step_id=assemble_id,
            expected_revision=rev,
            authorize_estimate_assemble=False,
            authorize_record_completion=True,
        )
    exe = store.execute_verified_bound_step(
        cid,
        step_id=assemble_id,
        expected_revision=rev,
        authorize_estimate_assemble=True,
        authorize_record_completion=True,
        execution_id="exec_" + "c" * 16,
    )
    assert exe["receipt"]["subtotal_usd"] == "2162.50"
    assert exe["conversation"]["estimate_bundle"]["subtotal_usd"] == "2162.50"
    assert exe["conversation"]["next_safe_action"] == "Draft estimate for operator review"


def test_upstream_reopen_marks_assemble_stale(store, estimates):
    cid, mat_id, labor_id, assemble_id, draft_id, rev = _run_materials_and_labor(
        store, estimates
    )
    bound = store.bind_operator_step(
        cid,
        step_id=assemble_id,
        expected_revision=rev,
        capability="estimate.assemble",
        arguments={"material_step_id": mat_id, "labor_step_id": labor_id},
    )
    rev = int(bound["conversation"]["checkpoint_revision"])
    exe = store.execute_verified_bound_step(
        cid,
        step_id=assemble_id,
        expected_revision=rev,
        authorize_estimate_assemble=True,
        authorize_record_completion=True,
        execution_id="exec_" + "d" * 16,
    )
    rev = int(exe["conversation"]["checkpoint_revision"])
    reopened = store.reopen_operator_step(cid, step_id=mat_id, expected_revision=rev)
    assemble = next(
        s for s in reopened["conversation"]["task_steps"] if s["step_id"] == assemble_id
    )
    assert assemble["result_reference"]["stale"] is True
    assert reopened["conversation"]["estimate_bundle"]["stale"] is True


def test_draft_uses_mock_model(store, estimates):
    cid, mat_id, labor_id, assemble_id, draft_id, rev = _run_materials_and_labor(
        store, estimates
    )
    bound = store.bind_operator_step(
        cid,
        step_id=assemble_id,
        expected_revision=rev,
        capability="estimate.assemble",
        arguments={"material_step_id": mat_id, "labor_step_id": labor_id},
    )
    rev = int(bound["conversation"]["checkpoint_revision"])
    exe = store.execute_verified_bound_step(
        cid,
        step_id=assemble_id,
        expected_revision=rev,
        authorize_estimate_assemble=True,
        authorize_record_completion=True,
        execution_id="exec_" + "e" * 16,
    )
    rev = int(exe["conversation"]["checkpoint_revision"])
    bound = store.bind_operator_step(
        cid,
        step_id=draft_id,
        expected_revision=rev,
        capability="estimate.draft",
        arguments={"assemble_step_id": assemble_id},
    )
    rev = int(bound["conversation"]["checkpoint_revision"])

    class FakeModel:
        model = "fake"

        def generate(self, messages, json_mode=False):
            return (
                '{"draft":"DRAFT / NOT APPROVED FOR CUSTOMER DELIVERY\\n'
                "Materials 482.50 from paint-estimate-duration.md.\\n"
                "Labor 1680.00.\\n"
                'Subtotal 2162.50. Missing taxes and markup."}'
            )

    done = store.execute_verified_bound_step(
        cid,
        step_id=draft_id,
        expected_revision=rev,
        authorize_estimate_draft=True,
        authorize_record_completion=True,
        execution_id="exec_" + "f" * 16,
        draft_model=FakeModel(),
    )
    assert done["verified"] is True
    assert "2162.50" in done["conversation"]["estimate_draft"]["text"]
    assert done["conversation"]["estimate_draft"]["approved"] is False


def test_mark_dependent_helper():
    steps = [
        {
            "step_id": "step_aaaaaaaaaaaa",
            "capability": "estimate.assemble",
            "status": "completed",
            "verification_status": "verified",
            "arguments": {
                "material_step_id": "step_cccccccccccc",
                "labor_step_id": "step_dddddddddddd",
            },
            "result_reference": {"amount_usd": "2162.50"},
        }
    ]
    stale = mark_dependent_steps_stale(steps, changed_step_id="step_cccccccccccc")
    assert stale == ["step_aaaaaaaaaaaa"]
    assert steps[0]["result_reference"]["stale"] is True
