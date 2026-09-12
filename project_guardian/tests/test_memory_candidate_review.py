# project_guardian/tests/test_memory_candidate_review.py

from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_guardian.local_ingestion.memory_candidate_review import (
    MemoryCandidateReviewError,
    approve_candidate,
    edit_candidate,
    list_candidates,
    load_queue_candidates,
    reject_candidate,
    resolve_review_paths,
)
from project_guardian.local_ingestion.memory_candidates import (
    review_queue_path,
)
from project_guardian.local_ingestion.transcription_ingest import ingest_transcriptions


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def _stage_one_candidate(dest: Path, *, filename: str, text: str) -> str:
    source = dest.parent / "source"
    source.mkdir(exist_ok=True)
    _write(source / filename, text)
    ingest_transcriptions(
        source,
        dest,
        apply=True,
        stage_memory_candidates=True,
    )
    queue = review_queue_path(dest)
    record = json.loads(queue.read_text(encoding="utf-8").strip().splitlines()[0])
    return str(record["candidate_id"])


def test_list_pending_writes_nothing(tmp_path):
    dest = tmp_path / "dest"
    candidate_id = _stage_one_candidate(dest, filename="note.txt", text="Pending review text.")

    paths = resolve_review_paths(dest_dir=dest)
    decisions_before = paths.decisions_path.exists()
    report = list_candidates(paths, include_all=False)

    assert report.count == 1
    assert report.candidates[0]["candidate_id"] == candidate_id
    assert report.candidates[0]["effective_review_status"] == "pending"
    assert decisions_before is False
    assert not paths.decisions_path.exists()


def test_approve_records_decision_without_live_memory_write(tmp_path):
    dest = tmp_path / "dest"
    candidate_id = _stage_one_candidate(dest, filename="approve.txt", text="Approve me.")
    paths = resolve_review_paths(dest_dir=dest)

    report = approve_candidate(paths, candidate_id, notes="useful memory")

    assert report.decision["new_status"] == "approved"
    assert report.decision["live_memory_written"] is False
    assert report.decision["operator_required"] is True
    decision = json.loads(paths.decisions_path.read_text(encoding="utf-8").strip())
    assert decision["notes"] == "useful memory"
    approved = json.loads(paths.approved_path.read_text(encoding="utf-8").strip())
    assert approved["effective_review_status"] == "approved"
    assert approved["live_memory_written"] is False


def test_reject_records_decision_and_preserves_source_files(tmp_path):
    dest = tmp_path / "dest"
    candidate_id = _stage_one_candidate(dest, filename="reject.txt", text="Reject me.")
    paths = resolve_review_paths(dest_dir=dest)
    source_text = Path(json.loads(review_queue_path(dest).read_text(encoding="utf-8").strip())["source_text_path"])
    before = source_text.read_bytes()

    report = reject_candidate(paths, candidate_id, notes="not useful")

    assert report.decision["new_status"] == "rejected"
    assert report.decision["live_memory_written"] is False
    assert source_text.read_bytes() == before
    rejected = json.loads(paths.rejected_path.read_text(encoding="utf-8").strip())
    assert rejected["candidate_id"] == candidate_id


def test_edit_records_decision_and_writes_edited_artifact(tmp_path):
    dest = tmp_path / "dest"
    candidate_id = _stage_one_candidate(dest, filename="edit.txt", text="Original staged text.")
    paths = resolve_review_paths(dest_dir=dest)
    source_text = Path(json.loads(review_queue_path(dest).read_text(encoding="utf-8").strip())["source_text_path"])
    before = source_text.read_bytes()
    replacement = "Cleaned operator-edited text."

    report = edit_candidate(paths, candidate_id, replacement, notes="cleaned up")

    assert report.decision["new_status"] == "edited"
    assert report.decision["live_memory_written"] is False
    assert report.edited_text_path
    edited = Path(report.edited_text_path)
    assert edited.read_text(encoding="utf-8").strip() == replacement
    assert source_text.read_bytes() == before
    assert report.decision["edited_text_path"] == str(edited)


def test_duplicate_approve_fails_without_force(tmp_path):
    dest = tmp_path / "dest"
    candidate_id = _stage_one_candidate(dest, filename="dup.txt", text="Only once.")
    paths = resolve_review_paths(dest_dir=dest)
    approve_candidate(paths, candidate_id)

    with pytest.raises(MemoryCandidateReviewError, match="already has final decision"):
        approve_candidate(paths, candidate_id)


def test_missing_candidate_fails_clearly(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    queue = review_queue_path(dest)
    queue.parent.mkdir(parents=True)
    queue.write_text("", encoding="utf-8")

    paths = resolve_review_paths(dest_dir=dest)
    with pytest.raises(MemoryCandidateReviewError, match="Candidate not found"):
        approve_candidate(paths, "missing-candidate-id")


def test_malformed_queue_fails_safely(tmp_path):
    dest = tmp_path / "dest"
    queue = review_queue_path(dest)
    queue.parent.mkdir(parents=True)
    queue.write_text("{not valid json\n", encoding="utf-8")
    paths = resolve_review_paths(dest_dir=dest)

    with pytest.raises(MemoryCandidateReviewError, match="Malformed JSON"):
        load_queue_candidates(paths.queue_path)


def test_review_does_not_touch_live_memory_modules(tmp_path, monkeypatch):
    dest = tmp_path / "dest"
    candidate_id = _stage_one_candidate(dest, filename="safe.txt", text="No live memory.")
    paths = resolve_review_paths(dest_dir=dest)

    def _boom(*_args, **_kwargs):
        raise AssertionError("live memory must not be called")

    monkeypatch.setattr("project_guardian.memory.MemoryCore.remember", _boom, raising=False)

    approve_candidate(paths, candidate_id)
