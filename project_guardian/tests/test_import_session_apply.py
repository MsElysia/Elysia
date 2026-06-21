# project_guardian/tests/test_import_session_apply.py

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from project_guardian.local_ingestion.import_session_apply import (
    APPLY_REPORT_JSON,
    APPLY_REPORT_MD,
    ImportSessionApplyError,
    apply_memory_import_session,
)
from project_guardian.local_ingestion.import_session_preview import preview_memory_import_session
from project_guardian.local_ingestion.memory_candidates import REVIEW_QUEUE_FILENAME
from project_guardian.local_ingestion.transcription_ingest import MANIFEST_FILENAME


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def _preview_session(dest: Path, inputs: list[Path], **kwargs):
    return preview_memory_import_session(dest_dir=dest, input_paths=inputs, **kwargs)


def test_requires_explicit_session_json(tmp_path):
    missing = tmp_path / "missing.json"
    with pytest.raises(ImportSessionApplyError, match="not found"):
        apply_memory_import_session(session_json=missing)


def test_dry_run_writes_no_ingestion_or_candidates(tmp_path):
    dest = tmp_path / "dest"
    note = tmp_path / "note.txt"
    _write(note, "Drywall quote follow-up.")
    preview = _preview_session(dest, [note])

    report = apply_memory_import_session(session_json=Path(preview.json_path), apply=False)

    assert not (dest / "text").exists()
    assert not (dest / "metadata").exists()
    assert not (dest / MANIFEST_FILENAME).exists()
    assert not (dest / "memory_candidates" / REVIEW_QUEUE_FILENAME).exists()
    assert report.report["dry_run"] is True
    assert any(f["action"] == "dry_run_would_import" for f in report.report["files"])


def test_apply_imports_only_supported_now(tmp_path):
    dest = tmp_path / "dest"
    good = tmp_path / "good.txt"
    csv = tmp_path / "data.csv"
    _write(good, "Supported note.")
    _write(csv, "a,b")
    preview = _preview_session(dest, [good, csv])

    report = apply_memory_import_session(session_json=Path(preview.json_path), apply=True)

    actions = {f["name"]: f["action"] for f in report.report["files"]}
    assert actions["good.txt"] == "imported"
    assert actions["data.csv"] == "skipped_preview_category"
    assert report.report["imported_count"] == 1


def test_apply_skips_non_eligible_categories(tmp_path):
    dest = tmp_path / "dest"
    txt = tmp_path / "note.txt"
    binf = tmp_path / "blob.bin"
    _write(txt, "hello")
    binf.write_bytes(b"\x00\x01\xff" * 20)
    preview = _preview_session(dest, [txt, binf])

    report = apply_memory_import_session(session_json=Path(preview.json_path), apply=True)

    by_name = {f["name"]: f for f in report.report["files"]}
    assert by_name["note.txt"]["action"] == "imported"
    assert by_name["blob.bin"]["action"] == "skipped_preview_category"


def test_apply_creates_text_metadata_manifest_and_candidates(tmp_path):
    dest = tmp_path / "dest"
    note = tmp_path / "note.txt"
    _write(note, "Customer drywall quote.")
    preview = _preview_session(dest, [note])

    apply_memory_import_session(session_json=Path(preview.json_path), apply=True)

    assert list((dest / "text").glob("*.txt"))
    assert list((dest / "metadata").glob("*.meta.json"))
    assert (dest / MANIFEST_FILENAME).is_file()
    queue = dest / "memory_candidates" / REVIEW_QUEUE_FILENAME
    assert queue.is_file()
    assert "drywall" in queue.read_text(encoding="utf-8").lower()


def test_source_files_unchanged(tmp_path):
    dest = tmp_path / "dest"
    note = tmp_path / "note.txt"
    _write(note, "unchanged content")
    before = note.read_bytes()
    preview = _preview_session(dest, [note])

    apply_memory_import_session(session_json=Path(preview.json_path), apply=True)

    assert note.read_bytes() == before


def test_apply_does_not_rescan_unlisted_files(tmp_path):
    dest = tmp_path / "dest"
    folder = tmp_path / "folder"
    folder.mkdir()
    listed = folder / "listed.txt"
    unlisted = folder / "unlisted.txt"
    _write(listed, "listed only")
    _write(unlisted, "should not import")
    preview = _preview_session(dest, [listed])

    apply_memory_import_session(session_json=Path(preview.json_path), apply=True)

    manifest = (dest / MANIFEST_FILENAME).read_text(encoding="utf-8")
    assert "listed.txt" in manifest or "listed only" in manifest
    assert "unlisted" not in manifest


def test_changed_source_size_skipped(tmp_path):
    dest = tmp_path / "dest"
    note = tmp_path / "note.txt"
    _write(note, "original size")
    preview = _preview_session(dest, [note])
    _write(note, "much longer changed content now")

    report = apply_memory_import_session(session_json=Path(preview.json_path), apply=True)

    entry = next(f for f in report.report["files"] if f["name"] == "note.txt")
    assert entry["action"] == "skipped_size_changed"
    assert not (dest / MANIFEST_FILENAME).exists()


def test_apply_report_json_and_markdown_written(tmp_path):
    dest = tmp_path / "dest"
    note = tmp_path / "note.txt"
    _write(note, "report me")
    preview = _preview_session(dest, [note])

    report = apply_memory_import_session(session_json=Path(preview.json_path), apply=False)

    json_path = Path(report.json_path)
    md_path = Path(report.markdown_path)
    assert json_path.name == APPLY_REPORT_JSON
    assert md_path.name == APPLY_REPORT_MD
    assert json_path.is_file()
    assert md_path.is_file()


def test_apply_report_safety_flags(tmp_path):
    dest = tmp_path / "dest"
    note = tmp_path / "note.txt"
    _write(note, "flags")
    preview = _preview_session(dest, [note])

    report = apply_memory_import_session(session_json=Path(preview.json_path), apply=False)

    assert report.report["model_called"] is False
    assert report.report["embeddings_used"] is False
    assert report.report["live_memory_written"] is False


def test_duplicate_apply_does_not_duplicate_candidates(tmp_path):
    dest = tmp_path / "dest"
    note = tmp_path / "note.txt"
    _write(note, "duplicate check")
    preview = _preview_session(dest, [note])

    first = apply_memory_import_session(session_json=Path(preview.json_path), apply=True)
    second = apply_memory_import_session(session_json=Path(preview.json_path), apply=True)

    assert first.report["candidate_count"] == 1
    assert second.report["candidate_count"] == 0
    queue_lines = [
        ln
        for ln in (dest / "memory_candidates" / REVIEW_QUEUE_FILENAME)
        .read_text(encoding="utf-8")
        .splitlines()
        if ln.strip()
    ]
    assert len(queue_lines) == 1
    assert second.report["files"][0]["action"] == "duplicate"


def test_no_live_memory_vector_model_calls(tmp_path):
    dest = tmp_path / "dest"
    note = tmp_path / "note.txt"
    _write(note, "safe apply")
    preview = _preview_session(dest, [note])

    with patch("project_guardian.memory_vector.VectorMemory") as vector:
        report = apply_memory_import_session(session_json=Path(preview.json_path), apply=True)

    vector.assert_not_called()
    assert report.report["model_called"] is False
    assert report.report["embeddings_used"] is False


def test_malformed_session_json_fails_safely(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ImportSessionApplyError, match="Malformed"):
        apply_memory_import_session(session_json=bad)
