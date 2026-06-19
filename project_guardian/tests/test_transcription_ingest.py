# project_guardian/tests/test_transcription_ingest.py

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from project_guardian.local_ingestion.transcription_ingest import (
    MANIFEST_FILENAME,
    ingest_transcriptions,
    normalize_srt,
    normalize_vtt,
)


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def test_dry_run_finds_files_but_writes_nothing(tmp_path):
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()
    _write(source / "note.txt", "Hello from phone transcription.")
    _write(source / "photo.jpg", "fake image bytes")

    before = (source / "note.txt").read_text(encoding="utf-8")
    report = ingest_transcriptions(source, dest, apply=False)

    assert report.apply is False
    assert report.ingested == 1
    assert report.skipped == 1
    assert not dest.exists()
    assert (source / "note.txt").read_text(encoding="utf-8") == before
    assert report.results[0].status == "dry_run"
    assert report.results[1].status == "skipped_unsupported"


def test_apply_writes_text_metadata_and_manifest(tmp_path):
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()
    _write(source / "meeting.md", "# Meeting\n\nDiscuss roadmap.")

    source_bytes = (source / "meeting.md").read_bytes()
    report = ingest_transcriptions(source, dest, apply=True)

    assert report.ingested == 1
    assert (dest / "text").is_dir()
    assert (dest / "metadata").is_dir()
    text_files = list((dest / "text").glob("*.txt"))
    meta_files = list((dest / "metadata").glob("*.meta.json"))
    assert len(text_files) == 1
    assert len(meta_files) == 1
    assert text_files[0].read_text(encoding="utf-8").startswith("# Meeting")
    metadata = json.loads(meta_files[0].read_text(encoding="utf-8"))
    assert metadata["original_filename"] == "meeting.md"
    assert metadata["status"] == "ingested"
    assert metadata["sha256"]
    assert (dest / MANIFEST_FILENAME).is_file()
    manifest_lines = (dest / MANIFEST_FILENAME).read_text(encoding="utf-8").strip().splitlines()
    assert len(manifest_lines) == 1
    assert json.loads(manifest_lines[0])["status"] == "ingested"
    assert (source / "meeting.md").read_bytes() == source_bytes


def test_source_files_remain_unchanged_after_apply(tmp_path):
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()
    original = "Original untouched content."
    path = source / "voice.txt"
    _write(path, original)
    before_bytes = path.read_bytes()

    ingest_transcriptions(source, dest, apply=True)

    assert path.read_bytes() == before_bytes


def test_unsupported_and_binary_like_files_are_skipped(tmp_path):
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()
    _write(source / "notes.txt", "valid")
    (source / "archive.zip").write_bytes(b"PK\x03\x04binary")
    (source / "bad.txt").write_bytes(b"hello\x00world")

    report = ingest_transcriptions(source, dest, apply=True)

    assert report.ingested == 1
    assert report.skipped == 2
    statuses = {item.status for item in report.results}
    assert "skipped_unsupported" in statuses
    assert "skipped_binary" in statuses


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlinks unavailable")
def test_symlinks_are_skipped(tmp_path):
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()
    real = source / "real.txt"
    _write(real, "real content")
    link = source / "linked.txt"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported in this environment")

    report = ingest_transcriptions(source, dest, apply=True)

    assert report.ingested == 1
    assert report.skipped == 1
    assert any(item.status == "skipped_symlink" for item in report.results)


def test_oversized_files_are_skipped(tmp_path):
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()
    _write(source / "small.txt", "ok")
    huge = source / "huge.txt"
    huge.write_bytes(b"x" * (2 * 1024 * 1024))

    report = ingest_transcriptions(source, dest, apply=True, max_file_mb=1.0)

    assert report.ingested == 1
    assert report.skipped == 1
    assert any(item.status == "skipped_oversized" for item in report.results)


def test_duplicate_content_is_not_overwritten(tmp_path):
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()
    _write(source / "a.txt", "Same words.")
    _write(source / "b.txt", "Same words.")

    first = ingest_transcriptions(source, dest, apply=True)
    second = ingest_transcriptions(source, dest, apply=True)

    assert first.ingested == 1
    assert first.duplicates == 1
    assert second.duplicates == 2
    assert second.ingested == 0
    text_files = list((dest / "text").glob("*.txt"))
    assert len(text_files) == 1
    manifest_lines = (dest / MANIFEST_FILENAME).read_text(encoding="utf-8").strip().splitlines()
    assert len(manifest_lines) == 1


def test_vtt_and_srt_normalization_helpers():
    vtt = "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nHello there.\n"
    srt = "1\n00:00:01,000 --> 00:00:04,000\nHello there.\n"
    assert normalize_vtt(vtt) == "Hello there."
    assert normalize_srt(srt) == "Hello there."


def test_non_recursive_scan_ignores_subfolders(tmp_path):
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()
    nested = source / "nested"
    nested.mkdir()
    _write(source / "top.txt", "top")
    _write(nested / "hidden.txt", "hidden")

    report = ingest_transcriptions(source, dest, apply=False, recursive=False)

    assert report.scanned == 1
    assert report.ingested == 1


def test_recursive_scan_includes_subfolders(tmp_path):
    source = tmp_path / "source"
    dest = tmp_path / "dest"
    source.mkdir()
    nested = source / "nested"
    nested.mkdir()
    _write(source / "top.txt", "top")
    _write(nested / "hidden.txt", "hidden")

    report = ingest_transcriptions(source, dest, apply=False, recursive=True)

    assert report.scanned == 2
    assert report.ingested == 2
