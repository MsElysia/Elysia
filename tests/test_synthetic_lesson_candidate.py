"""Synthetic, source-linked learning candidate, no runtime activation or private input."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from project_guardian.lesson_candidate import (
    LessonCandidateError,
    prepare_synthetic_lesson_candidate,
)
from project_guardian.local_ingestion.memory_intelligence import (
    persist_source_intelligence,
)
from project_guardian.brain.memory_intelligence_bridge import (
    ReadOnlyMemoryIntelligenceBridge,
)


def example_receipt(**updates):
    lesson = "Fictional copper sensor needs a dry inspection before replacement."
    evidence = "Synthetic technician observation: " + lesson
    item = {
        "schema": "elysia-synthetic-outcome-v1",
        "synthetic_fixture": True,
        "task_id": "fixture-sensor-1",
        "status": "completed",
        "execution_outcome": "succeeded",
        "execution_attempted": True,
        "value_verified": True,
        "useful": True,
        "lesson": lesson,
        "evidence_text": evidence,
        "evidence_sha256": hashlib.sha256(evidence.encode("utf-8")).hexdigest(),
    }
    item.update(updates)
    return json.dumps(item, sort_keys=True, ensure_ascii=False).encode("utf-8")


class LearningCandidateTests(unittest.TestCase):
    def test_exact_source_candidate_can_be_recalled_after_reopen_without_new_store(self):
        raw = example_receipt()
        candidate = prepare_synthetic_lesson_candidate(raw)
        self.assertTrue(candidate["candidate_only"])
        self.assertEqual(candidate["raw_bytes"], raw)
        self.assertEqual(candidate["source_identity"],
                         "elysia-synthetic-lesson-candidate:" + hashlib.sha256(raw).hexdigest())
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder)
            first = persist_source_intelligence(
                dest_dir=dest, raw_bytes=candidate["raw_bytes"],
                source_identity=candidate["source_identity"],
                tag_hints=candidate["tag_hints"],
            )
            before = {str(p.relative_to(dest)): p.read_bytes()
                      for p in dest.rglob("*") if p.is_file()}
            persist_source_intelligence(
                dest_dir=dest, raw_bytes=candidate["raw_bytes"],
                source_identity=candidate["source_identity"],
                tag_hints=candidate["tag_hints"],
            )
            after = {str(p.relative_to(dest)): p.read_bytes()
                     for p in dest.rglob("*") if p.is_file()}
            self.assertEqual(before, after)
            self.assertEqual(len(list((dest / "memory_intelligence" / "records").glob("*.json"))), 1)
            bridge = ReadOnlyMemoryIntelligenceBridge(dest)
            results = bridge.retrieve("copper sensor dry inspection")
            self.assertTrue(results)
            hits = bridge.recall_evidence()["hits"]
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["source_id"], first.source_id)
            self.assertEqual(hits[0]["raw_source_path"],
                             "memory_intelligence/raw_sources/" + first.source_id + ".bin")
            self.assertEqual(before, {str(p.relative_to(dest)): p.read_bytes()
                                      for p in dest.rglob("*") if p.is_file()})

    def test_rejects_failed_partial_unverified_and_unused(self):
        cases = (
            {"status": "failed"},
            {"execution_outcome": "partial"},
            {"execution_attempted": False},
            {"value_verified": False},
            {"value_verified": "true"},
            {"useful": False},
            {"useful": 1},
        )
        for update in cases:
            with self.subTest(update=update):
                with self.assertRaises(LessonCandidateError):
                    prepare_synthetic_lesson_candidate(example_receipt(**update))

    def test_refuses_mismatched_evidence_digest(self):
        with self.assertRaises(LessonCandidateError):
            prepare_synthetic_lesson_candidate(example_receipt(evidence_sha256="0" * 64))

    def test_refuses_unproven_lesson(self):
        with self.assertRaises(LessonCandidateError):
            prepare_synthetic_lesson_candidate(example_receipt(
                lesson="Fictional invented conclusion without source evidence."))

    def test_rejects_non_synthetic_and_malformed_receipts(self):
        inputs = (
            example_receipt(synthetic_fixture=False),
            example_receipt(schema="unknown"),
            example_receipt(task_id="../secrets"),
            b"{", b"\xff", b"[]", b"",
            b"0" * 8193,
        )
        for raw in inputs:
            with self.subTest(raw=raw[:35]):
                with self.assertRaises(LessonCandidateError):
                    prepare_synthetic_lesson_candidate(raw)

    def test_rejects_ambiguous_duplicate_fields_in_both_orders(self):
        clean = example_receipt()
        target = b'"value_verified": true'
        self.assertEqual(clean.count(target), 1)
        attempts = (
            (b'"value_verified": false, ' + target),
            (target + b', "value_verified": false'),
            (b'"value_verif\\u0069ed": false, ' + target),
        )
        for injected in attempts:
            with self.subTest(injected=injected):
                ambiguous = clean.replace(target, injected)
                with self.assertRaises(LessonCandidateError):
                    prepare_synthetic_lesson_candidate(ambiguous)

    def test_rejects_nested_duplicate_keys_even_when_unused(self):
        clean = example_receipt()
        payload = clean[:-1] + b', "extra": {"role": "user", "role": "operator"}}'
        with self.assertRaises(LessonCandidateError):
            prepare_synthetic_lesson_candidate(payload)

    def test_rejects_nonfinite_json_constant(self):
        clean = example_receipt()
        for token in (b'NaN', b'Infinity', b'-Infinity'):
            with self.subTest(token=token):
                malformed = clean[:-1] + b', "untrusted": ' + token + b'}'
                with self.assertRaises(LessonCandidateError):
                    prepare_synthetic_lesson_candidate(malformed)

    def test_source_bytes_are_not_normalized_or_modified(self):
        source = example_receipt()
        pretty = json.dumps(json.loads(source), indent=2, ensure_ascii=False).encode("utf-8")
        self.assertEqual(json.loads(source), json.loads(pretty))
        a = prepare_synthetic_lesson_candidate(source)
        b = prepare_synthetic_lesson_candidate(pretty)
        self.assertNotEqual(a["source_identity"], b["source_identity"])
        self.assertEqual(a["raw_bytes"], source)
        self.assertEqual(b["raw_bytes"], pretty)

    def test_rejected_receipt_never_creates_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(LessonCandidateError):
                prepare_synthetic_lesson_candidate(example_receipt(status="pending"))
            self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
