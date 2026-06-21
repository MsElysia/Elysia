# project_guardian/tests/test_approved_memory_search.py

from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_guardian.local_ingestion.approved_memory_export import export_approved_memory_candidates
from project_guardian.local_ingestion.approved_memory_search import (
    ApprovedMemorySearchError,
    list_recent_memories,
    load_memory_store,
    memory_store_stats,
    search_memory_store,
    show_memory_record,
)
from project_guardian.local_ingestion.approved_memory_store import (
    default_memory_store_path,
    write_approved_memory_store,
)
from project_guardian.local_ingestion.memory_candidate_review import approve_candidate, resolve_review_paths
from project_guardian.local_ingestion.transcription_ingest import ingest_transcriptions


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def _build_store(dest: Path, entries: list[tuple[str, str]]) -> Path:
    for filename, text in entries:
        source = dest.parent / f"source_{filename}"
        source.mkdir(exist_ok=True)
        _write(source / filename, text)
        ingest_transcriptions(source, dest, apply=True, stage_memory_candidates=True)
        candidate_id = json.loads(
            (dest / "memory_candidates" / "review_queue.jsonl")
            .read_text(encoding="utf-8")
            .strip()
            .splitlines()[-1]
        )["candidate_id"]
        paths = resolve_review_paths(dest_dir=dest)
        if not paths.decisions_path.exists():
            paths.decisions_path.parent.mkdir(parents=True, exist_ok=True)
            paths.decisions_path.write_text("", encoding="utf-8")
        approve_candidate(paths, candidate_id)
    export_approved_memory_candidates(dest_dir=dest)
    write_approved_memory_store(dest_dir=dest, apply=True)
    return default_memory_store_path(dest)


def test_search_finds_matching_memories(tmp_path):
    dest = tmp_path / "dest"
    store_path = _build_store(
        dest,
        [
            ("drywall.txt", "Customer asked for a drywall quote for the kitchen."),
            ("paint.txt", "Need paint colors for the living room."),
        ],
    )
    records = load_memory_store(store_path)

    report = search_memory_store(records, "drywall quote")

    assert report.count == 1
    assert report.results[0].memory_id
    assert "drywall" in report.results[0].snippet.lower()


def test_search_is_case_insensitive(tmp_path):
    dest = tmp_path / "dest"
    store_path = _build_store(dest, [("memo.txt", "Drywall Quote details here.")])
    records = load_memory_store(store_path)

    report = search_memory_store(records, "DRYWALL quote")

    assert report.count == 1


def test_search_ranks_stronger_matches_higher(tmp_path):
    dest = tmp_path / "dest"
    store_path = _build_store(
        dest,
        [
            ("weak.txt", "drywall only"),
            ("strong.txt", "drywall quote for kitchen drywall quote"),
        ],
    )
    records = load_memory_store(store_path)

    report = search_memory_store(records, "drywall quote")

    assert report.count == 2
    assert report.results[0].score >= report.results[1].score


def test_search_with_no_matches_returns_empty_safely(tmp_path):
    dest = tmp_path / "dest"
    store_path = _build_store(dest, [("note.txt", "Unrelated content.")])
    records = load_memory_store(store_path)

    report = search_memory_store(records, "nonexistent phrase")

    assert report.count == 0
    assert report.results == []


def test_show_returns_one_memory_by_id(tmp_path):
    dest = tmp_path / "dest"
    store_path = _build_store(dest, [("showme.txt", "Full memory body text.")])
    records = load_memory_store(store_path)
    memory_id = records[0]["memory_id"]

    record = show_memory_record(records, memory_id)

    assert record["memory_id"] == memory_id
    assert record["text"] == "Full memory body text."


def test_show_missing_memory_id_fails_clearly(tmp_path):
    dest = tmp_path / "dest"
    store_path = _build_store(dest, [("one.txt", "Only one.")])
    records = load_memory_store(store_path)

    with pytest.raises(ApprovedMemorySearchError, match="Memory not found"):
        show_memory_record(records, "missing-memory-id")


def test_list_recent_respects_limit(tmp_path):
    dest = tmp_path / "dest"
    store_path = _build_store(
        dest,
        [
            ("a.txt", "First memory."),
            ("b.txt", "Second memory."),
            ("c.txt", "Third memory."),
        ],
    )
    records = load_memory_store(store_path)

    report = list_recent_memories(records, limit=2)

    assert report.count == 2
    assert len(report.results) == 2


def test_stats_returns_basic_count(tmp_path):
    dest = tmp_path / "dest"
    store_path = _build_store(dest, [("stats.txt", "Stats memory.")])
    records = load_memory_store(store_path)

    report = memory_store_stats(records)

    assert report.total_records == 1
    assert report.active_records == 1
    assert report.memory_types.get("personal_note") == 1


def test_search_does_not_modify_memory_store(tmp_path):
    dest = tmp_path / "dest"
    store_path = _build_store(dest, [("immutable.txt", "Drywall quote unchanged.")])
    before = store_path.read_bytes()
    records = load_memory_store(store_path)

    search_memory_store(records, "drywall")
    list_recent_memories(records, limit=5)
    memory_store_stats(records)
    show_memory_record(records, records[0]["memory_id"])

    assert store_path.read_bytes() == before


def test_missing_memory_store_fails_safely(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    missing = default_memory_store_path(dest)

    with pytest.raises(ApprovedMemorySearchError, match="Memory store not found"):
        load_memory_store(missing)


def test_malformed_jsonl_fails_safely(tmp_path):
    dest = tmp_path / "dest"
    store_path = default_memory_store_path(dest)
    store_path.parent.mkdir(parents=True)
    store_path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(ApprovedMemorySearchError, match="Malformed JSON"):
        load_memory_store(store_path)


def test_no_live_memory_or_embedding_calls(tmp_path, monkeypatch):
    dest = tmp_path / "dest"
    store_path = _build_store(dest, [("safe.txt", "Drywall quote safe search.")])
    records = load_memory_store(store_path)

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

    search_memory_store(records, "drywall")
