from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_guardian.local_ingestion.chatgpt_export_ingest import (
    apply_chatgpt_export,
    conversation_to_text,
    preview_chatgpt_export,
)
from project_guardian.local_ingestion.memory_intelligence import (
    MEMORY_INTELLIGENCE_SUBDIR,
    MemoryIntelligenceError,
    expand_persisted_highlight,
    load_memory_intelligence_records,
    persist_source_intelligence,
    query_memory_intelligence,
)


def _sample_export() -> list[dict]:
    return [
        {
            "title": "Drywall Quote Chat",
            "id": "conv-memory-intel",
            "create_time": 1700000000,
            "update_time": 1700000100,
            "current_node": "node-2",
            "mapping": {
                "node-1": {
                    "id": "node-1",
                    "message": {
                        "author": {"role": "user"},
                        "content": {
                            "parts": [
                                "Need a drywall quote for the kitchen. "
                                "Please include labor and materials."
                            ]
                        },
                        "create_time": 1700000001,
                    },
                },
                "node-2": {
                    "id": "node-2",
                    "parent": "node-1",
                    "message": {
                        "author": {"role": "assistant"},
                        "content": {
                            "parts": [
                                "I can estimate it. Measure the wall area first."
                            ]
                        },
                        "create_time": 1700000002,
                    },
                },
            },
        }
    ]


def _write_export(path: Path) -> list[dict]:
    payload = _sample_export()
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def _apply_once(tmp_path: Path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    payload = _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)
    report = apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)
    return dest, export, payload, preview, report


def test_dry_run_creates_no_memory_intelligence_artifacts(tmp_path):
    dest = tmp_path / "dest"
    export = tmp_path / "conversations.json"
    _write_export(export)
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)

    report = apply_chatgpt_export(preview_json=Path(preview.json_path), apply=False)

    assert report.report["dry_run"] is True
    assert report.report["memory_intelligence_created"] == 0
    assert not (dest / MEMORY_INTELLIGENCE_SUBDIR).exists()


def test_chatgpt_apply_persists_source_linked_chunks_highlights_and_tags(tmp_path):
    dest, _export, payload, _preview, report = _apply_once(tmp_path)

    assert report.report["memory_intelligence_created"] == 1
    assert report.report["memory_intelligence_chunk_count"] >= 1
    assert report.report["memory_intelligence_highlight_count"] >= 2

    records = load_memory_intelligence_records(dest)
    assert len(records) == 1
    record = records[0]
    expected_text, _truncated, _message_count = conversation_to_text(payload[0])

    raw_path = dest / record["raw_source_path"]
    assert raw_path.read_bytes() == expected_text.encode("utf-8")
    assert record["selected_tags"] == ["chatgpt export", "conversation history"]
    assert "drywall quote chat" in record["candidate_tags"]
    assert record["model_called"] is False
    assert record["embeddings_used"] is False
    assert record["live_memory_written"] is False

    chunks = record["chunks"]
    assert chunks
    assert all(chunk["summary"] for chunk in chunks)
    assert sum(len(chunk["highlights"]) for chunk in chunks) >= 2
    assert all(chunk["source_id"] == record["source_id"] for chunk in chunks)
    assert all(chunk["source_sha256"] == record["source_sha256"] for chunk in chunks)


def test_repeat_apply_is_store_idempotent_with_no_duplicate_intelligence_records(tmp_path):
    dest, _export, _payload, preview, first = _apply_once(tmp_path)
    record_path = next((dest / MEMORY_INTELLIGENCE_SUBDIR / "records").glob("*.json"))
    raw_path = next((dest / MEMORY_INTELLIGENCE_SUBDIR / "raw_sources").glob("*.bin"))
    record_before = record_path.read_bytes()
    raw_before = raw_path.read_bytes()

    second = apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)

    assert first.report["memory_intelligence_created"] == 1
    assert second.report["memory_intelligence_created"] == 0
    assert second.report["memory_intelligence_unchanged"] == 1
    assert len(list((dest / MEMORY_INTELLIGENCE_SUBDIR / "records").glob("*.json"))) == 1
    assert len(list((dest / MEMORY_INTELLIGENCE_SUBDIR / "raw_sources").glob("*.bin"))) == 2
    assert record_path.read_bytes() == record_before
    assert raw_path.read_bytes() == raw_before


