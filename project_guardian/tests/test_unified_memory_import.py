# project_guardian/tests/test_unified_memory_import.py

from __future__ import annotations

import json
from email.message import EmailMessage
from pathlib import Path

import pytest

from project_guardian.local_ingestion.chatgpt_export_ingest import PREVIEW_JSON as CHATGPT_PREVIEW_JSON
from project_guardian.local_ingestion.email_export_ingest import PREVIEW_JSON as EMAIL_PREVIEW_JSON
from project_guardian.local_ingestion.import_session_preview import PREVIEW_JSON as TRANSCRIPTION_PREVIEW_JSON
from project_guardian.local_ingestion.memory_candidates import REVIEW_QUEUE_FILENAME
from project_guardian.local_ingestion.unified_memory_import import (
    SOURCE_TYPE_CHATGPT,
    SOURCE_TYPE_EMAIL,
    SOURCE_TYPE_TRANSCRIPTION,
    UnifiedMemoryImportError,
    unified_apply_memory_import,
    unified_preview_memory_import,
)


def _sample_chatgpt_export() -> list[dict]:
    return [
        {
            "title": "Drywall quote chat",
            "id": "conv-1",
            "mapping": {
                "node-1": {
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": ["Need a drywall quote."]},
                    }
                }
            },
        }
    ]


