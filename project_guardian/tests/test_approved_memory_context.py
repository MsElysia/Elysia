# project_guardian/tests/test_approved_memory_context.py

from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_guardian.local_ingestion.approved_memory_context import (
    CONTEXT_BUNDLE_JSON,
    CONTEXT_BUNDLE_MD,
    SAFETY_STATEMENT,
    ApprovedMemoryContextError,
    build_approved_memory_context,
    default_context_output_dir,
)
from project_guardian.local_ingestion.approved_memory_export import export_approved_memory_candidates
from project_guardian.local_ingestion.approved_memory_store import (
    default_memory_store_path,
    write_approved_memory_store,
)
from project_guardian.local_ingestion.memory_candidate_review import approve_candidate, resolve_review_paths
from project_guardian.local_ingestion.transcription_ingest import ingest_transcriptions


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def _build_store(dest: Path, entries: list[tuple[str, str]]) -> None:
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


def test_context_bundle_created_for_matching_query(tmp_path):
    dest = tmp_path / "dest"
    _build_store(dest, [("drywall.txt", "Customer asked for a drywall quote for the kitchen.")])

    report = build_approved_memory_context(dest_dir=dest, query="drywall quote", limit=5)

    assert report.result_count == 1
    assert Path(report.json_path).is_file()
    assert Path(report.markdown_path).is_file()
    bundle = json.loads(Path(report.json_path).read_text(encoding="utf-8"))
    assert bundle["bundle_type"] == "approved_memory_context"


def test_json_bundle_safety_flags(tmp_path):
    dest = tmp_path / "dest"
    _build_store(dest, [("note.txt", "Drywall quote details.")])

    report = build_approved_memory_context(dest_dir=dest, query="drywall")

    bundle = report.bundle
    assert bundle["model_called"] is False
    assert bundle["embeddings_used"] is False
    assert bundle["live_memory_written"] is False


def test_markdown_bundle_includes_safety_statement(tmp_path):
    dest = tmp_path / "dest"
    _build_store(dest, [("note.txt", "Drywall quote details.")])

    report = build_approved_memory_context(dest_dir=dest, query="drywall")
    md = Path(report.markdown_path).read_text(encoding="utf-8")

    assert SAFETY_STATEMENT in md
    assert "Suggested Prompt" in md


def test_only_approved_store_records_are_used(tmp_path):
    dest = tmp_path / "dest"
    store_path = default_memory_store_path(dest)
    store_path.parent.mkdir(parents=True)
    store_path.write_text(
        json.dumps(
            {
                "memory_id": "bad1",
                "candidate_id": "c1",
                "source_type": "phone_transcription",
                "text": "Drywall quote hidden",
                "text_sha256": "x",
                "memory_status": "active",
                "operator_approved": False,
                "live_runtime_memory_written": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_approved_memory_context(dest_dir=dest, query="drywall")

    assert report.result_count == 0
    assert report.bundle["results"] == []


def test_limit_is_respected(tmp_path):
    dest = tmp_path / "dest"
    _build_store(
        dest,
        [
            ("a.txt", "drywall quote alpha"),
            ("b.txt", "drywall quote beta"),
            ("c.txt", "drywall quote gamma"),
        ],
    )

    report = build_approved_memory_context(dest_dir=dest, query="drywall quote", limit=2)

    assert report.result_count == 2


def test_max_chars_is_respected(tmp_path):
    dest = tmp_path / "dest"
    _build_store(dest, [("big.txt", "drywall quote " + ("x" * 5000))])

    report = build_approved_memory_context(
        dest_dir=dest,
        query="drywall",
        max_chars=200,
        include_full_text=True,
    )

    total = sum(len(str(item.get("text") or item.get("snippet") or "")) for item in report.bundle["results"])
    assert total <= 200


def test_no_match_creates_empty_bundle(tmp_path):
    dest = tmp_path / "dest"
    _build_store(dest, [("note.txt", "Unrelated gardening tips.")])
    out_dir = default_context_output_dir(dest)

    report = build_approved_memory_context(dest_dir=dest, query="drywall quote", output_dir=out_dir)

    assert report.result_count == 0
    bundle = json.loads((out_dir / CONTEXT_BUNDLE_JSON).read_text(encoding="utf-8"))
    md = (out_dir / CONTEXT_BUNDLE_MD).read_text(encoding="utf-8")
    assert bundle["results"] == []
    assert "No matching approved memories found" in md


def test_missing_memory_store_fails_safely(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()

    with pytest.raises(ApprovedMemoryContextError, match="Memory store not found"):
        build_approved_memory_context(dest_dir=dest, query="drywall")


def test_malformed_jsonl_fails_safely(tmp_path):
    dest = tmp_path / "dest"
    store_path = default_memory_store_path(dest)
    store_path.parent.mkdir(parents=True)
    store_path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(ApprovedMemoryContextError, match="Malformed JSON"):
        build_approved_memory_context(dest_dir=dest, query="drywall")


def test_memory_store_is_not_modified(tmp_path):
    dest = tmp_path / "dest"
    _build_store(dest, [("immutable.txt", "Drywall quote unchanged.")])
    store_path = default_memory_store_path(dest)
    before = store_path.read_bytes()

    build_approved_memory_context(dest_dir=dest, query="drywall")

    assert store_path.read_bytes() == before


def test_no_model_or_embedding_calls(tmp_path, monkeypatch):
    dest = tmp_path / "dest"
    _build_store(dest, [("safe.txt", "Drywall quote safe bundle.")])

    def _boom(*_args, **_kwargs):
        raise AssertionError("model, vector DB, or embeddings must not be called")

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

    build_approved_memory_context(dest_dir=dest, query="drywall")
