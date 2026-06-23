# project_guardian/tests/test_local_memory_pipeline_smoke.py

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from project_guardian.local_ingestion.approved_memory_context import CONTEXT_BUNDLE_JSON, CONTEXT_BUNDLE_MD
from project_guardian.local_ingestion.approved_memory_export import APPROVED_MEMORY_EXPORT_FILENAME
from project_guardian.local_ingestion.approved_memory_store import APPROVED_MEMORY_STORE_FILENAME
from project_guardian.local_ingestion.import_session_apply import APPLY_REPORT_JSON, APPLY_REPORT_MD
from project_guardian.local_ingestion.import_session_preview import PREVIEW_JSON, PREVIEW_MD
from project_guardian.local_ingestion.chatgpt_export_ingest import (
    APPLY_REPORT_JSON as CHATGPT_APPLY_REPORT_JSON,
    PREVIEW_JSON as CHATGPT_PREVIEW_JSON,
    PREVIEW_MD as CHATGPT_PREVIEW_MD,
)
from project_guardian.local_ingestion.email_export_ingest import (
    APPLY_REPORT_JSON as EMAIL_APPLY_REPORT_JSON,
    PREVIEW_JSON as EMAIL_PREVIEW_JSON,
    PREVIEW_MD as EMAIL_PREVIEW_MD,
)
from project_guardian.local_ingestion.local_memory_pipeline_smoke import (
    SOURCE_TYPE_CHATGPT,
    SOURCE_TYPE_EMAIL,
    SOURCE_TYPE_TRANSCRIPTION,
    LocalMemoryPipelineSmokeError,
    run_local_memory_pipeline_smoke,
)
from project_guardian.local_ingestion.memory_candidate_review import REVIEW_DECISIONS_FILENAME
from project_guardian.local_ingestion.memory_candidates import REVIEW_QUEUE_FILENAME


def test_smoke_returns_pass(tmp_path):
    summary = run_local_memory_pipeline_smoke(base_dir=tmp_path, keep_temp=True)
    assert summary.verdict == "PASS"


def test_smoke_creates_expected_artifacts(tmp_path):
    summary = run_local_memory_pipeline_smoke(base_dir=tmp_path, keep_temp=True)
    dest = tmp_path / "dest"
    session_dirs = list((dest / "import_sessions").iterdir())
    assert session_dirs
    session = session_dirs[0]
    assert (session / PREVIEW_JSON).is_file()
    assert (session / PREVIEW_MD).is_file()
    assert (session / APPLY_REPORT_JSON).is_file()
    assert (session / APPLY_REPORT_MD).is_file()
    assert (dest / "memory_candidates" / REVIEW_QUEUE_FILENAME).is_file()
    assert (dest / "memory_candidates" / REVIEW_DECISIONS_FILENAME).is_file()
    assert (dest / "memory_candidates" / APPROVED_MEMORY_EXPORT_FILENAME).is_file()
    assert (dest / "memory_store" / APPROVED_MEMORY_STORE_FILENAME).is_file()
    assert (dest / "memory_context" / CONTEXT_BUNDLE_JSON).is_file()
    assert (dest / "memory_context" / CONTEXT_BUNDLE_MD).is_file()
    assert summary.preview_created
    assert summary.apply_report_created
    assert summary.approved_export_created
    assert summary.memory_store_created
    assert summary.context_bundle_created


def test_smoke_search_finds_expected_memory(tmp_path):
    summary = run_local_memory_pipeline_smoke(base_dir=tmp_path, keep_temp=True)
    assert summary.search_result_count >= 1


def test_smoke_context_bundle_safety_flags(tmp_path):
    run_local_memory_pipeline_smoke(base_dir=tmp_path, keep_temp=True)
    bundle = json.loads(
        (tmp_path / "dest" / "memory_context" / CONTEXT_BUNDLE_JSON).read_text(encoding="utf-8")
    )
    assert bundle["model_called"] is False
    assert bundle["embeddings_used"] is False
    assert bundle["live_memory_written"] is False


def test_smoke_no_model_embedding_calls(tmp_path):
    with patch("project_guardian.memory_vector.VectorMemory") as vector:
        summary = run_local_memory_pipeline_smoke(base_dir=tmp_path, keep_temp=True)
    vector.assert_not_called()
    assert summary.model_called is False
    assert summary.embeddings_used is False