def test_read_only_query_explains_recall_and_expands_highlight_to_raw_source(tmp_path):
    dest, _export, payload, _preview, _report = _apply_once(tmp_path)
    expected_text, _truncated, _message_count = conversation_to_text(payload[0])

    results = query_memory_intelligence(dest, "drywall quote", limit=5)

    assert results
    reasons = {reason["type"] for reason in results[0]["recall_reasons"]}
    assert "text_relevance" in reasons
    assert "tag_match" in reasons
    assert "source_relation" in reasons
    assert results[0]["highlights"]

    highlight_id = results[0]["highlights"][0]["highlight_id"]
    expanded = expand_persisted_highlight(dest, highlight_id, context_bytes=80)
    assert expanded["highlight"] in expanded["surrounding_context"]
    assert expanded["surrounding_context"] in expanded["raw_source"]
    assert expanded["raw_source"] == expected_text


def test_candidate_tag_variants_collapse_to_one_proposal(tmp_path):
    report = persist_source_intelligence(
        dest_dir=tmp_path,
        raw_bytes=b"One useful source sentence. Another useful sentence.",
        source_identity="candidate-tag-source",
        canonical_tags=("conversation history",),
        tag_hints=("New Concept", "new-concept", " NEW   concept "),
    )

    assert report.candidate_tag_count == 1
    record = load_memory_intelligence_records(tmp_path)[0]
    assert record["candidate_tags"] == ["new concept"]
    for chunk in record["chunks"]:
        proposed = [
            item for item in chunk["tag_decisions"]
            if item["state"] == "candidate_proposed"
        ]
        assert len(proposed) == 1
        assert proposed[0]["normalized_tag"] == "new concept"
        assert proposed[0]["source_chunk_id"] == chunk["chunk_id"]
        assert proposed[0]["method"] == "deterministic-normalization"
        assert proposed[0]["rule_version"] == "tag-v1"


def test_tampered_chunk_offset_fails_closed_during_query(tmp_path):
    dest, _export, _payload, _preview, _report = _apply_once(tmp_path)
    record_path = next((dest / MEMORY_INTELLIGENCE_SUBDIR / "records").glob("*.json"))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["chunks"][0]["end_byte"] += 1
    record_path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(MemoryIntelligenceError):
        query_memory_intelligence(dest, "drywall")


def test_tampered_raw_source_fails_closed_during_query(tmp_path):
    dest, _export, _payload, _preview, _report = _apply_once(tmp_path)
    record = load_memory_intelligence_records(dest)[0]
    raw_path = dest / record["raw_source_path"]
    raw_path.write_bytes(raw_path.read_bytes() + b"tamper")

    with pytest.raises(MemoryIntelligenceError, match="provenance mismatch"):
        query_memory_intelligence(dest, "drywall")


def test_forged_tag_source_link_fails_closed_during_query(tmp_path):
    persist_source_intelligence(
        dest_dir=tmp_path,
        raw_bytes=b"A source with no roofing content.",
        source_identity="forged-tag-source-link",
        tag_hints=("roofing",),
    )
    record_path = next((tmp_path / MEMORY_INTELLIGENCE_SUBDIR / "records").glob("*.json"))
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["chunks"][0]["tag_decisions"][0]["source_chunk_id"] = "forged-chunk-id"
    record_path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(MemoryIntelligenceError, match="source linkage"):
        query_memory_intelligence(tmp_path, "roofing")


def test_original_export_survives_truncation_and_repeat_apply(tmp_path):
    export = tmp_path / "original.json"
    payload = _sample_export()
    payload[0]["mapping"]["node-2"]["message"]["content"]["parts"] = ["tail evidence café 🛠 " * 1000]
    original = (json.dumps(payload, ensure_ascii=False, indent=3) + "\r\n").encode("utf-8")
    export.write_bytes(original)
    dest = tmp_path / "dest"
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest, max_conversation_chars=160)
    first = apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)
    record = load_memory_intelligence_records(dest)[0]
    origin = record["origin_source"]
    assert (dest / origin["raw_source_path"]).read_bytes() == original
    result = query_memory_intelligence(dest, "drywall")[0]
    for highlight in result["highlights"]:
        expansion = expand_persisted_highlight(dest, highlight["highlight_id"])
        assert expansion["original_raw_source"].encode("utf-8") == original
        assert "[truncated for safety]" in expansion["raw_source"]
    before = {p.relative_to(dest): p.read_bytes() for p in (dest / MEMORY_INTELLIGENCE_SUBDIR).rglob("*") if p.is_file()}
    second = apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)
    after = {p.relative_to(dest): p.read_bytes() for p in (dest / MEMORY_INTELLIGENCE_SUBDIR).rglob("*") if p.is_file()}
    assert before == after
    assert first.report["staged_count"] == 1
    assert second.report["staged_count"] == 0
    assert second.report["memory_intelligence_unchanged"] == 1
    export.unlink()
    assert expand_persisted_highlight(dest, result["highlights"][0]["highlight_id"])["original_raw_source"].encode("utf-8") == original