def _write_eml(path: Path, *, subject: str = "Drywall quote", body: str = "Please send a drywall quote.") -> None:
    message = EmailMessage()
    message["From"] = "contractor@example.com"
    message["To"] = "owner@example.com"
    message["Subject"] = subject
    message["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    message.set_content(body)
    path.write_bytes(message.as_bytes())


def test_preview_routes_txt_to_transcription(tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("Phone call about drywall quote.", encoding="utf-8")
    dest = tmp_path / "dest"

    summary = unified_preview_memory_import(dest_dir=dest, input_paths=[source])

    assert summary.source_type == SOURCE_TYPE_TRANSCRIPTION
    assert Path(summary.session_json).name == TRANSCRIPTION_PREVIEW_JSON
    assert summary.items_seen >= 1
    assert summary.model_called is False
    assert summary.embeddings_used is False
    assert summary.live_memory_written is False
    assert summary.autonomy_enabled is False


def test_preview_routes_chatgpt_json_to_chatgpt_preview(tmp_path):
    export = tmp_path / "conversations.json"
    export.write_text(json.dumps(_sample_chatgpt_export()), encoding="utf-8")
    dest = tmp_path / "dest"

    summary = unified_preview_memory_import(dest_dir=dest, input_paths=[export])

    assert summary.source_type == SOURCE_TYPE_CHATGPT
    assert Path(summary.session_json).name == CHATGPT_PREVIEW_JSON
    assert summary.items_seen == 1
    assert summary.candidates_available == 1


def test_preview_routes_eml_to_email_preview(tmp_path):
    eml = tmp_path / "quote.eml"
    _write_eml(eml)
    dest = tmp_path / "dest"

    summary = unified_preview_memory_import(dest_dir=dest, input_paths=[eml])

    assert summary.source_type == SOURCE_TYPE_EMAIL
    assert Path(summary.session_json).name == EMAIL_PREVIEW_JSON
    assert summary.items_seen == 1
    assert summary.candidates_available == 1


def test_explicit_source_type_overrides_auto_detect(tmp_path):
    export = tmp_path / "conversations.json"
    export.write_text(json.dumps(_sample_chatgpt_export()), encoding="utf-8")
    dest = tmp_path / "dest"

    summary = unified_preview_memory_import(
        dest_dir=dest,
        input_paths=[export],
        source_type=SOURCE_TYPE_TRANSCRIPTION,
    )

    assert summary.source_type == SOURCE_TYPE_TRANSCRIPTION
    assert Path(summary.session_json).name == TRANSCRIPTION_PREVIEW_JSON


def test_mixed_folder_fails_without_explicit_source_type(tmp_path):
    mixed = tmp_path / "mixed"
    mixed.mkdir()
    (mixed / "note.txt").write_text("transcription text", encoding="utf-8")
    _write_eml(mixed / "mail.eml")

    with pytest.raises(UnifiedMemoryImportError, match="Mixed source types"):
        unified_preview_memory_import(dest_dir=tmp_path / "dest", input_paths=[mixed])


def test_unknown_source_type_fails_safely(tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("hello", encoding="utf-8")

    with pytest.raises(UnifiedMemoryImportError, match="Unknown source type"):
        unified_preview_memory_import(
            dest_dir=tmp_path / "dest",
            input_paths=[source],
            source_type="mbox_archive",
        )


def test_apply_routes_transcription_session_json(tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("Phone call about drywall quote.", encoding="utf-8")
    dest = tmp_path / "dest"
    preview = unified_preview_memory_import(dest_dir=dest, input_paths=[source])

    summary = unified_apply_memory_import(session_json=Path(preview.session_json), apply=False)

    assert summary.source_type == SOURCE_TYPE_TRANSCRIPTION
    assert summary.dry_run is True
    assert summary.candidates_staged == 0
    assert Path(summary.apply_report_path).is_file()


def test_apply_routes_chatgpt_preview_json(tmp_path):
    export = tmp_path / "conversations.json"
    export.write_text(json.dumps(_sample_chatgpt_export()), encoding="utf-8")
    dest = tmp_path / "dest"
    preview = unified_preview_memory_import(dest_dir=dest, input_paths=[export])

    summary = unified_apply_memory_import(session_json=Path(preview.session_json), apply=False)

    assert summary.source_type == SOURCE_TYPE_CHATGPT
    assert summary.dry_run is True
    assert summary.candidates_staged == 0


def test_apply_routes_email_preview_json(tmp_path):
    eml = tmp_path / "quote.eml"
    _write_eml(eml)
    dest = tmp_path / "dest"
    preview = unified_preview_memory_import(dest_dir=dest, input_paths=[eml])

    summary = unified_apply_memory_import(session_json=Path(preview.session_json), apply=False)

    assert summary.source_type == SOURCE_TYPE_EMAIL
    assert summary.dry_run is True
    assert summary.candidates_staged == 0


def test_apply_dry_run_writes_no_candidates(tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("Unique drywall quote note.", encoding="utf-8")
    dest = tmp_path / "dest"
    preview = unified_preview_memory_import(dest_dir=dest, input_paths=[source])

    unified_apply_memory_import(session_json=Path(preview.session_json), apply=False)

    queue = dest / "memory_candidates" / REVIEW_QUEUE_FILENAME
    assert not queue.exists() or queue.read_text(encoding="utf-8").strip() == ""


def test_apply_with_apply_stages_pending_candidates(tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("Unique drywall quote for staging.", encoding="utf-8")
    dest = tmp_path / "dest"
    preview = unified_preview_memory_import(dest_dir=dest, input_paths=[source])

    summary = unified_apply_memory_import(session_json=Path(preview.session_json), apply=True)

    assert summary.candidates_staged >= 1
    queue = dest / "memory_candidates" / REVIEW_QUEUE_FILENAME
    assert queue.is_file()
    record = json.loads(queue.read_text(encoding="utf-8").strip())
    assert record["review_status"] == "pending"
    assert record["live_memory_written"] is False


def test_safety_flags_are_false(tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("Safety flag check.", encoding="utf-8")
    dest = tmp_path / "dest"
    preview = unified_preview_memory_import(dest_dir=dest, input_paths=[source])
    apply_summary = unified_apply_memory_import(
        session_json=Path(preview.session_json),
        apply=False,
    )

    for summary in (preview, apply_summary):
        assert summary.model_called is False
        assert summary.embeddings_used is False
        assert summary.live_memory_written is False
        assert summary.autonomy_enabled is False


def test_no_external_model_or_api_calls(tmp_path, monkeypatch):
    calls: list[str] = []

    def _blocked(*_args, **_kwargs):
        calls.append("blocked")
        from project_guardian.local_ingestion.import_session_preview import ImportSessionPreviewError

        raise ImportSessionPreviewError("external call blocked")

    monkeypatch.setattr(
        "project_guardian.local_ingestion.unified_memory_import.preview_memory_import_session",
        _blocked,
    )
    source = tmp_path / "note.txt"
    source.write_text("Should route locally.", encoding="utf-8")

    with pytest.raises(UnifiedMemoryImportError, match="external call blocked"):
        unified_preview_memory_import(dest_dir=tmp_path / "dest", input_paths=[source])

    assert calls == ["blocked"]
