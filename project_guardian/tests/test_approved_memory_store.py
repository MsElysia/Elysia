# project_guardian/tests/test_approved_memory_store.py

from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_guardian.local_ingestion.approved_memory_export import (
    default_export_path,
    export_approved_memory_candidates,
)
from project_guardian.local_ingestion.approved_memory_store import (
    APPROVED_MEMORY_STORE_FILENAME,
    ApprovedMemoryStoreError,
    default_memory_store_path,
    write_approved_memory_store,
)
from project_guardian.local_ingestion.memory_candidate_review import (
    approve_candidate,
    resolve_review_paths,
)
from project_guardian.local_ingestion.transcription_ingest import ingest_transcriptions


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def _stage_and_approve(dest: Path, *, filename: str, text: str) -> None:
    source = dest.parent / f"source_{filename}"
    source.mkdir(exist_ok=True)
    _write(source / filename, text)
    ingest_transcriptions(source, dest, apply=True, stage_memory_candidates=True)
    candidate_id = json.loads(
        (dest / "memory_candidates" / "review_queue.jsonl")
        .read_text(encoding="utf-8")
        .strip()
        .splitlines()[0]
    )["candidate_id"]
    paths = resolve_review_paths(dest_dir=dest)
    paths.decisions_path.parent.mkdir(parents=True, exist_ok=True)
    if not paths.decisions_path.exists():
        paths.decisions_path.write_text("", encoding="utf-8")
    approve_candidate(paths, candidate_id)


def test_dry_run_writes_nothing(tmp_path):
    dest = tmp_path / "dest"
    _stage_and_approve(dest, filename="dry.txt", text="Dry run only.")
    export_approved_memory_candidates(dest_dir=dest)

    report = write_approved_memory_store(dest_dir=dest, apply=False)

    assert report.apply is False
    assert report.stored_count == 1
    assert not default_memory_store_path(dest).exists()


def test_apply_writes_local_memory_store(tmp_path):
    dest = tmp_path / "dest"
    _stage_and_approve(dest, filename="store.txt", text="Store this approved memory.")
    export_approved_memory_candidates(dest_dir=dest)

    report = write_approved_memory_store(dest_dir=dest, apply=True)

    store_path = default_memory_store_path(dest)
    assert store_path.is_file()
    assert report.stored_count == 1
    record = json.loads(store_path.read_text(encoding="utf-8").strip())
    assert record["text"] == "Store this approved memory."
    assert record["memory_status"] == "active"
    assert record["operator_approved"] is True
    assert record["live_vector_written"] is False
    assert record["live_runtime_memory_written"] is False
    assert record["reversible"] is True
    assert "local_store_only_not_runtime_memory" in record["safety_notes"]
    assert record["created_by"] == "local_approved_memory_store_writer"


def test_non_approved_export_records_are_skipped(tmp_path):
    dest = tmp_path / "dest"
    export_path = default_export_path(dest)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "candidate_id": "pending1",
                        "source_type": "phone_transcription",
                        "approved_text": "pending",
                        "review_status": "pending",
                        "operator_approved": False,
                        "live_memory_written": False,
                    }
                ),
                json.dumps(
                    {
                        "candidate_id": "reject1",
                        "source_type": "phone_transcription",
                        "approved_text": "rejected",
                        "review_status": "rejected",
                        "operator_approved": True,
                        "live_memory_written": False,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = write_approved_memory_store(
        dest_dir=dest,
        approved_export_path=export_path,
        apply=True,
    )

    assert report.stored_count == 0
    assert report.skipped_invalid == 2
    assert default_memory_store_path(dest).read_text(encoding="utf-8") == ""


def test_operator_approved_and_live_memory_written_required(tmp_path):
    dest = tmp_path / "dest"
    export_path = default_export_path(dest)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(
        json.dumps(
            {
                "candidate_id": "bad1",
                "source_type": "phone_transcription",
                "approved_text": "nope",
                "review_status": "approved",
                "operator_approved": False,
                "live_memory_written": False,
            }
        )
        + "\n"
        + json.dumps(
            {
                "candidate_id": "bad2",
                "source_type": "phone_transcription",
                "approved_text": "nope",
                "review_status": "approved",
                "operator_approved": True,
                "live_memory_written": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = write_approved_memory_store(dest_dir=dest, apply=True)

    assert report.stored_count == 0
    assert report.skipped_invalid == 2


def test_duplicate_apply_does_not_duplicate_records(tmp_path):
    dest = tmp_path / "dest"
    _stage_and_approve(dest, filename="once.txt", text="Single store record.")
    export_approved_memory_candidates(dest_dir=dest)

    write_approved_memory_store(dest_dir=dest, apply=True)
    write_approved_memory_store(dest_dir=dest, apply=True)

    lines = default_memory_store_path(dest).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_approved_export_file_remains_unchanged(tmp_path):
    dest = tmp_path / "dest"
    _stage_and_approve(dest, filename="preserve.txt", text="Keep export unchanged.")
    export_approved_memory_candidates(dest_dir=dest)
    export_path = default_export_path(dest)
    before = export_path.read_bytes()

    write_approved_memory_store(dest_dir=dest, apply=True)

    assert export_path.read_bytes() == before


def test_missing_export_fails_safely(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()

    with pytest.raises(ApprovedMemoryStoreError, match="Approved export not found"):
        write_approved_memory_store(dest_dir=dest, apply=False)


def test_malformed_export_fails_safely(tmp_path):
    dest = tmp_path / "dest"
    export_path = default_export_path(dest)
    export_path.parent.mkdir(parents=True)
    export_path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(ApprovedMemoryStoreError, match="Malformed JSON"):
        write_approved_memory_store(dest_dir=dest, apply=False)


def test_no_live_memory_or_embedding_calls(tmp_path, monkeypatch):
    dest = tmp_path / "dest"
    _stage_and_approve(dest, filename="safe.txt", text="No runtime calls.")
    export_approved_memory_candidates(dest_dir=dest)

    def _boom(*_args, **_kwargs):
        raise AssertionError("live memory or embeddings must not be called")

    monkeypatch.setattr("project_guardian.memory.MemoryCore.remember", _boom, raising=False)
    monkeypatch.setattr(
        "project_guardian.memory_vector.EnhancedMemoryCore.remember",
        _boom,
        raising=False,
    )
    monkeypatch.setattr(
        "project_guardian.context_pipeline.embedding_backend.embed_text",
        _boom,
        raising=False,
    )

    write_approved_memory_store(dest_dir=dest, apply=True)
