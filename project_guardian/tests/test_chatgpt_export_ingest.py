# project_guardian/tests/test_chatgpt_export_ingest.py

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from project_guardian.local_ingestion.chatgpt_export_ingest import (
    APPLY_REPORT_JSON,
    PREVIEW_JSON,
    PREVIEW_MD,
    ChatGPTExportIngestError,
    apply_chatgpt_export,
    preview_chatgpt_export,
)
from project_guardian.local_ingestion.memory_candidates import REVIEW_QUEUE_FILENAME


def _sample_export() -> list[dict]:
    return [
        {
            "title": "Drywall quote chat",
            "id": "conv-1",
            "create_time": 1700000000,
            "update_time": 1700000100,
            "current_node": "node-2",
            "mapping": {
                "node-1": {
                    "id": "node-1",
                    "message": {
                        "author": {"role": "user"},
                        "content": {"parts": ["Need a drywall quote for the kitchen."]},
                        "create_time": 1700000001,
                    },
                },
                "node-2": {
                    "id": "node-2",
                    "parent": "node-1",
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {"parts": ["Sure, what are the dimensions?"]},
                        "create_time": 1700000002,
                    },
                },
            },
        },
        {
            "title": "Empty chat",
            "id": "conv-empty",
            "mapping": {},
        },
    ]


def _write_export(path: Path) -> None:
    path.write_text(json.dumps(_sample_export()), encoding="utf-8")


def test_preview_requires_explicit_paths(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    report = preview_chatgpt_export(export_json=export, dest_dir=dest)
    assert report.preview["export_path"]


def test_preview_writes_json_and_markdown(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)

    report = preview_chatgpt_export(export_json=export, dest_dir=dest)

    assert Path(report.json_path).name == PREVIEW_JSON
    assert Path(report.markdown_path).name == PREVIEW_MD
    assert Path(report.json_path).is_file()
    assert Path(report.markdown_path).is_file()


def test_preview_counts_conversations_and_messages(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)

    report = preview_chatgpt_export(export_json=export, dest_dir=dest)

    assert report.preview["conversation_count"] == 2
    assert report.preview["message_count_estimate"] >= 2
    assert report.preview["candidate_count_estimate"] == 1
    assert report.preview["skipped_count"] == 1


def test_preview_writes_no_candidates(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)

    preview_chatgpt_export(export_json=export, dest_dir=dest)

    queue = dest / "memory_candidates" / REVIEW_QUEUE_FILENAME
    assert not queue.exists()


def test_apply_dry_run_writes_no_candidates(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)

    report = apply_chatgpt_export(preview_json=Path(preview.json_path), apply=False)

    assert report.report["dry_run"] is True
    assert not (dest / "memory_candidates" / REVIEW_QUEUE_FILENAME).exists()


def test_apply_with_apply_stages_pending_candidates(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)

    report = apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)

    assert report.report["staged_count"] == 1
    queue = dest / "memory_candidates" / REVIEW_QUEUE_FILENAME
    assert queue.is_file()
    record = json.loads(queue.read_text(encoding="utf-8").strip())
    assert record["review_status"] == "pending"


def test_apply_writes_extracted_text_and_metadata(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)

    apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)

    session = Path(preview.session_dir)
    assert list((session / "extracted_text").glob("*.txt"))
    assert list((session / "metadata").glob("*.json"))


def test_candidate_source_type_chatgpt_export(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)
    apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)

    record = json.loads(
        (dest / "memory_candidates" / REVIEW_QUEUE_FILENAME).read_text(encoding="utf-8").strip()
    )
    assert record["source_type"] == "chatgpt_export"
    assert record["suggested_memory_type"] == "conversation_history"


def test_candidate_live_memory_written_false(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)
    apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)

    record = json.loads(
        (dest / "memory_candidates" / REVIEW_QUEUE_FILENAME).read_text(encoding="utf-8").strip()
    )
    assert record["live_memory_written"] is False


def test_repeat_apply_does_not_duplicate_candidates(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)

    first = apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)
    second = apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)

    assert first.report["staged_count"] == 1
    assert second.report["duplicate_count"] == 1
    lines = [
        ln
        for ln in (dest / "memory_candidates" / REVIEW_QUEUE_FILENAME)
        .read_text(encoding="utf-8")
        .splitlines()
        if ln.strip()
    ]
    assert len(lines) == 1


def test_malformed_json_fails_safely(tmp_path):
    dest = tmp_path / "dest"
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ChatGPTExportIngestError, match="Malformed"):
        preview_chatgpt_export(export_json=bad, dest_dir=dest)


def test_missing_export_fails_safely(tmp_path):
    dest = tmp_path / "dest"
    missing = tmp_path / "missing.json"
    with pytest.raises(ChatGPTExportIngestError, match="not found"):
        preview_chatgpt_export(export_json=missing, dest_dir=dest)


def test_export_size_changed_after_preview_fails_safely(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)
    export.write_text(json.dumps(_sample_export() + [{"title": "extra", "id": "x", "mapping": {}}]), encoding="utf-8")

    with pytest.raises(ChatGPTExportIngestError, match="size changed"):
        apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)


def test_no_network_model_vector_calls(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)

    with patch("project_guardian.memory_vector.VectorMemory") as vector:
        apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)

    vector.assert_not_called()
    bundle = json.loads(Path(preview.json_path).read_text(encoding="utf-8"))
    assert bundle["model_called"] is False
    assert bundle["embeddings_used"] is False
    assert bundle["live_memory_written"] is False


def test_apply_report_written(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)

    report = apply_chatgpt_export(preview_json=Path(preview.json_path), apply=False)

    assert Path(report.json_path).name == APPLY_REPORT_JSON
    assert Path(report.markdown_path).is_file()