def test_json_output_includes_required_fields(tmp_path):
    summary = run_local_memory_pipeline_smoke(base_dir=tmp_path, keep_temp=True)
    payload = summary.to_dict()
    for key in (
        "verdict",
        "temp_root",
        "source_type",
        "preview_created",
        "apply_report_created",
        "chatgpt_preview_created",
        "chatgpt_apply_report_created",
        "email_preview_created",
        "email_apply_report_created",
        "extracted_text_created",
        "candidate_source_type",
        "candidates_created",
        "approvals_created",
        "approved_export_created",
        "memory_store_created",
        "search_result_count",
        "context_bundle_created",
        "model_called",
        "embeddings_used",
        "live_memory_written",
        "autonomy_enabled",
    ):
        assert key in payload


def test_keep_temp_preserves_working_dir(tmp_path):
    work = tmp_path / "smoke_keep"
    summary = run_local_memory_pipeline_smoke(base_dir=work, keep_temp=True)
    assert summary.verdict == "PASS"
    assert work.exists()
    assert (work / "dest" / "memory_store" / APPROVED_MEMORY_STORE_FILENAME).is_file()


def test_owned_temp_cleaned_up_when_not_keep_temp():
    summary = run_local_memory_pipeline_smoke(keep_temp=False)
    assert summary.verdict == "PASS"
    assert not Path(summary.temp_root).exists()


def test_smoke_only_touches_base_dir(tmp_path):
    outside = tmp_path.parent / "outside_marker"
    outside.write_text("untouched", encoding="utf-8")
    before = outside.read_text(encoding="utf-8")
    work = tmp_path / "isolated"
    run_local_memory_pipeline_smoke(base_dir=work, keep_temp=True)
    assert outside.read_text(encoding="utf-8") == before


def test_transcription_smoke_still_passes(tmp_path):
    summary = run_local_memory_pipeline_smoke(
        base_dir=tmp_path,
        keep_temp=True,
        source_type=SOURCE_TYPE_TRANSCRIPTION,
    )
    assert summary.verdict == "PASS"
    assert summary.source_type == SOURCE_TYPE_TRANSCRIPTION


def test_chatgpt_export_smoke_passes(tmp_path):
    summary = run_local_memory_pipeline_smoke(
        base_dir=tmp_path,
        keep_temp=True,
        source_type=SOURCE_TYPE_CHATGPT,
    )
    assert summary.verdict == "PASS"
    assert summary.source_type == SOURCE_TYPE_CHATGPT


def test_chatgpt_smoke_creates_chatgpt_source_candidates(tmp_path):
    summary = run_local_memory_pipeline_smoke(
        base_dir=tmp_path,
        keep_temp=True,
        source_type=SOURCE_TYPE_CHATGPT,
    )
    assert summary.candidate_source_type == "chatgpt_export"
    queue = tmp_path / "dest" / "memory_candidates" / REVIEW_QUEUE_FILENAME
    record = json.loads(queue.read_text(encoding="utf-8").strip())
    assert record["source_type"] == "chatgpt_export"
    assert record["review_status"] == "pending"
    assert record["live_memory_written"] is False


def test_chatgpt_smoke_search_finds_conversation_phrase(tmp_path):
    summary = run_local_memory_pipeline_smoke(
        base_dir=tmp_path,
        keep_temp=True,
        source_type=SOURCE_TYPE_CHATGPT,
    )
    assert summary.search_result_count >= 1


def test_chatgpt_smoke_context_bundle_safety_flags(tmp_path):
    run_local_memory_pipeline_smoke(
        base_dir=tmp_path,
        keep_temp=True,
        source_type=SOURCE_TYPE_CHATGPT,
    )
    bundle = json.loads(
        (tmp_path / "dest" / "memory_context" / CONTEXT_BUNDLE_JSON).read_text(encoding="utf-8")
    )
    assert bundle["model_called"] is False
    assert bundle["embeddings_used"] is False
    assert bundle["live_memory_written"] is False


def test_chatgpt_smoke_preserves_source_export_hash(tmp_path):
    summary = run_local_memory_pipeline_smoke(
        base_dir=tmp_path,
        keep_temp=True,
        source_type=SOURCE_TYPE_CHATGPT,
    )
    assert summary.verdict == "PASS"
    export_path = tmp_path / "source" / "conversations.json"
    assert export_path.is_file()
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload[0]["title"] == "Drywall quote chat"


def test_chatgpt_smoke_creates_extracted_text_and_metadata(tmp_path):
    summary = run_local_memory_pipeline_smoke(
        base_dir=tmp_path,
        keep_temp=True,
        source_type=SOURCE_TYPE_CHATGPT,
    )
    assert summary.extracted_text_created
    assert summary.chatgpt_preview_created
    assert summary.chatgpt_apply_report_created
    session_dirs = list((tmp_path / "dest" / "chatgpt_import_sessions").iterdir())
    assert session_dirs
    session = session_dirs[0]
    assert (session / CHATGPT_PREVIEW_JSON).is_file()
    assert (session / CHATGPT_PREVIEW_MD).is_file()
    assert (session / CHATGPT_APPLY_REPORT_JSON).is_file()


