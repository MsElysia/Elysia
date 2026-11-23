"""FOA-002 transitive invalidation and restart-safe selective recomputation."""
from __future__ import annotations

import json
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
    _checkpoint_content_sha,
    resolve_conversation_root,
)


class _RejectedDraftModel:
    model = "synthetic-rejected-draft"

    def generate(self, messages, json_mode=False):
        return '{"draft":"unsupported"}'


class TransitiveInvalidationResumeTests(unittest.TestCase):
    def test_forged_receipt_and_corrupt_checkpoint_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = resolve_conversation_root(Path(tmp))
            store = ConversationStore(root)
            conv = store.create(objective="Synthetic receipt admission")
            cid = conv["conversation_id"]
            saved = store.commit_operator_task_state(
                cid,
                expected_revision=0,
                outstanding_steps=["Calculate input", "Aggregate input"],
                next_safe_action="Calculate input",
            )
            input_id, aggregate_id = [
                step["step_id"] for step in saved["conversation"]["task_steps"]
            ]
            bound = store.bind_operator_step(
                cid,
                step_id=input_id,
                expected_revision=saved["conversation"]["checkpoint_revision"],
                capability="calculator.labor",
                arguments={
                    "hourly_rate_usd": "420",
                    "painters": 1,
                    "days": 1,
                    "hours_per_day": 1,
                },
            )
            completed = store.execute_verified_bound_step(
                cid,
                step_id=input_id,
                expected_revision=bound["conversation"]["checkpoint_revision"],
                authorize_calculator=True,
                authorize_record_completion=True,
                execution_id="exec_" + "7" * 16,
            )
            bound = store.bind_operator_step(
                cid,
                step_id=aggregate_id,
                expected_revision=completed["conversation"]["checkpoint_revision"],
                capability="compose.aggregate_usd",
                arguments={"source_step_ids": [input_id]},
            )
            revision = bound["conversation"]["checkpoint_revision"]
            conversation_path = store._conv_path(cid)
            checkpoint_path = store._checkpoint_path(cid)
            original_conversation = conversation_path.read_text(encoding="utf-8")
            original_checkpoint = checkpoint_path.read_text(encoding="utf-8")

            def attempt() -> None:
                ConversationStore(root).execute_verified_bound_step(
                    cid,
                    step_id=aggregate_id,
                    expected_revision=revision,
                    authorize_compose_aggregate=True,
                    authorize_record_completion=True,
                    execution_id="exec_" + "8" * 16,
                )

            # A conversation-only receipt forgery disagrees with the durable
            # checkpoint and is rejected before any downstream execution.
            forged_conversation = json.loads(original_conversation)
            forged_input = next(
                step
                for step in forged_conversation["task_steps"]
                if step["step_id"] == input_id
            )
            forged_input["execution_receipt_id"] = None
            forged_input["result_reference"].pop("execution_id", None)
            forged_input["execution_history"] = []
            conversation_path.write_text(
                json.dumps(forged_conversation), encoding="utf-8"
            )
            with self.assertRaisesRegex(ContinuityError, "task state mismatch"):
                attempt()

            conversation_path.write_text(original_conversation, encoding="utf-8")
            corrupt_checkpoint = json.loads(original_checkpoint)
            corrupt_checkpoint["content_sha256"] = "0" * 64
            checkpoint_path.write_text(
                json.dumps(corrupt_checkpoint), encoding="utf-8"
            )
            with self.assertRaisesRegex(ContinuityError, "integrity mismatch"):
                attempt()

            checkpoint_path.write_text("{interrupted", encoding="utf-8")
            with self.assertRaisesRegex(ContinuityError, "checkpoint unreadable"):
                attempt()

            # Even a structurally valid reconstructed checkpoint cannot make a
            # missing receipt authoritative: executor admission checks the
            # step's receipt/reference/history/revision lineage.
            conversation_path.write_text(
                json.dumps(forged_conversation), encoding="utf-8"
            )
            forged_checkpoint = json.loads(original_checkpoint)
            forged_checkpoint["task_steps"] = forged_conversation["task_steps"]
            forged_checkpoint["content_sha256"] = _checkpoint_content_sha(
                forged_checkpoint
            )
            checkpoint_path.write_text(
                json.dumps(forged_checkpoint), encoding="utf-8"
            )
            with self.assertRaisesRegex(ContinuityError, "receipt invalid"):
                attempt()

            # A receipt borrowed from another execution also fails because its
            # result reference and verified history/revision must agree.
            forged_receipt = json.loads(original_conversation)
            forged_input = next(
                step
                for step in forged_receipt["task_steps"]
                if step["step_id"] == input_id
            )
            forged_input["execution_receipt_id"] = "exec_" + "f" * 16
            forged_input["result_reference"]["execution_id"] = "exec_" + "f" * 16
            conversation_path.write_text(json.dumps(forged_receipt), encoding="utf-8")
            forged_checkpoint["task_steps"] = forged_receipt["task_steps"]
            forged_checkpoint["content_sha256"] = _checkpoint_content_sha(
                forged_checkpoint
            )
            checkpoint_path.write_text(
                json.dumps(forged_checkpoint), encoding="utf-8"
            )
            with self.assertRaisesRegex(ContinuityError, "receipt invalid"):
                attempt()

            # Simulate checkpoint-written/conversation-not-written interruption.
            conversation_path.write_text(original_conversation, encoding="utf-8")
            ahead_checkpoint = json.loads(original_checkpoint)
            ahead_checkpoint["revision"] += 1
            ahead_checkpoint["content_sha256"] = _checkpoint_content_sha(
                ahead_checkpoint
            )
            checkpoint_path.write_text(
                json.dumps(ahead_checkpoint), encoding="utf-8"
            )
            with self.assertRaisesRegex(ContinuityError, "revision mismatch"):
                attempt()

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
