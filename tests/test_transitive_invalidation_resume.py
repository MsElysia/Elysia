"""FOA-002 transitive invalidation and restart-safe selective recomputation."""
from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if "project_guardian" not in sys.modules:
    package = types.ModuleType("project_guardian")
    package.__path__ = [str(_ROOT / "project_guardian")]
    package.__package__ = "project_guardian"
    sys.modules["project_guardian"] = package

from project_guardian.conversation_continuity import (  # noqa: E402
    ContinuityError,
    ConversationStore,
    StaleTaskEditError,
    resolve_conversation_root,
)


class _RejectedDraftModel:
    model = "synthetic-rejected-draft"

    def generate(self, messages, json_mode=False):
        return '{"draft":"unsupported"}'


class TransitiveInvalidationResumeTests(unittest.TestCase):
    def test_corrected_input_invalidates_chain_and_requires_fresh_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = resolve_conversation_root(Path(tmp))
            store = ConversationStore(root)
            conv = store.create(objective="Synthetic estimate correction")
            cid = conv["conversation_id"]
            saved = store.commit_operator_task_state(
                cid,
                expected_revision=0,
                outstanding_steps=[
                    "Calculate fictional materials",
                    "Calculate fictional labor",
                    "Aggregate verified subtotal",
                    "Draft fictional estimate",
                ],
                next_safe_action="Calculate fictional materials",
            )
            material_id, labor_id, aggregate_id, draft_id = [
                step["step_id"] for step in saved["conversation"]["task_steps"]
            ]

            def revision(result):
                return int(result["conversation"]["checkpoint_revision"])

            rev = revision(saved)
            bound = store.bind_operator_step(
                cid,
                step_id=material_id,
                expected_revision=rev,
                capability="calculator.labor",
                arguments={
                    "hourly_rate_usd": "420",
                    "painters": 1,
                    "days": 1,
                    "hours_per_day": 1,
                },
            )
            material = store.execute_verified_bound_step(
                cid,
                step_id=material_id,
                expected_revision=revision(bound),
                authorize_calculator=True,
                authorize_record_completion=True,
                execution_id="exec_" + "a" * 16,
            )
            bound = store.bind_operator_step(
                cid,
                step_id=labor_id,
                expected_revision=revision(material),
                capability="calculator.labor",
                arguments={
                    "hourly_rate_usd": "35",
                    "painters": 2,
                    "days": 3,
                    "hours_per_day": 8,
                },
            )
            labor = store.execute_verified_bound_step(
                cid,
                step_id=labor_id,
                expected_revision=revision(bound),
                authorize_calculator=True,
                authorize_record_completion=True,
                execution_id="exec_" + "b" * 16,
            )
            labor_receipt = labor["receipt"]
            bound = store.bind_operator_step(
                cid,
                step_id=aggregate_id,
                expected_revision=revision(labor),
                capability="compose.aggregate_usd",
                arguments={
                    "components": [
                        {"step_id": material_id, "label": "materials"},
                        {"step_id": labor_id, "label": "labor"},
                    ]
                },
            )
            aggregate = store.execute_verified_bound_step(
                cid,
                step_id=aggregate_id,
                expected_revision=revision(bound),
                authorize_compose_aggregate=True,
                authorize_record_completion=True,
                execution_id="exec_" + "c" * 16,
            )
            self.assertEqual(aggregate["receipt"]["subtotal_usd"], "2100.00")
            bound = store.bind_operator_step(
                cid,
                step_id=draft_id,
                expected_revision=revision(aggregate),
                capability="compose.synthesize",
                arguments={
                    "evidence_step_ids": [aggregate_id],
                    "aggregate_step_id": aggregate_id,
                    "mode": "draft",
                },
            )
            draft = store.execute_verified_bound_step(
                cid,
                step_id=draft_id,
                expected_revision=revision(bound),
                authorize_compose_synthesize=True,
                authorize_record_completion=True,
                execution_id="exec_" + "d" * 16,
                draft_model=_RejectedDraftModel(),
            )

            reopened = store.reopen_operator_step(
                cid,
                step_id=material_id,
                expected_revision=revision(draft),
            )
            self.assertEqual(
                reopened["stale_dependent_steps"], [aggregate_id, draft_id]
            )
            by_id = {
                step["step_id"]: step for step in reopened["conversation"]["task_steps"]
            }
            self.assertEqual(by_id[aggregate_id]["status"], "pending")
            self.assertEqual(by_id[draft_id]["status"], "pending")
            self.assertTrue(by_id[aggregate_id]["result_reference"]["stale"])
            self.assertTrue(by_id[draft_id]["result_reference"]["stale"])
            self.assertEqual(by_id[labor_id]["status"], "completed")
            self.assertEqual(by_id[labor_id]["execution_receipt_id"], labor_receipt["execution_id"])
            self.assertNotIn(
                "Aggregate verified subtotal",
                reopened["conversation"]["completed_work"],
            )
            self.assertNotIn(
                "Draft fictional estimate",
                reopened["conversation"]["completed_work"],
            )
            self.assertEqual(
                reopened["conversation"]["next_safe_action"],
                "Calculate fictional materials",
            )
            duplicate = store.reopen_operator_step(
                cid,
                step_id=material_id,
                expected_revision=revision(draft),
            )
            self.assertTrue(duplicate["idempotent"])

            # A fresh store proves pending/current projection survives restart.
            resumed = ConversationStore(root)
            loaded = resumed.get(cid)
            self.assertEqual(loaded["next_safe_action"], "Calculate fictional materials")
            self.assertEqual(
                [s["step_id"] for s in loaded["task_steps"] if s["status"] == "pending"],
                [material_id, aggregate_id, draft_id],
            )

            bound = resumed.bind_operator_step(
                cid,
                step_id=material_id,
                expected_revision=int(loaded["checkpoint_revision"]),
                capability="calculator.labor",
                arguments={
                    "hourly_rate_usd": "480",
                    "painters": 1,
                    "days": 1,
                    "hours_per_day": 1,
                },
            )
            with self.assertRaises(StaleTaskEditError):
                resumed.execute_verified_bound_step(
                    cid,
                    step_id=material_id,
                    expected_revision=revision(reopened),
                    authorize_calculator=True,
                    authorize_record_completion=True,
                )
            with self.assertRaisesRegex(ContinuityError, "not authorized"):
                resumed.execute_verified_bound_step(
                    cid,
                    step_id=material_id,
                    expected_revision=revision(bound),
                    authorize_calculator=False,
                    authorize_record_completion=True,
                )
            material2 = resumed.execute_verified_bound_step(
                cid,
                step_id=material_id,
                expected_revision=revision(bound),
                authorize_calculator=True,
                authorize_record_completion=True,
                execution_id="exec_" + "e" * 16,
            )
            self.assertEqual(
                material2["conversation"]["next_safe_action"],
                "Aggregate verified subtotal",
            )
            with self.assertRaisesRegex(ContinuityError, "not authorized"):
                resumed.execute_verified_bound_step(
                    cid,
                    step_id=aggregate_id,
                    expected_revision=revision(material2),
                    authorize_compose_aggregate=False,
                    authorize_record_completion=True,
                )
            aggregate2 = resumed.execute_verified_bound_step(
                cid,
                step_id=aggregate_id,
                expected_revision=revision(material2),
                authorize_compose_aggregate=True,
                authorize_record_completion=True,
                execution_id="exec_" + "f" * 16,
            )
            self.assertEqual(aggregate2["receipt"]["subtotal_usd"], "2160.00")
            draft2 = resumed.execute_verified_bound_step(
                cid,
                step_id=draft_id,
                expected_revision=revision(aggregate2),
                authorize_compose_synthesize=True,
                authorize_record_completion=True,
                execution_id="exec_" + "1" * 16,
                draft_model=_RejectedDraftModel(),
            )
            self.assertIn("2160.00", draft2["conversation"]["estimate_draft"]["text"])
            final_by_id = {
                step["step_id"]: step for step in draft2["conversation"]["task_steps"]
            }
            self.assertEqual(final_by_id[labor_id]["execution_receipt_id"], labor_receipt["execution_id"])
            self.assertEqual(len(final_by_id[labor_id]["execution_history"]), 1)


if __name__ == "__main__":
    unittest.main()