def test_unknown_source_type_rejected(tmp_path):
    with pytest.raises(LocalMemoryPipelineSmokeError, match="Unknown source type"):
        run_local_memory_pipeline_smoke(
            base_dir=tmp_path,
            keep_temp=True,
            source_type="mbox_archive",
        )


def test_email_export_smoke_passes(tmp_path):
    summary = run_local_memory_pipeline_smoke(
        base_dir=tmp_path,
        keep_temp=True,
        source_type=SOURCE_TYPE_EMAIL,
    )
    assert summary.verdict == "PASS"
    assert summary.source_type == SOURCE_TYPE_EMAIL


def test_email_smoke_creates_email_source_candidates(tmp_path):
    summary = run_local_memory_pipeline_smoke(
        base_dir=tmp_path,
        keep_temp=True,
        source_type=SOURCE_TYPE_EMAIL,
    )
    assert summary.candidate_source_type == "email_export"
    queue = tmp_path / "dest" / "memory_candidates" / REVIEW_QUEUE_FILENAME
    record = json.loads(queue.read_text(encoding="utf-8").strip())
    assert record["source_type"] == "email_export"
    assert record["review_status"] == "pending"
    assert record["live_memory_written"] is False


def test_email_smoke_search_finds_email_phrase(tmp_path):
    summary = run_local_memory_pipeline_smoke(
        base_dir=tmp_path,
        keep_temp=True,
        source_type=SOURCE_TYPE_EMAIL,
    )
    assert summary.search_result_count >= 1


def test_email_smoke_context_bundle_safety_flags(tmp_path):
    run_local_memory_pipeline_smoke(
        base_dir=tmp_path,
        keep_temp=True,
        source_type=SOURCE_TYPE_EMAIL,
    )
    bundle = json.loads(
        (tmp_path / "dest" / "memory_context" / CONTEXT_BUNDLE_JSON).read_text(encoding="utf-8")
    )
    assert bundle["model_called"] is False
    assert bundle["embeddings_used"] is False
    assert bundle["live_memory_written"] is False


def test_email_smoke_preserves_source_email_unchanged(tmp_path):
    summary = run_local_memory_pipeline_smoke(
        base_dir=tmp_path,
        keep_temp=True,
        source_type=SOURCE_TYPE_EMAIL,
    )
    assert summary.verdict == "PASS"
    eml_path = tmp_path / "source" / "drywall_quote.eml"
    assert eml_path.is_file()
    assert "drywall quote" in eml_path.read_text(encoding="utf-8").lower()


def test_email_smoke_creates_extracted_text_and_metadata(tmp_path):
    summary = run_local_memory_pipeline_smoke(
        base_dir=tmp_path,
        keep_temp=True,
        source_type=SOURCE_TYPE_EMAIL,
    )
    assert summary.extracted_text_created
    assert summary.email_preview_created
    assert summary.email_apply_report_created
    session_dirs = list((tmp_path / "dest" / "email_import_sessions").iterdir())
    assert session_dirs
    session = session_dirs[0]
    assert (session / EMAIL_PREVIEW_JSON).is_file()
    assert (session / EMAIL_PREVIEW_MD).is_file()
    assert (session / EMAIL_APPLY_REPORT_JSON).is_file()


def test_json_output_includes_email_fields(tmp_path):
    summary = run_local_memory_pipeline_smoke(
        base_dir=tmp_path,
        keep_temp=True,
        source_type=SOURCE_TYPE_EMAIL,
    )
    payload = summary.to_dict()
    assert payload["source_type"] == SOURCE_TYPE_EMAIL
    for key in (
        "email_preview_created",
        "email_apply_report_created",
        "extracted_text_created",
        "candidate_source_type",
    ):
        assert key in payload


def test_json_output_includes_source_type(tmp_path):
    summary = run_local_memory_pipeline_smoke(
        base_dir=tmp_path,
        keep_temp=True,
        source_type=SOURCE_TYPE_CHATGPT,
    )
    payload = summary.to_dict()
    assert payload["source_type"] == SOURCE_TYPE_CHATGPT
    for key in (
        "chatgpt_preview_created",
        "chatgpt_apply_report_created",
        "email_preview_created",
        "email_apply_report_created",
        "extracted_text_created",
        "candidate_source_type",
    ):
        assert key in payload