@pytest.mark.parametrize("apply", [False, True])
def test_same_size_export_edit_rejected_before_ingestion_writes(tmp_path, apply):
    export = tmp_path / "conversations.json"
    _write_export(export)
    dest = tmp_path / "dest"
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)
    before = {p.relative_to(dest): p.read_bytes() for p in dest.rglob("*") if p.is_file()}
    export.write_bytes(export.read_bytes().replace(b"kitchen", b"bedroom"))
    from project_guardian.local_ingestion.chatgpt_export_ingest import ChatGPTExportIngestError
    with pytest.raises(ChatGPTExportIngestError, match="hash changed"):
        apply_chatgpt_export(preview_json=Path(preview.json_path), apply=apply)
    assert before == {p.relative_to(dest): p.read_bytes() for p in dest.rglob("*") if p.is_file()}


@pytest.mark.parametrize("field,value", [
    ("conversation_index", -1), ("conversation_index", True),
    ("conversation_index", 999), ("conversation_id", "forged"),
    ("max_conversation_chars", 41), ("max_conversation_chars", False),
])
def test_origin_segment_tampering_fails_closed(tmp_path, field, value):
    dest, _, _, _, report = _apply_once(tmp_path)
    record_path = Path(report.report["conversations"][0]["memory_intelligence"]["record_path"])
    record = json.loads(record_path.read_text())
    highlight_id = record["chunks"][0]["highlights"][0]["highlight_id"]
    record["origin_source"]["segment"][field] = value
    record_path.write_text(json.dumps(record))
    with pytest.raises(MemoryIntelligenceError):
        query_memory_intelligence(dest, "drywall")
    with pytest.raises(MemoryIntelligenceError):
        expand_persisted_highlight(dest, highlight_id)


def test_original_raw_source_tampering_fails_closed(tmp_path):
    dest, _, _, _, _ = _apply_once(tmp_path)
    record = load_memory_intelligence_records(dest)[0]
    path = dest / record["origin_source"]["raw_source_path"]
    path.write_bytes(path.read_bytes().replace(b"kitchen", b"bedroom"))
    with pytest.raises(MemoryIntelligenceError, match="provenance mismatch"):
        query_memory_intelligence(dest, "drywall")


def test_old_unhashed_preview_requires_fresh_preview(tmp_path):
    export = tmp_path / "conversations.json"
    _write_export(export)
    dest = tmp_path / "dest"
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)
    path = Path(preview.json_path)
    data = json.loads(path.read_text())
    del data["export_sha256"]
    path.write_text(json.dumps(data))
    from project_guardian.local_ingestion.chatgpt_export_ingest import ChatGPTExportIngestError
    with pytest.raises(ChatGPTExportIngestError, match="fresh preview"):
        apply_chatgpt_export(preview_json=path, apply=True)
    assert not (dest / MEMORY_INTELLIGENCE_SUBDIR).exists()


@pytest.mark.parametrize("tamper", ["path", "identity", "missing", "nested"])
def test_origin_source_reference_tampering_fails_closed(tmp_path, tamper):
    dest, _, _, _, report = _apply_once(tmp_path)
    record_path = Path(report.report["conversations"][0]["memory_intelligence"]["record_path"])
    record = json.loads(record_path.read_text())
    if tamper == "path":
        record["origin_source"]["raw_source_path"] = "../outside.json"
    elif tamper == "identity":
        record["origin_source"]["source_identity"] = "forged.json"
    elif tamper == "missing":
        (dest / record["origin_source"]["raw_source_path"]).unlink()
    else:
        record["origin_source"]["origin_source"] = {}
    record_path.write_text(json.dumps(record))
    with pytest.raises(MemoryIntelligenceError):
        query_memory_intelligence(dest, "drywall")


def test_multiple_conversations_share_one_original_artifact(tmp_path):
    export = tmp_path / "conversations.json"
    payload = _sample_export()
    second = json.loads(json.dumps(payload[0]))
    second["id"] = "second-conversation"
    second["title"] = "Separate Job"
    payload.append(second)
    export.write_text(json.dumps(payload))
    dest = tmp_path / "dest"
    preview = preview_chatgpt_export(export_json=export, dest_dir=dest)
    first = apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)
    records = load_memory_intelligence_records(dest)
    assert len(records) == first.report["memory_intelligence_created"] == 2
    assert len({r["origin_source"]["raw_source_path"] for r in records}) == 1
    assert {r["origin_source"]["segment"]["conversation_index"] for r in records} == {0, 1}
    assert len(list((dest / MEMORY_INTELLIGENCE_SUBDIR / "raw_sources").glob("*.bin"))) == 3
    second = apply_chatgpt_export(preview_json=Path(preview.json_path), apply=True)
    assert second.report["memory_intelligence_unchanged"] == 2
    assert second.report["staged_count"] == 0
