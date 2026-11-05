"""End-to-end integration of canonical incremental imports and local lexical retrieval.

Disposable bytes/history only; no model calls, network, user records, or installed Windows.
"""
from pathlib import Path

from project_guardian.document_ingestion import DocumentLibrary
from project_guardian.memory import MemoryCore


def _library(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    memory = MemoryCore(
        filepath=str(root / "synthetic_memory.json"),
        enable_timeline_logging=False,
        enable_vector_search=False,
    )
    return DocumentLibrary(memory)


def test_real_import_receipt_and_safe_cost_price_alias_survive_restart(tmp_path):
    root = tmp_path / "synthetic"
    library = _library(root)
    text = (
        "The Bellford mosaic price was 47 credits. "
        "The unrelated Atlas catalog includes technical part ATLAS-S, not Atla. "
    )
    receipt = library.import_bytes("receipt.txt", text.encode("utf-8"))
    assert receipt["status"] == "completed"
    assert receipt["char_count"] == len(text.strip())
    assert receipt["chunk_count"] >= 1
    found = library.search("Bellford mosaic cost")
    assert found and found[0]["source_id"] == receipt["source_id"]
    assert "price was 47 credits" in found[0]["text"]
    assert library.import_bytes("renamed.txt", text.encode("utf-8"))["duplicate"] is True
    restored = _library(root)
    again = restored.search("Bellford mosaic cost")
    assert again and again[0]["source_id"] == receipt["source_id"]
    assert (library.root / receipt["managed_copy"]).read_bytes() == text.encode()


def test_above_former_500k_boundary_import_then_normalized_retrieval(tmp_path):
    root = tmp_path / "large"
    library = _library(root)
    evidence = "The Bellford mosaic price was 47 credits.\n"
    filler = "anonymous synthetic index text with unrelated letters.\n" * 10_600
    raw = (filler + evidence).encode("utf-8")
    assert 500_000 < len(raw) < 8 * 1024 * 1024
    receipt = library.import_bytes("large-receipt.txt", raw)
    assert receipt["status"] == "completed"
    assert receipt["char_count"] == len(raw.strip())
    assert receipt["chunk_count"] > 500
    result = library.search("Bellford mosaic cost")
    assert result and any(
        row["source_id"] == receipt["source_id"] and "price was 47 credits" in row["text"]
        for row in result
    )
    assert (library.root / receipt["managed_copy"]).read_bytes() == raw
    restored = _library(root)
    assert restored.search("Bellford mosaic cost")
