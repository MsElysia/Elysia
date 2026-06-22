# project_guardian/tests/test_email_export_ingest.py

from __future__ import annotations

import json
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from unittest.mock import patch

import pytest

from project_guardian.local_ingestion.email_export_ingest import (
    APPLY_REPORT_JSON,
    PREVIEW_JSON,
    PREVIEW_MD,
    EmailExportIngestError,
    apply_email_export,
    preview_email_export,
)
from project_guardian.local_ingestion.memory_candidates import REVIEW_QUEUE_FILENAME


def _write_plain_eml(
    path: Path,
    *,
    subject: str = "Drywall quote follow-up",
    body: str = "Please send the drywall quote for the kitchen remodel.",
) -> None:
    lines = [
        "From: sender@example.com",
        "To: user@example.com",
        f"Subject: {subject}",
        "Date: Mon, 1 Jan 2026 12:00:00 +0000",
        "Message-ID: <test-plain@example.com>",
        "Content-Type: text/plain; charset=utf-8",
        "",
        body,
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_html_eml(path: Path) -> None:
    msg = MIMEMultipart("alternative")
    msg["From"] = "html@example.com"
    msg["To"] = "user@example.com"
    msg["Subject"] = "HTML only drywall note"
    msg["Date"] = "Mon, 1 Jan 2026 12:00:00 +0000"
    msg.attach(MIMEText("<p>Please send the <b>drywall</b> quote.</p>", "html", "utf-8"))
    path.write_bytes(msg.as_bytes())


def _write_attachment_eml(path: Path) -> None:
    msg = MIMEMultipart("mixed")
    msg["From"] = "attach@example.com"
    msg["To"] = "user@example.com"
    msg["Subject"] = "Quote with attachment"
    msg.attach(MIMEText("Body text about drywall quote.", "plain", "utf-8"))
    attachment = MIMEApplication(b"fake pdf bytes", _subtype="pdf")
    attachment.add_header("Content-Disposition", "attachment", filename="quote.pdf")
    msg.attach(attachment)
    path.write_bytes(msg.as_bytes())


def test_preview_requires_explicit_input_and_dest(tmp_path):
    eml = tmp_path / "mail.eml"
    _write_plain_eml(eml)
    dest = tmp_path / "dest"
    report = preview_email_export(dest_dir=dest, input_paths=[eml])
    assert report.preview["dest_dir"]


def test_preview_requires_at_least_one_input(tmp_path):
    with pytest.raises(EmailExportIngestError, match="At least one explicit"):
        preview_email_export(dest_dir=tmp_path / "dest", input_paths=[])


def test_preview_writes_json_and_markdown(tmp_path):
    eml = tmp_path / "mail.eml"
    _write_plain_eml(eml)
    dest = tmp_path / "dest"
    report = preview_email_export(dest_dir=dest, input_paths=[eml])
    assert Path(report.json_path).name == PREVIEW_JSON
    assert Path(report.markdown_path).name == PREVIEW_MD
    assert Path(report.json_path).is_file()
    assert Path(report.markdown_path).is_file()


def test_eml_classified_supported_now(tmp_path):
    eml = tmp_path / "mail.eml"
    _write_plain_eml(eml)
    report = preview_email_export(dest_dir=tmp_path / "dest", input_paths=[eml])
    entry = report.preview["file_entries"][0]
    assert entry["category"] == "supported_now"
    assert entry["import_action_available"] is True


def test_mbox_classified_supported_later(tmp_path):
    mbox = tmp_path / "archive.mbox"
    mbox.write_text("From sender@example.com Mon Jan 01 00:00:00 2026\n", encoding="utf-8")
    report = preview_email_export(dest_dir=tmp_path / "dest", input_paths=[mbox])
    entry = report.preview["file_entries"][0]
    assert entry["category"] == "supported_later"
    assert entry["import_action_available"] is False


def test_unsupported_file_classified(tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("plain text", encoding="utf-8")
    report = preview_email_export(dest_dir=tmp_path / "dest", input_paths=[bad])
    entry = report.preview["file_entries"][0]
    assert entry["category"] == "unsupported"


def test_recursive_requires_explicit_flag(tmp_path):
    folder = tmp_path / "folder"
    sub = folder / "nested"
    sub.mkdir(parents=True)
    eml = sub / "mail.eml"
    _write_plain_eml(eml)
    without = preview_email_export(dest_dir=tmp_path / "dest", input_paths=[folder], recursive=False)
    assert without.preview["supported_now_count"] == 0
    assert without.preview["files_seen"] == 0
    with_recursive = preview_email_export(
        dest_dir=tmp_path / "dest2",
        input_paths=[folder],
        recursive=True,
    )
    assert with_recursive.preview["supported_now_count"] == 1


def test_preview_rejects_input_symlink_before_resolve_monkeypatch(tmp_path, monkeypatch):
    eml = tmp_path / "mail.eml"
    _write_plain_eml(eml)
    resolve_called: list[str] = []
    original_is_symlink = Path.is_symlink
    original_resolve = Path.resolve

    def tracking_resolve(self, *args, **kwargs):
        resolve_called.append(str(self))
        return original_resolve(self, *args, **kwargs)

    def fake_is_symlink(self):
        if self == eml:
            return True
        return original_is_symlink(self)

    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(Path, "resolve", tracking_resolve)

    with pytest.raises(EmailExportIngestError, match="Symlinks are not followed"):
        preview_email_export(dest_dir=tmp_path / "dest", input_paths=[eml])

    assert all(str(eml) not in p for p in resolve_called)


def test_oversized_file_skipped(tmp_path):
    eml = tmp_path / "big.eml"
    _write_plain_eml(eml)
    report = preview_email_export(
        dest_dir=tmp_path / "dest",
        input_paths=[eml],
        max_file_mb=0.000001,
    )
    entry = report.preview["file_entries"][0]
    assert entry["category"] == "skipped"
    assert "max size" in entry["reason"].lower()


def test_preview_writes_no_candidates(tmp_path):
    eml = tmp_path / "mail.eml"
    _write_plain_eml(eml)
    preview_email_export(dest_dir=tmp_path / "dest", input_paths=[eml])
    queue = tmp_path / "dest" / "memory_candidates" / REVIEW_QUEUE_FILENAME
    assert not queue.exists()


def test_apply_dry_run_writes_no_candidates(tmp_path):
    eml = tmp_path / "mail.eml"
    _write_plain_eml(eml)
    preview = preview_email_export(dest_dir=tmp_path / "dest", input_paths=[eml])
    report = apply_email_export(preview_json=Path(preview.json_path), apply=False)
    assert report.report["dry_run"] is True
    assert not (tmp_path / "dest" / "memory_candidates" / REVIEW_QUEUE_FILENAME).exists()


def test_apply_with_apply_writes_artifacts_and_candidates(tmp_path):
    eml = tmp_path / "mail.eml"
    _write_plain_eml(eml)
    preview = preview_email_export(dest_dir=tmp_path / "dest", input_paths=[eml])
    report = apply_email_export(preview_json=Path(preview.json_path), apply=True)
    assert report.report["staged_count"] == 1
    session = Path(preview.session_dir)
    assert list((session / "extracted_text").glob("*.txt"))
    assert list((session / "metadata").glob("*.json"))
    assert Path(report.json_path).name == APPLY_REPORT_JSON
    queue = tmp_path / "dest" / "memory_candidates" / REVIEW_QUEUE_FILENAME
    assert queue.is_file()


def test_candidate_source_type_email_export(tmp_path):
    eml = tmp_path / "mail.eml"
    _write_plain_eml(eml)
    preview = preview_email_export(dest_dir=tmp_path / "dest", input_paths=[eml])
    apply_email_export(preview_json=Path(preview.json_path), apply=True)
    record = json.loads(
        (tmp_path / "dest" / "memory_candidates" / REVIEW_QUEUE_FILENAME)
        .read_text(encoding="utf-8")
        .strip()
    )
    assert record["source_type"] == "email_export"
    assert record["review_status"] == "pending"
    assert record["suggested_memory_type"] == "email_history"


def test_candidate_live_memory_written_false(tmp_path):
    eml = tmp_path / "mail.eml"
    _write_plain_eml(eml)
    preview = preview_email_export(dest_dir=tmp_path / "dest", input_paths=[eml])
    apply_email_export(preview_json=Path(preview.json_path), apply=True)
    record = json.loads(
        (tmp_path / "dest" / "memory_candidates" / REVIEW_QUEUE_FILENAME)
        .read_text(encoding="utf-8")
        .strip()
    )
    assert record["live_memory_written"] is False


def test_repeat_apply_does_not_duplicate_candidates(tmp_path):
    eml = tmp_path / "mail.eml"
    _write_plain_eml(eml)
    preview = preview_email_export(dest_dir=tmp_path / "dest", input_paths=[eml])
    first = apply_email_export(preview_json=Path(preview.json_path), apply=True)
    second = apply_email_export(preview_json=Path(preview.json_path), apply=True)
    assert first.report["staged_count"] == 1
    assert second.report["duplicate_count"] == 1
    lines = [
        ln
        for ln in (tmp_path / "dest" / "memory_candidates" / REVIEW_QUEUE_FILENAME)
        .read_text(encoding="utf-8")
        .splitlines()
        if ln.strip()
    ]
    assert len(lines) == 1


def test_missing_source_fails_safely_on_apply(tmp_path):
    eml = tmp_path / "mail.eml"
    _write_plain_eml(eml)
    preview = preview_email_export(dest_dir=tmp_path / "dest", input_paths=[eml])
    eml.unlink()
    report = apply_email_export(preview_json=Path(preview.json_path), apply=True)
    assert report.report["staged_count"] == 0
    assert report.report["skipped_count"] >= 1


def test_source_size_changed_skipped_on_apply(tmp_path):
    eml = tmp_path / "mail.eml"
    _write_plain_eml(eml)
    preview = preview_email_export(dest_dir=tmp_path / "dest", input_paths=[eml])
    eml.write_text(eml.read_text(encoding="utf-8") + "\nextra line\n", encoding="utf-8")
    report = apply_email_export(preview_json=Path(preview.json_path), apply=True)
    assert report.report["staged_count"] == 0
    assert any(item["action"] == "skipped_validation_failed" for item in report.report["files"])


def test_source_file_preserved_unchanged(tmp_path):
    eml = tmp_path / "mail.eml"
    _write_plain_eml(eml)
    before = eml.read_bytes()
    preview = preview_email_export(dest_dir=tmp_path / "dest", input_paths=[eml])
    apply_email_export(preview_json=Path(preview.json_path), apply=True)
    assert eml.read_bytes() == before


def test_attachments_ignored(tmp_path):
    eml = tmp_path / "attach.eml"
    _write_attachment_eml(eml)
    preview = preview_email_export(dest_dir=tmp_path / "dest", input_paths=[eml])
    apply_email_export(preview_json=Path(preview.json_path), apply=True)
    meta_files = list((Path(preview.session_dir) / "metadata").glob("*.json"))
    assert meta_files
    meta = json.loads(meta_files[0].read_text(encoding="utf-8"))
    assert meta["attachments_ignored"] is True


def test_html_body_extracted_when_no_plain_text(tmp_path):
    eml = tmp_path / "html.eml"
    _write_html_eml(eml)
    preview = preview_email_export(dest_dir=tmp_path / "dest", input_paths=[eml])
    report = apply_email_export(preview_json=Path(preview.json_path), apply=True)
    assert report.report["staged_count"] == 1
    text_files = list((Path(preview.session_dir) / "extracted_text").glob("*.txt"))
    body = text_files[0].read_text(encoding="utf-8")
    assert "drywall" in body.lower()


def test_no_network_model_vector_calls(tmp_path):
    eml = tmp_path / "mail.eml"
    _write_plain_eml(eml)
    preview = preview_email_export(dest_dir=tmp_path / "dest", input_paths=[eml])
    with patch("project_guardian.memory_vector.VectorMemory") as vector:
        apply_email_export(preview_json=Path(preview.json_path), apply=True)
    vector.assert_not_called()
    bundle = json.loads(Path(preview.json_path).read_text(encoding="utf-8"))
    assert bundle["model_called"] is False
    assert bundle["embeddings_used"] is False
    assert bundle["live_memory_written"] is False
