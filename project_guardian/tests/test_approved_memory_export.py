# project_guardian/tests/test_approved_memory_export.py

from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_guardian.local_ingestion.approved_memory_export import (
    APPROVED_MEMORY_EXPORT_FILENAME,
    ApprovedMemoryExportError,
    default_export_path,
    export_approved_memory_candidates,
)
from project_guardian.local_ingestion.memory_candidate_review import (
    approve_candidate,
    edit_candidate,
    reject_candidate,
    resolve_review_paths,
)
from project_guardian.local_ingestion.memory_candidates import review_queue_path
from project_guardian.local_ingestion.transcription_ingest import ingest_transcriptions


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def _stage_candidate(dest: Path, *, filename: str, text: str) -> str:
    source = dest.parent / f"source_{filename}"
    source.mkdir(exist_ok=True)
    _write(source / filename, text)
    ingest_transcriptions(source, dest, apply=True, stage_memory_candidates=True)
    record = json.loads(review_queue_path(dest).read_text(encoding="utf-8").strip().splitlines()[0])
    return str(record["candidate_id"])


def test_exports_approved_candidate(tmp_path):
    dest = tmp_path / "dest"
    candidate_id = _stage_candidate(dest, filename="approved.txt", text="Approved export body.")
    paths = resolve_review_paths(dest_dir=dest)
    approve_candidate(paths, candidate_id)

    report = export_approved_memory_candidates(dest_dir=dest)

    assert report.exported_count == 1
    export_file = default_export_path(dest)
    record = json.loads(export_file.read_text(encoding="utf-8").strip())
    assert record["candidate_id"] == candidate_id
    assert record["approved_text"] == "Approved export body."
    assert record["operator_approved"] is True
    assert record["live_memory_written"] is False
    assert record["review_status"] == "approved"
    assert "approved_export_only_not_live_memory" in record["safety_notes"]


def test_does_not_export_pending_candidate(tmp_path):
    dest = tmp_path / "dest"
    _stage_candidate(dest, filename="pending.txt", text="Still pending.")
    decisions = resolve_review_paths(dest_dir=dest).decisions_path
    decisions.parent.mkdir(parents=True, exist_ok=True)
    decisions.write_text("", encoding="utf-8")

    report = export_approved_memory_candidates(dest_dir=dest)

    assert report.exported_count == 0
    assert report.skipped_pending == 1
    assert default_export_path(dest).read_text(encoding="utf-8") == ""


def test_does_not_export_rejected_candidate(tmp_path):
    dest = tmp_path / "dest"
    candidate_id = _stage_candidate(dest, filename="rejected.txt", text="Reject me.")
    paths = resolve_review_paths(dest_dir=dest)
    reject_candidate(paths, candidate_id)

    report = export_approved_memory_candidates(dest_dir=dest)

    assert report.exported_count == 0
    assert report.skipped_rejected == 1


def test_duplicate_export_run_does_not_duplicate_records(tmp_path):
    dest = tmp_path / "dest"
    candidate_id = _stage_candidate(dest, filename="once.txt", text="Single export.")
    paths = resolve_review_paths(dest_dir=dest)
    approve_candidate(paths, candidate_id)

    export_approved_memory_candidates(dest_dir=dest)
    export_approved_memory_candidates(dest_dir=dest)

    lines = default_export_path(dest).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_source_and_review_files_remain_unchanged(tmp_path):
    dest = tmp_path / "dest"
    candidate_id = _stage_candidate(dest, filename="preserve.txt", text="Keep originals.")
    paths = resolve_review_paths(dest_dir=dest)
    approve_candidate(paths, candidate_id)

    queue_before = review_queue_path(dest).read_bytes()
    decisions_before = paths.decisions_path.read_bytes()
    source_text = Path(
        json.loads(review_queue_path(dest).read_text(encoding="utf-8").strip())["source_text_path"]
    )
    source_before = source_text.read_bytes()

    export_approved_memory_candidates(dest_dir=dest)

    assert review_queue_path(dest).read_bytes() == queue_before
    assert paths.decisions_path.read_bytes() == decisions_before
    assert source_text.read_bytes() == source_before


def test_missing_queue_fails_safely(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()

    with pytest.raises(ApprovedMemoryExportError, match="Review queue not found"):
        export_approved_memory_candidates(dest_dir=dest)


def test_missing_decisions_fails_safely(tmp_path):
    dest = tmp_path / "dest"
    _stage_candidate(dest, filename="only_queue.txt", text="No decisions yet.")
    paths = resolve_review_paths(dest_dir=dest)
    paths.decisions_path.unlink(missing_ok=True)

    with pytest.raises(ApprovedMemoryExportError, match="Review decisions not found"):
        export_approved_memory_candidates(dest_dir=dest)


def test_malformed_queue_fails_safely(tmp_path):
    dest = tmp_path / "dest"
    queue = review_queue_path(dest)
    queue.parent.mkdir(parents=True)
    queue.write_text("{bad json", encoding="utf-8")
    decisions = resolve_review_paths(dest_dir=dest).decisions_path
    decisions.parent.mkdir(parents=True, exist_ok=True)
    decisions.write_text("", encoding="utf-8")

    with pytest.raises(ApprovedMemoryExportError, match="Malformed JSON"):
        export_approved_memory_candidates(dest_dir=dest)


def test_edited_then_approved_exports_edited_text(tmp_path):
    dest = tmp_path / "dest"
    candidate_id = _stage_candidate(dest, filename="edit.txt", text="Original staged text.")
    paths = resolve_review_paths(dest_dir=dest)
    edit_candidate(paths, candidate_id, "Operator cleaned text.", notes="cleaned up")
    approve_candidate(paths, candidate_id, force=True)

    report = export_approved_memory_candidates(dest_dir=dest)

    assert report.exported_count == 1
    record = json.loads(default_export_path(dest).read_text(encoding="utf-8").strip())
    assert record["approved_text"] == "Operator cleaned text."
    source_text = Path(record["source_text_path"])
    assert source_text.read_text(encoding="utf-8").strip() == "Original staged text."
