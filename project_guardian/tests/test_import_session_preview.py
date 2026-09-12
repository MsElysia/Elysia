# project_guardian/tests/test_import_session_preview.py

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from project_guardian.local_ingestion.import_session_preview import (
    PREVIEW_JSON,
    PREVIEW_MD,
    ImportSessionPreviewError,
    preview_memory_import_session,
)


def _write(path: Path, content: str | bytes) -> None:
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8", newline="\n")
    else:
        path.write_bytes(content)


def test_requires_at_least_one_explicit_input(tmp_path):
    dest = tmp_path / "dest"
    with pytest.raises(ImportSessionPreviewError, match="At least one explicit"):
        preview_memory_import_session(dest_dir=dest, input_paths=[])


def test_preview_writes_json_and_markdown(tmp_path):
    dest = tmp_path / "dest"
    note = tmp_path / "note.txt"
    _write(note, "Drywall quote follow-up.")

    report = preview_memory_import_session(dest_dir=dest, input_paths=[note])

    json_path = Path(report.json_path)
    md_path = Path(report.markdown_path)
    assert json_path.is_file()
    assert md_path.is_file()
    assert PREVIEW_JSON in str(json_path)
    assert PREVIEW_MD in str(md_path)
    assert "import_sessions" in str(json_path)


def test_txt_and_md_classified_supported_now(tmp_path):
    dest = tmp_path / "dest"
    txt = tmp_path / "a.txt"
    md = tmp_path / "b.md"
    _write(txt, "text")
    _write(md, "# heading")

    report = preview_memory_import_session(dest_dir=dest, input_paths=[txt, md])
    categories = {entry["name"]: entry["category"] for entry in report.preview["file_entries"]}

    assert categories["a.txt"] == "supported_now"
    assert categories["b.md"] == "supported_now"


def test_json_and_csv_classified_supported_later(tmp_path):
    dest = tmp_path / "dest"
    js = tmp_path / "data.json"
    csv = tmp_path / "data.csv"
    _write(js, '{"a": 1}')
    _write(csv, "a,b\n1,2")

    report = preview_memory_import_session(dest_dir=dest, input_paths=[js, csv])
    categories = {entry["name"]: entry["category"] for entry in report.preview["file_entries"]}

    assert categories["data.json"] == "supported_later"
    assert categories["data.csv"] == "supported_later"


def test_binary_unsupported_without_text_read(tmp_path):
    dest = tmp_path / "dest"
    binary = tmp_path / "image.bin"
    _write(binary, b"\x00\x01\x02\xff" * 100)

    with patch(
        "project_guardian.local_ingestion.import_session_preview._peek_binary",
        wraps=lambda path: True,
    ) as peek:
        report = preview_memory_import_session(dest_dir=dest, input_paths=[binary])

    peek.assert_called_once()
    entry = report.preview["file_entries"][0]
    assert entry["category"] == "unsupported"


def test_symlink_skipped_when_supported(tmp_path):
    dest = tmp_path / "dest"
    real = tmp_path / "real.txt"
    _write(real, "hello")
    link = tmp_path / "link.txt"
    try:
        os.symlink(real, link)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not supported in this environment")

    report = preview_memory_import_session(dest_dir=dest, input_paths=[link])
    entry = report.preview["file_entries"][0]
    assert entry["category"] == "skipped"
    assert "Symlink" in entry["reason"]


def test_recursive_scan_requires_explicit_flag(tmp_path):
    dest = tmp_path / "dest"
    folder = tmp_path / "folder"
    nested = folder / "nested"
    nested.mkdir(parents=True)
    _write(nested / "deep.txt", "nested text")

    non_recursive = preview_memory_import_session(dest_dir=dest, input_paths=[folder], recursive=False)
    assert non_recursive.preview["summary"]["files_seen"] == 0

    recursive = preview_memory_import_session(dest_dir=dest, input_paths=[folder], recursive=True)
    assert recursive.preview["summary"]["files_seen"] == 1
    assert recursive.preview["file_entries"][0]["category"] == "supported_now"


def test_max_file_size_skip(tmp_path):
    dest = tmp_path / "dest"
    big = tmp_path / "big.txt"
    _write(big, "x" * 200)

    report = preview_memory_import_session(
        dest_dir=dest,
        input_paths=[big],
        max_file_mb=0.00001,
    )
    entry = report.preview["file_entries"][0]
    assert entry["category"] == "skipped"
    assert "exceeds max size" in entry["reason"]


def test_source_files_not_modified(tmp_path):
    dest = tmp_path / "dest"
    note = tmp_path / "note.txt"
    _write(note, "unchanged")
    before = note.read_bytes()

    preview_memory_import_session(dest_dir=dest, input_paths=[note])

    assert note.read_bytes() == before


def test_no_import_memory_model_vector_calls(tmp_path):
    dest = tmp_path / "dest"
    note = tmp_path / "note.txt"
    _write(note, "safe preview")

    with patch("project_guardian.local_ingestion.transcription_ingest.ingest_transcriptions") as ingest:
        with patch("project_guardian.memory_vector.VectorMemory") as vector:
            report = preview_memory_import_session(dest_dir=dest, input_paths=[note])

    ingest.assert_not_called()
    vector.assert_not_called()
    preview = report.preview
    assert preview["model_called"] is False
    assert preview["embeddings_used"] is False
    assert preview["live_memory_written"] is False
    assert preview["import_applied"] is False


def test_json_safety_flags(tmp_path):
    dest = tmp_path / "dest"
    note = tmp_path / "note.txt"
    _write(note, "hello")

    report = preview_memory_import_session(dest_dir=dest, input_paths=[note])
    bundle = json.loads(Path(report.json_path).read_text(encoding="utf-8"))

    assert bundle["model_called"] is False
    assert bundle["embeddings_used"] is False
    assert bundle["live_memory_written"] is False
    assert bundle["import_applied"] is False


def test_missing_input_fails_safely(tmp_path):
    dest = tmp_path / "dest"
    missing = tmp_path / "missing.txt"
    with pytest.raises(ImportSessionPreviewError, match="not found"):
        preview_memory_import_session(dest_dir=dest, input_paths=[missing])


def test_unavailable_path_fails_safely(tmp_path, monkeypatch):
    dest = tmp_path / "dest"
    bad = tmp_path / "bad.txt"
    _write(bad, "x")

    def _broken_resolve(self, strict=False):
        raise OSError("broken path")

    monkeypatch.setattr(Path, "resolve", _broken_resolve)
    with pytest.raises(ImportSessionPreviewError, match="unavailable"):
        preview_memory_import_session(dest_dir=dest, input_paths=[bad])
